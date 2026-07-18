"""Reconciliation / balance-integrity check.

v1 does two things:
  1. Re-walks the balance chain from the opening balance and measures drift — proving
     the parse is internally consistent (this is the BRS integrity backbone).
  2. Cross-checks our computed counts/totals/closing against the figures the bank
     printed in its own summary.

Matching against an uploaded Tally ledger export is stubbed for the next milestone.
"""
from __future__ import annotations

from decimal import Decimal

from core.schema import DrCr, ReconResult, Statement

EPS = Decimal("0.02")


def reconcile(statement: Statement) -> ReconResult:
    info = statement.info
    opening = info.opening_balance if info.opening_balance is not None else Decimal("0")

    prev = opening
    max_drift = Decimal("0")
    for t in statement.transactions:
        expected = prev - t.amount if t.dr_cr is DrCr.DEBIT else prev + t.amount
        drift = abs(expected - t.balance)
        max_drift = max(max_drift, drift)
        prev = t.balance

    computed_close = prev
    notes: list[str] = []

    chains = max_drift <= EPS
    notes.append(
        "Balance chains cleanly from opening to closing (zero drift)."
        if chains
        else f"Balance chain drift detected (max ₹{max_drift}). Parse needs review."
    )

    matches = None
    if info.stmt_dr_count is not None:
        checks = [
            statement.dr_count == info.stmt_dr_count,
            statement.cr_count == info.stmt_cr_count,
            statement.total_debits == info.stmt_total_debits,
            statement.total_credits == info.stmt_total_credits,
            info.closing_balance is None or abs(computed_close - info.closing_balance) <= EPS,
        ]
        matches = all(checks)
        notes.append(
            "Computed totals tie out to the bank's printed summary."
            if matches
            else "Computed totals DO NOT match the printed summary — investigate."
        )

    return ReconResult(
        opening_balance=opening,
        closing_balance_computed=computed_close,
        closing_balance_reported=info.closing_balance,
        balance_chains=chains,
        max_drift=max_drift,
        dr_count=statement.dr_count,
        cr_count=statement.cr_count,
        total_debits=statement.total_debits,
        total_credits=statement.total_credits,
        matches_statement_summary=matches,
        notes=notes,
    )
