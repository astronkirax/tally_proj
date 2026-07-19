"""Tag every transaction into a transparent bucket for the financials layer.

We do NOT try to reverse-engineer the auditor's manual curation. Instead each row is
tagged by an auditable rule so the Summary reconciles exactly to the bank:

  business  — an identifiable counterparty (a real Sundry Debtor / Creditor)
  suspense  — no identifiable party, or a reward/refund/reversal narration
  charge    — bank charges (kept separate; not turnover)

The four totals (business/suspense × receipts/payments) always add back to the exact
bank receipts and payments, so nothing is hidden.
"""
from __future__ import annotations

from decimal import Decimal

from core.schema import DrCr, Statement

# narrations that mark a receipt/payment as non-business (kept in Suspense)
SUSPENSE_KW = (
    "CASHBACK", "CASH BACK", "REWARD", "REFUND", "REVERSAL", " REV ", "REV-",
    "RETURN AMOUNT", "IMPS RETURN", "NEFT RETURN",
)


def tag_buckets(statement: Statement) -> Statement:
    for t in statement.transactions:
        up = " " + t.narration.upper() + " "
        if t.ledger == "Bank Charges":
            t.bucket = "charge"
        elif any(k in up for k in SUSPENSE_KW):
            t.bucket = "suspense"
        elif t.counterparty and len(t.counterparty.strip()) >= 3:
            t.bucket = "business"
        else:
            t.bucket = "suspense"
    return statement


def bucket_totals(statement: Statement) -> dict:
    """Aggregate the tagged buckets into receipt/payment splits (exact, reconciling)."""
    z = Decimal("0")
    out = {
        "biz_receipts": z, "sus_receipts": z, "charge_receipts": z,
        "biz_payments": z, "sus_payments": z, "charge_payments": z,
        "total_receipts": z, "total_payments": z,
    }
    for t in statement.transactions:
        credit = t.dr_cr is DrCr.CREDIT
        side = "receipts" if credit else "payments"
        out[f"total_{side}"] += t.amount
        key = {"business": "biz", "suspense": "sus", "charge": "charge"}[t.bucket or "suspense"]
        out[f"{key}_{side}"] += t.amount
    return out
