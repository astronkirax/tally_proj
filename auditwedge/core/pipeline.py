"""One entry point that runs the whole engine: ingest -> classify -> reconcile ->
flag. The UI and tests call :func:`analyze`; exports are generated on demand from the
returned result.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.classify import classify_statement
from core.exceptions import find_exceptions
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


def analyze(statement_source, invoice_source=None, use_llm: bool = False) -> AnalysisResult:
    st = load_statement(statement_source)
    stats = classify_statement(st, use_llm=use_llm)
    recon = reconcile(st)
    flags = find_exceptions(st)
    if invoice_source is not None:
        invoices = load_invoices(invoice_source)
        flags += invoice_period_exceptions(invoices, st.info.from_date, st.info.to_date)
    return AnalysisResult(statement=st, recon=recon, flags=flags, stats=stats)
