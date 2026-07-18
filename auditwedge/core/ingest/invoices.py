"""Read the purchase-invoice register (Excel) and cross-check it against the
statement period. This is a small taste of the cross-document scrutiny that Phase 2
expands (GSTR-2B / ITC matching).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import openpyxl

from core.schema import ExceptionFlag, Severity

HEADER_KEY = "invoice date"


def _to_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def load_invoices(source) -> list[dict]:
    """Return a list of invoice dicts from the Excel. ``source`` = path / bytes / file-like."""
    if isinstance(source, (bytes, bytearray)):
        source = BytesIO(source)
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # locate the header row (first cell that looks like 'Invoice Date')
    hidx = next(
        (i for i, r in enumerate(rows)
         if r and any(isinstance(c, str) and c.strip().lower() == HEADER_KEY for c in r)),
        None,
    )
    if hidx is None:
        return []
    headers = [str(c).strip() if c is not None else "" for c in rows[hidx]]

    out: list[dict] = []
    for r in rows[hidx + 1:]:
        if not r or r[0] is None:  # stop at the first blank / totals gap
            continue
        rec = dict(zip(headers, r))
        d = _to_date(rec.get("Invoice Date"))
        if d is None:  # totals row or malformed
            continue
        out.append({
            "date": d,
            "number": str(rec.get("Invoice Number", "")).strip().strip("'"),
            "supplier": rec.get("Supplier Legal Name"),
            "gstin": rec.get("Supplier GSTIN"),
            "taxable": rec.get("Item Taxable Value"),
            "igst": rec.get("IGST Amount"),
            "total": rec.get("Total Transaction Value"),
        })
    return out


def invoice_period_exceptions(
    invoices: list[dict], from_date: date | None, to_date: date | None
) -> list[ExceptionFlag]:
    """Flag invoices whose date lies outside the statement's financial year."""
    if not (from_date and to_date):
        return []
    out = [inv for inv in invoices if inv["date"] < from_date or inv["date"] > to_date]
    if not out:
        return []
    total = sum((Decimal(str(inv["total"])) for inv in out
                 if isinstance(inv.get("total"), (int, float))), Decimal("0"))
    dates = sorted(inv["date"] for inv in out)
    numbers = ", ".join(inv["number"] for inv in out[:6]) + ("…" if len(out) > 6 else "")
    return [ExceptionFlag(
        code="INVOICE_WRONG_PERIOD",
        title="Purchase invoices dated outside the statement period",
        severity=Severity.MEDIUM,
        amount=total,
        detail=(f"{len(out)} invoices totalling ₹{total:,.2f} (dated {dates[0]} to {dates[-1]}) fall "
                f"outside the statement period {from_date} to {to_date}. These do not belong to this "
                f"year's books / GST return — confirm before claiming input credit. E.g. {numbers}"),
    )]
