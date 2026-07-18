"""Shared ingestion primitives + the self-checking running-balance classifier.

The heart of the engine is :func:`pair_by_running_balance`. Bank statements print an
*amount* and a *running balance* for every line but often don't machine-readably say
whether it was a debit or a credit. We recover Dr/Cr by walking the balance column:
for each candidate (amount, balance) pair, exactly one of ``prev - amount`` or
``prev + amount`` will equal the new balance. If neither does, the pair isn't a real
transaction (page noise, a stray number) and is skipped.

This makes the parser *self-verifying*: a clean parse chains from the opening balance
to the reported closing balance with zero drift. If it doesn't chain, we surface a
parse error instead of returning wrong numbers — which is the only acceptable failure
mode for audit software.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from core.schema import DrCr, Statement

# A transaction date on HDFC rows is dd/mm/yy (2-digit year). The header uses
# dd/mm/yyyy (4-digit) — keeping these distinct avoids mixing header dates into rows.
DATE_ONLY_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
DATE_LEAD_RE = re.compile(r"^(\d{2}/\d{2}/\d{2})\b")
MONEY_RE = re.compile(r"^-?[\d,]+\.\d{2}$")

EPS = Decimal("0.02")  # tolerance for the balance chain (HDFC parses exact; this is slack)


def to_decimal(s: str) -> Decimal:
    """'1,735.10' -> Decimal('1735.10'). Raises on non-money."""
    return Decimal(s.replace(",", "").strip())


def try_decimal(s: str) -> Decimal | None:
    try:
        return to_decimal(s)
    except (InvalidOperation, ValueError):
        return None


def parse_ddmmyy(s: str) -> date:
    d, m, y = s.split("/")
    return date(2000 + int(y), int(m), int(d))


def parse_ddmmyyyy(s: str) -> date:
    d, m, y = s.split("/")
    return date(int(y), int(m), int(d))


@dataclass
class SpineRecord:
    """One reconstructed transaction on the balance 'spine'."""

    dr_cr: DrCr
    amount: Decimal
    balance: Decimal
    amount_idx: int  # line index of the amount token (for later enrichment)


def pair_by_running_balance(
    tokens: list[tuple[int, Decimal]],
    opening: Decimal,
    eps: Decimal = EPS,
) -> tuple[list[SpineRecord], Decimal]:
    """Reconstruct Dr/Cr for every transaction from the balance column.

    ``tokens`` is the ordered list of (line_index, money_value) for every money-like
    line in the statement body. We consider consecutive-line pairs (amount, balance):
    if the balance chains from the previous balance by subtracting the amount it's a
    DEBIT, by adding it a CREDIT. Non-chaining pairs are skipped (self-cleaning).

    Returns (records, final_balance).
    """
    records: list[SpineRecord] = []
    prev = opening
    j = 0
    n = len(tokens)
    while j < n - 1:
        idx1, a1 = tokens[j]
        idx2, a2 = tokens[j + 1]
        if idx2 == idx1 + 1:  # amount and balance are adjacent lines
            if abs((prev - a1) - a2) <= eps:
                records.append(SpineRecord(DrCr.DEBIT, a1, a2, idx1))
                prev = a2
                j += 2
                continue
            if abs((prev + a1) - a2) <= eps:
                records.append(SpineRecord(DrCr.CREDIT, a1, a2, idx1))
                prev = a2
                j += 2
                continue
        j += 1
    return records, prev


class BankAdapter(ABC):
    """Interface every bank-format adapter implements. Add a new bank = new subclass."""

    bank_name: str = "UNKNOWN"

    @classmethod
    @abstractmethod
    def matches(cls, text: str) -> bool:
        """Cheap check: does this statement look like our bank's format?"""

    @abstractmethod
    def parse(self, text: str) -> Statement:
        """Full text of the statement -> canonical :class:`Statement`."""


class ParseError(RuntimeError):
    """Raised when the statement cannot be parsed into a clean, chaining Statement."""


class PdfPasswordError(ParseError):
    """The PDF is encrypted and no (or a wrong) password was supplied."""


class NoTextError(ParseError):
    """The PDF has no extractable text layer (e.g. a scanned image)."""
