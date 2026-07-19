"""One entry point that runs the whole engine: ingest -> classify -> bucket -> reconcile
-> flag -> (optional) financial statements. The UI and tests call :func:`analyze`;
exports are generated on demand from the returned result.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.classify import classify_statement
from core.exceptions import find_exceptions
from core.financials.buckets import tag_buckets
from core.financials.gst import GstReturn, build_gst
from core.financials.itr import ItrReport, build_itr
from core.financials.masters import Masters
from core.financials.statements import Financials, build_financials
from core.ingest.invoices import invoice_period_exceptions, load_invoices
from core.ingest.registry import load_statement
from core.reconcile import reconcile
from core.schema import ExceptionFlag, ReconResult, Statement


@dataclass
class AnalysisResult:
    statement: Statement
    recon: ReconResult
    flags: list[ExceptionFlag]
    stats: dict
    gateway_taxable: Decimal = Decimal("0")
    financials: Financials | None = None  # present only when masters are supplied
    gst: GstReturn | None = None
    itr: ItrReport | None = None


def _gateway_taxable(invoices: list[dict]) -> Decimal:
    return sum((Decimal(str(inv["taxable"])) for inv in invoices
               if isinstance(inv.get("taxable"), (int, float))), Decimal("0"))


def analyze(statement_source, invoice_source=None, use_llm: bool = False,
            password: str | None = None, masters: Masters | None = None) -> AnalysisResult:
    st = load_statement(statement_source, password=password)
    stats = classify_statement(st, use_llm=use_llm)
    tag_buckets(st)  # business/suspense tags for the financials layer
    recon = reconcile(st)
    flags = find_exceptions(st)

    gateway_taxable = Decimal("0")
    if invoice_source is not None:
        invoices = load_invoices(invoice_source)
        flags += invoice_period_exceptions(invoices, st.info.from_date, st.info.to_date)
        gateway_taxable = _gateway_taxable(invoices)

    financials = gst = itr = None
    if masters is not None:
        financials = build_financials(st, masters, gateway_taxable)
        gst = build_gst(financials.summary, masters)
        itr = build_itr(financials.pnl, financials.balance_sheet, masters)
    return AnalysisResult(statement=st, recon=recon, flags=flags, stats=stats,
                          gateway_taxable=gateway_taxable, financials=financials, gst=gst, itr=itr)
