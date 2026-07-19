"""Serialize engine objects into clean JSON for the web frontend (Decimals -> floats)."""
from __future__ import annotations

from decimal import Decimal


def _d(x):
    return float(x) if isinstance(x, Decimal) else x


def _dt(x):
    return x.isoformat() if x is not None else None


def _account(info) -> dict:
    return {
        "bank": info.bank, "account_name": info.account_name, "account_no": info.account_no,
        "ifsc": info.ifsc, "from_date": _dt(info.from_date), "to_date": _dt(info.to_date),
    }


def _recon(r) -> dict:
    return {
        "opening": _d(r.opening_balance), "closing_computed": _d(r.closing_balance_computed),
        "closing_reported": _d(r.closing_balance_reported), "chains": r.balance_chains,
        "drift": _d(r.max_drift), "dr_count": r.dr_count, "cr_count": r.cr_count,
        "total_debits": _d(r.total_debits), "total_credits": _d(r.total_credits),
        "matches_summary": r.matches_statement_summary, "notes": r.notes,
    }


def _txn(t) -> dict:
    debit = _d(t.amount) if t.dr_cr.value == "DR" else None
    credit = _d(t.amount) if t.dr_cr.value == "CR" else None
    return {
        "row": t.row, "date": _dt(t.txn_date), "narration": t.narration, "ref": t.ref_no,
        "debit": debit, "credit": credit, "balance": _d(t.balance), "ledger": t.ledger,
        "counterparty": t.counterparty, "type": t.counterparty_type,
        "confidence": t.confidence, "source": t.source, "bucket": t.bucket,
    }


def _flag(f) -> dict:
    return {"severity": f.severity.value, "code": f.code, "title": f.title, "detail": f.detail,
            "amount": _d(f.amount), "row": f.row, "date": _dt(f.txn_date)}


def _lines(ls) -> list:
    return [{"group": l.group, "ledger": l.ledger, "amount": _d(l.amount)} for l in ls]


def _financials(f) -> dict | None:
    if f is None:
        return None
    s = f.summary
    return {
        "summary": {
            "opening": _d(s.opening), "closing": _d(s.closing),
            "biz_receipts": _d(s.biz_receipts), "sus_receipts": _d(s.sus_receipts),
            "total_receipts": _d(s.total_receipts), "biz_payments": _d(s.biz_payments),
            "sus_payments": _d(s.sus_payments), "total_payments": _d(s.total_payments),
            "charges": _d(s.charges), "gst_turnover": _d(s.gst_turnover),
            "stmt_turnover": _d(s.stmt_turnover), "notes": s.notes,
        },
        "pnl": {"income": _lines(f.pnl.income), "expenses": _lines(f.pnl.expenses),
                "total_income": _d(f.pnl.total_income), "total_expense": _d(f.pnl.total_expense),
                "net_profit": _d(f.pnl.net_profit)},
        "balance_sheet": {
            "liabilities": [{"group": l.group, "ledger": l.ledger, "amount": _d(l.amount)} for l in f.balance_sheet.liabilities],
            "assets": [{"group": l.group, "ledger": l.ledger, "amount": _d(l.amount)} for l in f.balance_sheet.assets],
            "total_liabilities": _d(f.balance_sheet.total_liabilities),
            "total_assets": _d(f.balance_sheet.total_assets), "suspense": _d(f.balance_sheet.suspense),
        },
        "cross_checks": [{"item": c.item, "bank_or_invoice": _d(c.bank_or_invoice),
                          "masters": _d(c.masters), "status": c.status} for c in f.cross_checks],
    }


def _gst(g) -> dict | None:
    if g is None:
        return None

    def sc(x):
        return {"label": x.label, "taxable": _d(x.taxable), "rate": _d(x.rate),
                "igst": _d(x.igst), "cgst": _d(x.cgst), "sgst": _d(x.sgst), "total_tax": _d(x.total_tax)}

    return {"gstin": g.gstin, "state_code": g.state_code, "ret_period": g.ret_period,
            "intra_state": g.intra_state, "cab": sc(g.cab), "commission": sc(g.commission)}


def _itr(it) -> dict | None:
    if it is None:
        return None
    return {"form": it.form, "assessment_year": it.assessment_year, "financial_year": it.financial_year,
            "pl": it.pl, "bs": it.bs, "computation": it.computation}


def serialize_result(res) -> dict:
    return {
        "account": _account(res.statement.info),
        "reconciliation": _recon(res.recon),
        "stats": res.stats,
        "gateway_taxable": _d(res.gateway_taxable),
        "flags": [_flag(f) for f in res.flags],
        "transactions": [_txn(t) for t in res.statement.transactions],
        "financials": _financials(res.financials),
        "gst": _gst(res.gst),
        "itr": _itr(res.itr),
        "has_masters": res.financials is not None,
    }
