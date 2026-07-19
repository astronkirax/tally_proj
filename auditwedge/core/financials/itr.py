"""ITR figures + JSON scaffold.

Maps the P&L and Balance Sheet to the ITR schedule line-items the CA enters (Part A-P&L,
Part A-BS, and a Part B income/tax computation), and emits a JSON scaffold in the ITR
structure for the client's form (ITR-4/5/6 — from masters).

Honest scope (as planned): the full ITR JSON is AY-versioned and has hundreds of mandatory
nodes per form. This produces the **core schedules** correctly populated for the target AY;
the CA imports it and completes the remaining fields in the income-tax utility. Validate
against the utility for the specific AY/form before filing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from core.financials.masters import Masters
from core.financials.statements import BalanceSheet, PnL

Q = Decimal("0.01")


def _f(x) -> float:
    return float(Decimal(x).quantize(Q))


def _round10(x: Decimal) -> int:
    """Total income is rounded to the nearest ₹10 (s.288A)."""
    return int((x / 10).to_integral_value(rounding="ROUND_HALF_UP") * 10)


@dataclass
class ItrReport:
    form: str            # ITR-4 | ITR-5 | ITR-6
    assessment_year: str  # e.g. 2023-24
    financial_year: str   # e.g. 2022-23
    pl: dict = field(default_factory=dict)
    bs: dict = field(default_factory=dict)
    computation: dict = field(default_factory=dict)


def build_itr(pnl: PnL, bs: BalanceSheet, masters: Masters) -> ItrReport:
    end = masters.period_to
    ay = f"{end.year}-{str(end.year + 1)[2:]}"
    fy = f"{end.year - 1}-{str(end.year)[2:]}"

    sales = sum((l.amount for l in pnl.income if l.group in ("Sales Accounts", "Direct Incomes")), Decimal("0"))
    other_income = sum((l.amount for l in pnl.income if l.group == "Indirect Incomes"), Decimal("0"))

    pl = {
        "revenue_from_operations": _f(sales),
        "other_income": _f(other_income),
        "total_revenue": _f(pnl.total_income),
        "total_expenses": _f(pnl.total_expense),
        "net_profit_before_tax": _f(pnl.net_profit),
    }

    def grp(lines, name):
        return sum((l.amount for l in lines if l.group == name), Decimal("0"))

    bs_d = {
        "capital_account": _f(grp(bs.liabilities, "Capital Account")),
        "profit_and_loss": _f(grp(bs.liabilities, "Profit & Loss A/c")),
        "current_liabilities": _f(grp(bs.liabilities, "Current Liabilities")),
        "total_liabilities": _f(bs.total_liabilities),
        "fixed_assets": _f(grp(bs.assets, "Fixed Assets")),
        "current_assets": _f(grp(bs.assets, "Current Assets")),
        "total_assets": _f(bs.total_assets),
    }

    # basic computation (CA finalises surcharge/MAT/AMT etc.)
    business_income = pnl.net_profit
    total_income = _round10(max(business_income, Decimal("0")))
    rate = Decimal("0.25") if masters.itr_form == "ITR-6" else Decimal("0.30")  # firm/company
    tax = (Decimal(total_income) * rate).quantize(Q)
    cess = (tax * Decimal("0.04")).quantize(Q)
    computation = {
        "profits_and_gains_of_business": _f(business_income),
        "gross_total_income": total_income,
        "total_income": total_income,
        "tax_rate": float(rate * 100),
        "tax_on_total_income": _f(tax),
        "health_education_cess_4pct": _f(cess),
        "total_tax_liability": _f(tax + cess),
        "note": "Basic computation — surcharge / MAT-AMT / TDS credit to be finalised by the CA.",
    }
    return ItrReport(masters.itr_form, ay, fy, pl, bs_d, computation)


def itr_json(report: ItrReport) -> dict:
    """A JSON scaffold in the ITR structure carrying the core schedules."""
    key = report.form.replace("-", "").upper()  # ITR5
    return {
        "ITR": {
            key: {
                "CreationInfo": {"SWVersionNo": "1.0", "SWCreatedBy": "AuditWedge",
                                 "JSONCreatedBy": "AuditWedge", "IntermediaryCity": "Kakinada"},
                "Form_" + key: {"FormName": key, "AssessmentYear": report.assessment_year.replace("-", ""),
                                "SchemaVer": "Ver1.0"},
                "PARTA_PL": report.pl,
                "PARTA_BS": report.bs,
                "PARTB_TI": {"TotalIncome": report.computation["total_income"],
                             "GrossTotalIncome": report.computation["gross_total_income"]},
                "PARTB_TTI": {"TaxOnTotalIncome": report.computation["tax_on_total_income"],
                              "EducationCess": report.computation["health_education_cess_4pct"],
                              "TotalTaxLiability": report.computation["total_tax_liability"]},
                "_note": "Core schedules only — complete remaining mandatory fields in the ITR utility.",
            }
        }
    }


def itr_bytes(report: ItrReport) -> bytes:
    return json.dumps(itr_json(report), indent=2).encode("utf-8")
