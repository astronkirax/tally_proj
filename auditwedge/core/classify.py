"""Transaction classification: rules first, optional LLM fallback.

Design goals:
  * **Deterministic-first** — a keyword rule table (built from real HDFC narrations)
    handles the bulk. This runs offline, free, and is auditable.
  * **LLM only for the remainder** — if a DeepSeek key is configured, ambiguous /
    low-confidence rows are sent to the model. Keeps cost to a few paise per statement
    and is entirely optional (the app works fully without it).
  * **Co-pilot, not autopilot** — every row keeps a ``confidence`` and ``source`` so the
    reviewer can see what to double-check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.llm import chat_json, llm_available
from core.schema import DrCr, Statement, Transaction

LOW_CONFIDENCE = 0.5  # rows at/below this are candidates for the LLM pass / human review


@dataclass(frozen=True)
class Rule:
    keywords: tuple[str, ...]  # uppercase substrings; match if ANY appears in narration
    ledger: str
    ctype: str  # counterparty_type
    category: str
    confidence: float
    applies_to: DrCr | None = None  # restrict to DR/CR, or None for both
    counterparty: str | None = None  # fixed name when the rule identifies a known party


# Order matters: most specific first. Derived from the patterns actually seen in the
# Gateway2Konaseema HDFC statement.
RULES: tuple[Rule, ...] = (
    # --- bank charges (all debits) ---
    Rule(("AQB SER CHGS", "STMT OF A/C CHGS", "SER CHGS INC GST", "INSTAALERT",
          "INSTAALERTCHG", "ALERTCHG", "DEBIT CARD ANNUAL FEE", "STMT CHGS"),
         "Bank Charges", "bank", "Bank Charges", 0.95, DrCr.DEBIT, "HDFC Bank"),
    # --- income / aggregators (credits) ---
    Rule(("GOOGLE INDIA DIGITAL", "GOOGLEINDIADIGITAL", "GOOG-PAYMENTS"),
         "Cab Service Income", "aggregator", "Sales / Service Income", 0.9, DrCr.CREDIT,
         "Google India Digital Services"),
    Rule(("RAZORPAY",), "Cab Service Income", "aggregator", "Sales / Service Income", 0.9,
         DrCr.CREDIT, "Razorpay Software Pvt Ltd"),
    Rule(("TRAVEL KARMA", "TRAVEL\nKARMA"), "Corporate Cab Hire Income", "corporate",
         "Sales / Service Income", 0.9, DrCr.CREDIT, "Travel Karma"),
    Rule(("LARSEN AND TOUBRO", "LARSEN AND TOUB"), "Corporate Cab Hire Income", "corporate",
         "Sales / Service Income", 0.9, DrCr.CREDIT, "Larsen & Toubro Ltd"),
    Rule(("ATURIA CONSTRUCTION",), "Corporate Cab Hire Income", "corporate",
         "Sales / Service Income", 0.9, DrCr.CREDIT, "Aturia Construction Pvt Ltd"),
    Rule(("EQUIP OFFSHORE",), "Corporate Cab Hire Income", "corporate",
         "Sales / Service Income", 0.9, DrCr.CREDIT, "Equip Offshore LLP"),
    # --- expenses (debits) ---
    Rule(("GOOGLE PLAY", "GOOGLESERVIS", "GOOGLESERVICES", "GOOGLE PLAY SE",
          "CYBS S"), "Software & Hosting", "vendor", "Software & Subscriptions", 0.85,
         DrCr.DEBIT, "Google"),
    Rule(("HOSTINGER", "RAZ*HOSTINGER"), "Software & Hosting", "vendor",
         "Software & Subscriptions", 0.85, DrCr.DEBIT, "Hostinger"),
    Rule(("EPDCL", "EASTERN POWER"), "Electricity Charges", "govt", "Utilities", 0.9,
         DrCr.DEBIT, "APEPDCL (Electricity)"),
    Rule(("VODAFONE", "JIO-", "-JIO", "AIRTEL"), "Telephone & Internet", "telecom",
         "Telecom", 0.85, DrCr.DEBIT),
    Rule(("FASTTAG", "FASTAG", "FASTTA"), "FASTag & Toll", "vendor", "Vehicle Running",
         0.85, DrCr.DEBIT),
    Rule(("FUEL", "PETROL", "FUELS"), "Fuel & Petrol", "vendor", "Vehicle Running", 0.8,
         DrCr.DEBIT),
    # 'ADVANCE' to an individual = the classic driver advance (also an audit flag later)
    Rule(("ADVANCE",), "Driver Advances", "individual", "Driver Advance", 0.7, DrCr.DEBIT),
    Rule(("TAXI", "CAB ", "INNOVA", "ROADSTER", "ROADSTAR"), "Vehicle Hire / Taxi",
         "individual", "Vehicle Hire", 0.65, DrCr.DEBIT),
)

# --- counterparty name extraction ------------------------------------------
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def extract_counterparty(narration: str, dr_cr: DrCr) -> str | None:
    """Best-effort payee/payer name from the narration structure."""
    up = narration.upper()
    parts = [p.strip() for p in re.split(r"[-]", narration) if p.strip()]
    if up.startswith("UPI"):
        # UPI-<NAME>-<vpa>-<bank>-<ref>-<remark>
        return parts[1] if len(parts) > 1 else None
    if up.startswith("IMPS"):
        # IMPS-<ref>-<NAME>-<bank>-...
        return parts[2] if len(parts) > 2 else None
    if "NEFT" in up or "RTGS" in up:
        # NEFT CR-<IFSC>-<NAME>-...
        for i, p in enumerate(parts[:-1]):
            if _IFSC.match(p.replace(" ", "")):
                return parts[i + 1]
        return parts[1] if len(parts) > 1 else None
    return None


def classify_txn(txn: Transaction) -> Transaction:
    up = re.sub(r"\s+", " ", txn.narration.upper())
    for rule in RULES:
        if rule.applies_to is not None and rule.applies_to is not txn.dr_cr:
            continue
        if any(k in up for k in rule.keywords):
            txn.ledger = rule.ledger
            txn.counterparty_type = rule.ctype
            txn.category = rule.category
            txn.confidence = rule.confidence
            txn.counterparty = rule.counterparty or extract_counterparty(txn.narration, txn.dr_cr)
            txn.source = "rule"
            return txn
    # Fallback: unclassified suspense, flagged low-confidence for review.
    txn.counterparty = extract_counterparty(txn.narration, txn.dr_cr)
    txn.counterparty_type = "individual" if txn.counterparty else "unknown"
    if txn.dr_cr is DrCr.CREDIT:
        txn.ledger, txn.category = "Suspense - Receipts", "Unclassified Income"
    else:
        txn.ledger, txn.category = "Suspense - Payments", "Unclassified Expense"
    txn.confidence = 0.3
    txn.source = "unclassified"
    return txn


def classify_statement(statement: Statement, use_llm: bool = False) -> dict:
    """Classify every transaction in place. Returns a small stats dict for the UI."""
    for t in statement.transactions:
        classify_txn(t)

    llm_applied = 0
    if use_llm and llm_available():
        low = [t for t in statement.transactions if t.confidence <= LOW_CONFIDENCE]
        llm_applied = _llm_pass(low)

    n = len(statement.transactions)
    classified = sum(1 for t in statement.transactions if t.confidence > LOW_CONFIDENCE)
    return {
        "total": n,
        "classified": classified,
        "needs_review": n - classified,
        "llm_applied": llm_applied,
        "rate": round(classified / n, 3) if n else 0.0,
    }


# --- optional LLM (DeepSeek) fallback ---------------------------------------
def _llm_pass(txns: list[Transaction]) -> int:
    """Send low-confidence narrations to the LLM. Fully guarded/optional."""
    if not txns:
        return 0
    ledgers = sorted({r.ledger for r in RULES} | {"Suspense - Receipts", "Suspense - Payments"})
    system = "You are an Indian accounting assistant. Reply ONLY with valid JSON."
    user = (
        "Classify each bank narration into ONE ledger from this list:\n"
        + ", ".join(ledgers) + "\n\n"
        'Return JSON of the form {"results": [{"ledger": str, "counterparty_type": one of '
        "[aggregator,corporate,individual,bank,govt,telecom,vendor,self,unknown], "
        '"category": str}, ...]} with one item per narration, IN THE SAME ORDER.\n\n'
        "Narrations:\n"
        + "\n".join(f"{i}. [{t.dr_cr.value}] {t.narration}" for i, t in enumerate(txns))
    )
    # ~200 output tokens per row; scale so the JSON never truncates (truncation -> None).
    budget = min(60_000, 3_000 + len(txns) * 250)
    out = chat_json(system, user, max_tokens=budget)
    rows = out.get("results") if isinstance(out, dict) else out
    if not isinstance(rows, list):
        return 0

    applied = 0
    for t, row in zip(txns, rows):
        if isinstance(row, dict) and row.get("ledger"):
            t.ledger = row["ledger"]
            t.counterparty_type = row.get("counterparty_type", t.counterparty_type)
            t.category = row.get("category", t.category)
            t.confidence = 0.75
            t.source = "llm"
            applied += 1
    return applied
