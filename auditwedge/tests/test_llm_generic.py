"""Opt-in live LLM tests (they cost API calls, so they're skipped by default).

Run with:  RUN_LLM_TESTS=1 pytest tests/test_llm_generic.py
Proves the generic AI parser reads a statement and still reconciles exactly, because
Dr/Cr is recovered from the balance column rather than trusted from the model.
"""
import os
from decimal import Decimal
from pathlib import Path

import pytest

from core.ingest.generic_llm import GenericLLMAdapter
from core.ingest.pdf import extract_text
from core.llm import llm_available
from core.reconcile import reconcile

FIX = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_TESTS") != "1" or not llm_available(),
    reason="opt-in: set RUN_LLM_TESTS=1 and a DEEPSEEK_API_KEY to run",
)


def test_generic_ai_parser_reconciles_hdfc():
    text = extract_text(str(FIX / "hdfc_sample.pdf"))
    st = GenericLLMAdapter().parse(text)
    assert len(st.transactions) == 131
    assert st.total_debits == Decimal("129593.00")
    assert st.total_credits == Decimal("129564.56")
    rec = reconcile(st)
    assert rec.balance_chains
    assert rec.closing_balance_computed == Decimal("89.02")
