"""Canonical data models for AuditWedge.

Framework-independent: no Streamlit / DB / Anthropic imports here. Everything the
engine produces and consumes flows through these pydantic models, so the UI (Streamlit
now, a web frontend later) and the persistence layer are just thin adapters on top.

Money is represented with :class:`decimal.Decimal` — never float — because this is
audit software and paise must chain exactly.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

TWO_DP = Decimal("0.01")


class DrCr(str, Enum):
    DEBIT = "DR"
    CREDIT = "CR"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Transaction(BaseModel):
    """One line of a bank statement, normalised to a canonical shape."""

    row: int  # 1-based sequence within the statement
    txn_date: date
    value_date: date | None = None
    narration: str
    ref_no: str | None = None  # Chq./Ref.No — usually the UTR
    amount: Decimal
    dr_cr: DrCr
    balance: Decimal  # closing balance *after* this transaction

    # --- filled in by the classification step ---
    ledger: str | None = None
    counterparty: str | None = None
    counterparty_type: str | None = None  # aggregator|corporate|individual|bank|govt|telecom|self|unknown
    category: str | None = None
    confidence: float = 0.0
    source: str | None = None  # 'rule' | 'llm' | 'unclassified'
    bucket: str | None = None  # 'business' | 'suspense' | 'reversal' | 'charge' (financials tagging)

    @property
    def signed_amount(self) -> Decimal:
        """+amount for credits, -amount for debits."""
        return self.amount if self.dr_cr is DrCr.CREDIT else -self.amount


class AccountInfo(BaseModel):
    """Statement header / account metadata."""

    bank: str = "UNKNOWN"
    account_name: str | None = None
    account_no: str | None = None
    ifsc: str | None = None
    from_date: date | None = None
    to_date: date | None = None

    # Summary block as *printed* on the statement (used to cross-check our parse).
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    stmt_dr_count: int | None = None
    stmt_cr_count: int | None = None
    stmt_total_debits: Decimal | None = None
    stmt_total_credits: Decimal | None = None


class Statement(BaseModel):
    info: AccountInfo
    transactions: list[Transaction] = Field(default_factory=list)

    @property
    def total_debits(self) -> Decimal:
        return sum((t.amount for t in self.transactions if t.dr_cr is DrCr.DEBIT), Decimal("0"))

    @property
    def total_credits(self) -> Decimal:
        return sum((t.amount for t in self.transactions if t.dr_cr is DrCr.CREDIT), Decimal("0"))

    @property
    def dr_count(self) -> int:
        return sum(1 for t in self.transactions if t.dr_cr is DrCr.DEBIT)

    @property
    def cr_count(self) -> int:
        return sum(1 for t in self.transactions if t.dr_cr is DrCr.CREDIT)


class ExceptionFlag(BaseModel):
    """One audit red-flag raised by the exception engine."""

    code: str  # machine code, e.g. 'LOW_BALANCE'
    title: str  # human title
    severity: Severity
    detail: str
    row: int | None = None  # linked transaction row, when applicable
    txn_date: date | None = None
    amount: Decimal | None = None


class ReconResult(BaseModel):
    """Output of the reconciliation / balance-integrity check."""

    opening_balance: Decimal
    closing_balance_computed: Decimal
    closing_balance_reported: Decimal | None = None
    balance_chains: bool  # did every running balance chain cleanly?
    max_drift: Decimal  # largest abs mismatch found while chaining
    dr_count: int
    cr_count: int
    total_debits: Decimal
    total_credits: Decimal
    matches_statement_summary: bool | None = None
    notes: list[str] = Field(default_factory=list)
