"""Golden test: the HDFC sample must reconcile to the paisa.

This is the engine's safety net. If a future change breaks the running-balance
reconstruction, these exact figures will fail loudly.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from core.ingest.registry import load_statement
from core.schema import DrCr

FIXTURE = Path(__file__).parent / "fixtures" / "hdfc_sample.pdf"

# The fixture is a real bank statement, kept OUT of the public repo. Skip if absent.
pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="real-data fixture not present")

# Figures printed on the statement's own STATEMENT SUMMARY block.
EXPECTED_DR_COUNT = 91
EXPECTED_CR_COUNT = 40
EXPECTED_DEBITS = Decimal("129593.00")
EXPECTED_CREDITS = Decimal("129564.56")
EXPECTED_OPENING = Decimal("117.46")
EXPECTED_CLOSING = Decimal("89.02")


@pytest.fixture(scope="module")
def statement():
    return load_statement(str(FIXTURE))


def test_counts_and_totals_match_printed_summary(statement):
    assert statement.dr_count == EXPECTED_DR_COUNT
    assert statement.cr_count == EXPECTED_CR_COUNT
    assert statement.total_debits == EXPECTED_DEBITS
    assert statement.total_credits == EXPECTED_CREDITS
    assert len(statement.transactions) == EXPECTED_DR_COUNT + EXPECTED_CR_COUNT


def test_balance_chains_from_opening_to_closing(statement):
    """Every running balance must equal prev ± amount, ending at the printed close."""
    prev = statement.info.opening_balance
    assert prev == EXPECTED_OPENING
    for t in statement.transactions:
        expected = prev - t.amount if t.dr_cr is DrCr.DEBIT else prev + t.amount
        assert t.balance == expected, f"balance chain broke at row {t.row}"
        prev = t.balance
    assert prev == EXPECTED_CLOSING
    assert statement.transactions[-1].balance == statement.info.closing_balance


def test_header_metadata(statement):
    info = statement.info
    assert info.bank == "HDFC"
    assert info.account_no == "50200057575144"
    assert info.ifsc == "HDFC0002388"
    assert info.account_name and "GATEWAY2KONASEEMA" in info.account_name


def test_transactions_have_dates_and_amounts(statement):
    for t in statement.transactions:
        assert t.txn_date is not None
        assert t.amount > 0
        assert t.narration  # non-empty
