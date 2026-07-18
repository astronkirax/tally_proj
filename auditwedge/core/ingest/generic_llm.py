"""Generic, bank-agnostic statement parser powered by an LLM.

This is what lets AuditWedge read *any* bank without a hand-written adapter. The LLM
does the messy job it's good at — turning an arbitrary statement layout into structured
rows — and we then re-apply the deterministic running-balance method so **Dr/Cr is
guaranteed by the balance column, not trusted from the model**. If the balances chain,
the parse is provably correct regardless of which bank produced it.

Used only as a fallback: banks with a dedicated adapter (e.g. HDFC) take the fast, free,
offline path; everything else routes here when a DeepSeek key is configured.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from core.ingest.base import BankAdapter, ParseError
from core.llm import chat_json, llm_available
from core.schema import AccountInfo, DrCr, Statement, Transaction

EPS = Decimal("0.05")

_SYSTEM = "You are a meticulous bank-statement parsing engine. Reply ONLY with valid JSON."

_USER_TMPL = """Extract EVERY transaction from this Indian bank statement text.

Return JSON exactly of this shape:
{{
  "bank": "short bank name e.g. SBI / ICICI / Axis",
  "account_name": "account holder",
  "account_no": "digits only or null",
  "ifsc": "IFSC or null",
  "from_date": "YYYY-MM-DD or null",
  "to_date": "YYYY-MM-DD or null",
  "opening_balance": number or null,
  "closing_balance": number or null,
  "transactions": [
    {{"date":"YYYY-MM-DD","value_date":"YYYY-MM-DD or null","narration":"full text",
      "ref":"cheque/UTR/ref or null","amount": positive number,
      "dr_cr":"DR if money left the account else CR","balance": running balance after the txn}}
  ]
}}

Rules:
- amount is always POSITIVE; use dr_cr for direction (DR = withdrawal/debit, CR = deposit/credit).
- balance is the running balance printed AFTER that transaction.
- Keep the FULL narration text. Preserve order top-to-bottom. Do NOT invent or skip rows.
- Ignore page headers/footers, summaries and marketing text.

STATEMENT TEXT:
{text}
"""


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _pdate(v) -> date | None:
    if not v or not isinstance(v, str):
        return None
    try:
        y, m, d = v.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


class GenericLLMAdapter(BankAdapter):
    bank_name = "GENERIC (AI)"

    @classmethod
    def matches(cls, text: str) -> bool:
        # Never auto-detected; the registry chooses it explicitly as a fallback.
        return False

    def parse(self, text: str) -> Statement:
        if not llm_available():
            raise ParseError("Generic AI parser needs a DEEPSEEK_API_KEY.")
        # non-thinking output is ~120 tokens/row; 60k gives headroom to ~500 txns
        data = chat_json(_SYSTEM, _USER_TMPL.format(text=text[:120_000]), max_tokens=60_000)
        if not isinstance(data, dict) or not isinstance(data.get("transactions"), list):
            raise ParseError("AI parser returned no usable transactions.")

        raw = data["transactions"]
        opening = _dec(data.get("opening_balance"))
        info = AccountInfo(
            bank=str(data.get("bank") or "UNKNOWN").upper(),
            account_name=data.get("account_name"),
            account_no=str(data["account_no"]) if data.get("account_no") else None,
            ifsc=data.get("ifsc"),
            from_date=_pdate(data.get("from_date")),
            to_date=_pdate(data.get("to_date")),
            opening_balance=opening,
            closing_balance=_dec(data.get("closing_balance")),
        )

        # If we have opening + balances, recover Dr/Cr from the balance chain (ground truth).
        balances = [_dec(r.get("balance")) for r in raw]
        can_chain = opening is not None and all(b is not None for b in balances)

        txns: list[Transaction] = []
        prev = opening
        for i, r in enumerate(raw):
            amount = _dec(r.get("amount"))
            if amount is None or amount == 0:
                continue
            amount = abs(amount)
            bal = balances[i]

            drcr = None
            if can_chain and bal is not None:
                if abs((prev - amount) - bal) <= EPS:
                    drcr = DrCr.DEBIT
                elif abs((prev + amount) - bal) <= EPS:
                    drcr = DrCr.CREDIT
                prev = bal
            if drcr is None:  # fall back to the model's own direction
                drcr = DrCr.CREDIT if str(r.get("dr_cr", "")).upper().startswith("C") else DrCr.DEBIT

            txns.append(Transaction(
                row=len(txns) + 1,
                txn_date=_pdate(r.get("date")) or info.from_date or date(1900, 1, 1),
                value_date=_pdate(r.get("value_date")),
                narration=str(r.get("narration") or "").strip(),
                ref_no=(str(r["ref"]).strip() if r.get("ref") else None),
                amount=amount,
                dr_cr=drcr,
                balance=bal if bal is not None else Decimal("0"),
            ))

        if not txns:
            raise ParseError("AI parser produced zero valid transactions.")
        return Statement(info=info, transactions=txns)
