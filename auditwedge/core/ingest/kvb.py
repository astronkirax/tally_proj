"""Karur Vysya Bank (KVB) statement adapter.

KVB prints a clean tabular statement:
    Txn Date | Value Date | Particulars | Ref. No. | Debit | Credit | Balance
with DD-MMM-YYYY dates and *separate* Debit/Credit columns. Each row therefore ends in
a (Debit, Credit, Balance) money-triple. We anchor on those triples and validate every
row against the running balance, so the parse is correct by construction — and it scales
to any size (these statements run to dozens of pages / thousands of rows), unlike a
single-shot LLM parse.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from core.ingest.base import BankAdapter, ParseError, to_decimal
from core.schema import AccountInfo, DrCr, Statement, Transaction

DATE_RE = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{4})$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
MONEY_RE = re.compile(r"^-?[\d,]+\.\d{2}$")
REFNUM_RE = re.compile(r"^\d{6,}$")
PAGENO_RE = re.compile(r"^\d{1,3}$")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}

_BOILER = {
    "ACCOUNT STATEMENT", "Txn Date", "Value Date", "Particulars", "Ref. No.",
    "Debit", "Credit", "Balance",
}
EPS = Decimal("0.05")


def _pdate(s: str) -> date | None:
    m = DATE_RE.match(s)
    if not m:
        return None
    d, mon, y = m.groups()
    mm = MONTHS.get(mon.upper())
    return date(int(y), mm, int(d)) if mm else None


class KVBAdapter(BankAdapter):
    bank_name = "KVB"

    @classmethod
    def matches(cls, text: str) -> bool:
        up = text.upper()
        if "KVB.BANK.IN" in up or "KARUR VYSYA" in up:
            return True
        return all(k in up for k in
                   ("TXN DATE", "VALUE DATE", "PARTICULARS", "REF. NO", "DEBIT", "CREDIT", "BALANCE"))

    def parse(self, text: str) -> Statement:
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

        # opening balance from the B/F ("brought forward") row
        opening, floor0 = Decimal("0"), 0
        for i, ln in enumerate(lines):
            if ln.upper().startswith("B/F"):
                for j in range(i + 1, min(i + 8, len(lines))):
                    if MONEY_RE.match(lines[j]):
                        opening, floor0 = to_decimal(lines[j]), j + 1
                        break
                break

        # collect maximal runs of consecutive money lines; length-3 runs = Debit,Credit,Balance
        is_money = [bool(MONEY_RE.match(ln)) for ln in lines]
        triples: list[tuple[int, Decimal, Decimal, Decimal]] = []
        i, n = 0, len(lines)
        while i < n:
            if is_money[i]:
                j = i
                while j < n and is_money[j]:
                    j += 1
                if j - i == 3:
                    triples.append((i, to_decimal(lines[i]), to_decimal(lines[i + 1]), to_decimal(lines[i + 2])))
                i = j
            else:
                i += 1

        # chain against the running balance + enrich each row
        txns: list[Transaction] = []
        prev = opening
        last_end = floor0
        for didx, debit, credit, bal in triples:
            if abs((prev - debit + credit) - bal) > EPS:  # doesn't chain -> not a real row
                last_end = didx + 3
                continue
            dr_cr = DrCr.DEBIT if debit > 0 else DrCr.CREDIT
            amount = debit if debit > 0 else credit
            txn_date, value_date, ref, narration = self._enrich(lines[last_end:didx])
            txns.append(Transaction(
                row=len(txns) + 1,
                txn_date=txn_date or value_date or date(1900, 1, 1),
                value_date=value_date, narration=narration, ref_no=ref,
                amount=abs(amount), dr_cr=dr_cr, balance=bal,
            ))
            prev = bal
            last_end = didx + 3

        if not txns:
            raise ParseError("KVB: no transactions could be parsed.")

        info = AccountInfo(bank=self.bank_name, opening_balance=opening,
                           closing_balance=txns[-1].balance,
                           from_date=txns[0].txn_date, to_date=txns[-1].txn_date)
        self._header(lines[:floor0] if floor0 else lines[:80], info)
        return Statement(info=info, transactions=txns)

    def _enrich(self, block: list[str]):
        dates = [ln for ln in block if DATE_RE.match(ln)]
        txn_date = _pdate(dates[0]) if dates else None
        value_date = _pdate(dates[1]) if len(dates) > 1 else None
        narr = [ln for ln in block
                if not (DATE_RE.match(ln) or TIME_RE.match(ln) or ln in _BOILER or PAGENO_RE.match(ln))]
        ref = None
        if narr and REFNUM_RE.match(narr[-1]):
            ref = narr[-1]
            narr = narr[:-1]
        return txn_date, value_date, ref, re.sub(r"\s+", " ", " ".join(narr)).strip()

    def _header(self, head: list[str], info: AccountInfo):
        joined = "\n".join(head)
        m = re.search(r"Customer ID\s*:\s*(\d+)", joined)
        if m:
            info.account_no = info.account_no or None  # KVB masks the number; keep customer id in name if useful
        m = re.search(r"(?:A/?C\s*(?:NO|Number)|Account\s*(?:No|Number))\s*[:\-]?\s*([0-9Xx]{6,20})", joined)
        if m:
            info.account_no = m.group(1)
