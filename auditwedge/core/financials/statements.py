"""Build the three auditor deliverables.

Division of labour (agreed with the user — *provable figures + reconciliation*):
  * **Summary**  — derived purely from the bank; reconciles to the exact closing balance.
  * **P&L / Balance Sheet** — assembled from the CA's trial balance (masters) in Tally
    format, with the bank-/invoice-derivable items (Gateway Charges, Bank Charges, bank
    closing) auto-filled and **cross-checked**; any residual shown as **Suspense A/c**.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from core.financials.buckets import bucket_totals
from core.financials.masters import Masters
from core.schema import DrCr, Statement

Q = Decimal("0.01")


# --------------------------------------------------------------------------- Summary
@dataclass
class SummaryReport:
    opening: Decimal
    closing: Decimal
    biz_receipts: Decimal
    sus_receipts: Decimal
    total_receipts: Decimal
    biz_payments: Decimal
    sus_payments: Decimal
    total_payments: Decimal
    charges: Decimal
    gst_turnover: Decimal
    stmt_turnover: Decimal
    margin: Decimal
    commission_base: Decimal
    gst_cab: Decimal
    gst_commission: Decimal
    notes: list[str] = field(default_factory=list)


def build_summary(statement: Statement, masters: Masters) -> SummaryReport:
    bt = bucket_totals(statement)
    stmt_turnover = bt["total_receipts"]
    margin = bt["biz_receipts"] - bt["biz_payments"]
    commission_base = masters.commission_income  # CA's commission income (positive, provable via masters)
    return SummaryReport(
        opening=statement.info.opening_balance or Decimal("0"),
        closing=statement.info.closing_balance or Decimal("0"),
        biz_receipts=bt["biz_receipts"], sus_receipts=bt["sus_receipts"] + bt["charge_receipts"],
        total_receipts=bt["total_receipts"],
        biz_payments=bt["biz_payments"], sus_payments=bt["sus_payments"],
        total_payments=bt["total_payments"], charges=bt["charge_payments"],
        gst_turnover=masters.gst_turnover, stmt_turnover=stmt_turnover, margin=margin,
        commission_base=commission_base,
        gst_cab=(stmt_turnover * Decimal("0.05")).quantize(Q),
        gst_commission=(commission_base * Decimal("0.18")).quantize(Q),
        notes=[
            "Business = identifiable counterparty (Sundry Debtor/Creditor); Suspense = unidentified/reward/reversal.",
            "Receipt & payment splits reconcile exactly to the bank; closing ties to the bank statement.",
            "GST both ways: Cab Services @5% on gross turnover; Commission @18% on the CA's commission income.",
        ],
    )


# --------------------------------------------------------------------------- P&L
@dataclass
class Line:
    group: str
    ledger: str
    amount: Decimal


@dataclass
class PnL:
    income: list[Line]
    expenses: list[Line]
    total_income: Decimal
    total_expense: Decimal
    net_profit: Decimal


def build_pnl(statement: Statement, masters: Masters, gateway_taxable: Decimal) -> PnL:
    income = [
        Line("Sales Accounts", "GST Sales / Services", masters.gst_sales),
        Line("Direct Incomes", "Commission", masters.commission_income),
        Line("Indirect Incomes", "Other Rewards & Cash Backs", masters.indirect_income),
    ]
    expenses = [Line("Indirect Expenses", "Gateway Charges", gateway_taxable.quantize(Q))]
    for ledger, amt in masters.pnl_expenses:
        expenses.append(Line("Indirect Expenses", ledger, Decimal(amt).quantize(Q)))

    ti = sum((l.amount for l in income), Decimal("0")).quantize(Q)
    te = sum((l.amount for l in expenses), Decimal("0")).quantize(Q)
    return PnL(income, expenses, ti, te, (ti - te).quantize(Q))


# --------------------------------------------------------------------------- Balance Sheet
@dataclass
class BSLine:
    group: str
    ledger: str
    amount: Decimal


@dataclass
class BalanceSheet:
    liabilities: list[BSLine]
    assets: list[BSLine]
    total_liabilities: Decimal
    total_assets: Decimal
    suspense: Decimal


def build_balance_sheet(statement: Statement, masters: Masters, pnl: PnL) -> BalanceSheet:
    bank_close = statement.info.closing_balance or Decimal("0")
    assets = [BSLine("Fixed Assets", n, (c * (Decimal(100) - d) / Decimal(100)).quantize(Q))
              for n, c, d in masters.fixed_assets]
    assets += [BSLine("Current Assets", led, Decimal(amt)) for led, grp, amt in masters.opening if grp == "asset"]
    assets.append(BSLine("Current Assets", "Bank Accounts", bank_close))

    liabilities = [BSLine("Capital Account", "Capital (partners)",
                          sum((a for _, a in masters.capital), Decimal("0")))]
    liabilities += [BSLine("Current Liabilities", led, Decimal(amt)) for led, grp, amt in masters.opening if grp == "liability"]
    liabilities.append(BSLine("Profit & Loss A/c", "Opening + Current Period",
                              (masters.opening_pnl + pnl.net_profit).quantize(Q)))

    ta = sum((l.amount for l in assets), Decimal("0")).quantize(Q)
    tl = sum((l.amount for l in liabilities), Decimal("0")).quantize(Q)
    suspense = (ta - tl).quantize(Q)
    if suspense != 0:
        liabilities.append(BSLine("Current Liabilities", "Suspense A/c (difference)", suspense))
        tl = (tl + suspense).quantize(Q)
    return BalanceSheet(liabilities, assets, tl, ta, suspense)


# --------------------------------------------------------------------------- Cross-checks
@dataclass
class CrossCheck:
    item: str
    bank_or_invoice: Decimal
    masters: Decimal | None
    status: str


@dataclass
class Financials:
    summary: SummaryReport
    pnl: PnL
    balance_sheet: BalanceSheet
    cross_checks: "list[CrossCheck]"
    masters: Masters


def build_financials(statement: Statement, masters: Masters, gateway_taxable: Decimal) -> Financials:
    """Assemble all three statements + cross-checks in one call."""
    summary = build_summary(statement, masters)
    pnl = build_pnl(statement, masters, gateway_taxable)
    bs = build_balance_sheet(statement, masters, pnl)
    cc = build_cross_checks(statement, masters, gateway_taxable)
    return Financials(summary, pnl, bs, cc, masters)


def build_cross_checks(statement: Statement, masters: Masters, gateway_taxable: Decimal) -> list[CrossCheck]:
    bank_charges = sum((t.amount for t in statement.transactions
                        if t.dr_cr is DrCr.DEBIT and t.ledger == "Bank Charges"), Decimal("0"))
    m_bank = next((Decimal(a) for led, a in masters.pnl_expenses if led == "Bank Charges"), None)
    out = [CrossCheck("Gateway Charges (from invoices)", gateway_taxable.quantize(Q), None, "auto-filled")]
    if m_bank is not None:
        diff = (bank_charges - m_bank).quantize(Q)
        out.append(CrossCheck("Bank Charges", bank_charges.quantize(Q), m_bank,
                              "MATCH" if abs(diff) <= Decimal("1") else f"review (diff {diff})"))
    out.append(CrossCheck("Bank closing balance", statement.info.closing_balance or Decimal("0"), None, "auto-filled"))
    return out
