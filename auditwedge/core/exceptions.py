"""Audit exception engine — the red flags an auditor would hand-hunt for.

Each rule turns a pattern in the transactions into one or more :class:`ExceptionFlag`s,
ranked by severity. This is the wedge's core value: it *performs* the scrutiny rather
than just organising a workflow. Everything here is deterministic and explainable.

Thresholds are parameters so a firm can tune them per engagement.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from core.schema import DrCr, ExceptionFlag, Severity, Statement

# tuneable thresholds
NEAR_ZERO = Decimal("100")
ADVANCE_MIN = Decimal("1000")
LARGE_INDIVIDUAL = Decimal("5000")
CONCENTRATION_MIN = 4  # a single individual payee appearing this many times


def _norm(name: str | None) -> str:
    return (name or "").strip().upper()


def find_exceptions(statement: Statement) -> list[ExceptionFlag]:
    txns = statement.transactions
    flags: list[ExceptionFlag] = []

    # 1) Sustained near-zero balance (account behaves like a pass-through).
    nz = [t for t in txns if t.balance < NEAR_ZERO]
    if nz:
        sev = Severity.HIGH if len(nz) >= 10 else Severity.MEDIUM if len(nz) >= 3 else Severity.LOW
        lowest = min(t.balance for t in nz)
        flags.append(ExceptionFlag(
            code="NEAR_ZERO_BALANCE", title="Account runs at near-zero balance", severity=sev,
            detail=(f"Closing balance fell below ₹{NEAR_ZERO} on {len(nz)} occasions "
                    f"(lowest ₹{lowest}). A current account held near ₹0 all year can indicate "
                    f"funds routed through other accounts or acute cash-flow stress — corroborate "
                    f"with the cash book and any other bank accounts."),
        ))

    # 2) Unclassified / suspense items must be coded before finalisation.
    susp = [t for t in txns if t.source == "unclassified" or t.confidence <= 0.5]
    if susp:
        total = sum((t.amount for t in susp), Decimal("0"))
        flags.append(ExceptionFlag(
            code="UNCLASSIFIED", title="Transactions need manual coding", severity=Severity.MEDIUM,
            detail=(f"{len(susp)} transactions totalling ₹{total:,.2f} could not be auto-classified "
                    f"with confidence and are parked in suspense. Assign correct ledgers before "
                    f"finalising — misclassification affects both the P&L and GST/TDS."),
        ))

    # 3) Unvouched advances to individuals (classic driver-advance exposure) — aggregated.
    adv = [t for t in txns
           if t.dr_cr is DrCr.DEBIT and "ADVANCE" in t.narration.upper() and t.amount >= ADVANCE_MIN]
    if adv:
        total = sum((t.amount for t in adv), Decimal("0"))
        flags.append(ExceptionFlag(
            code="ADVANCE_UNVOUCHED", title="Unvouched advances to individuals",
            severity=Severity.MEDIUM, amount=total,
            detail=(f"{len(adv)} advance-type payments totalling ₹{total:,.2f} made to individuals. "
                    f"Obtain supporting bills and confirm each is an expense or a recoverable "
                    f"(asset); check TDS applicability u/s 194C."),
        ))

    # 4) Large payments / receipts with individuals (non-advance).
    for t in txns:
        if t.counterparty_type != "individual" or t.amount < LARGE_INDIVIDUAL:
            continue
        if t.dr_cr is DrCr.DEBIT and "ADVANCE" not in t.narration.upper():
            flags.append(ExceptionFlag(
                code="LARGE_INDIVIDUAL_PAYMENT", title="Large payment to individual",
                severity=Severity.MEDIUM, row=t.row, txn_date=t.txn_date, amount=t.amount,
                detail=(f"₹{t.amount:,.2f} paid to {t.counterparty or 'an individual'} on "
                        f"{t.txn_date}. Verify nature and supporting documentation."),
            ))
        elif t.dr_cr is DrCr.CREDIT and t.confidence <= 0.5:
            flags.append(ExceptionFlag(
                code="UNEXPLAINED_RECEIPT", title="Unexplained receipt from individual",
                severity=Severity.MEDIUM, row=t.row, txn_date=t.txn_date, amount=t.amount,
                detail=(f"₹{t.amount:,.2f} received from {t.counterparty or 'an individual'} on "
                        f"{t.txn_date}. Confirm whether it is sales income, a loan, or capital "
                        f"introduced — the tax treatment of each is different."),
            ))

    # 5) Possible duplicate payments (same payee + same amount). Bank charges recur
    #    legitimately, so exclude them and trivial amounts to avoid noise.
    groups: dict[tuple[str, Decimal], list] = defaultdict(list)
    for t in txns:
        if (t.dr_cr is DrCr.DEBIT and t.counterparty and t.counterparty_type != "bank"
                and t.amount >= ADVANCE_MIN):
            groups[(_norm(t.counterparty), t.amount)].append(t)
    for (name, amt), grp in groups.items():
        if len(grp) >= 2:
            dates = ", ".join(str(t.txn_date) for t in grp)
            flags.append(ExceptionFlag(
                code="POSSIBLE_DUPLICATE", title="Possible duplicate payment", severity=Severity.LOW,
                amount=amt,
                detail=(f"₹{amt:,.2f} paid to {grp[0].counterparty} on {len(grp)} occasions "
                        f"({dates}). Confirm these are distinct genuine payments, not duplicates."),
            ))

    # 6) Payee concentration (one individual receiving many payments).
    counts: dict[str, list] = defaultdict(list)
    for t in txns:
        if t.dr_cr is DrCr.DEBIT and t.counterparty_type == "individual" and t.counterparty:
            counts[_norm(t.counterparty)].append(t)
    for name, grp in counts.items():
        if len(grp) >= CONCENTRATION_MIN:
            total = sum((t.amount for t in grp), Decimal("0"))
            flags.append(ExceptionFlag(
                code="PAYEE_CONCENTRATION", title="Recurring payments to one individual",
                severity=Severity.LOW, amount=total,
                detail=(f"{grp[0].counterparty} received {len(grp)} payments totalling "
                        f"₹{total:,.2f}. Consider related-party disclosure and TDS aggregation."),
            ))

    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    flags.sort(key=lambda f: (order[f.severity], -(f.amount or Decimal("0"))))
    return flags
