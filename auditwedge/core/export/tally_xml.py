"""Generate Tally-importable XML from a classified statement (+ optional invoices).

The file contains, in order:
  1. **Ledger masters** for every ledger used, each under a default Tally group — so the
     import never fails with "ledger does not exist".
  2. **Purchase vouchers** for the purchase invoices (Dr expense + Dr Input IGST, Cr party).
  3. **Receipt / Payment vouchers** for the bank lines:
       money OUT -> Payment (Dr expense/party, Cr Bank)
       money IN  -> Receipt (Dr Bank, Cr income/party)

Tally sign convention: the debit leg is a NEGATIVE <AMOUNT> with ISDEEMEDPOSITIVE=Yes;
the credit leg is POSITIVE with No.
"""
from __future__ import annotations

from decimal import Decimal
from xml.sax.saxutils import escape

from core.schema import DrCr, Statement

# AuditWedge ledger -> a Tally DEFAULT group (these exist in every Tally company).
LEDGER_GROUP = {
    "Bank Charges": "Indirect Expenses",
    "Cab Service Income": "Sales Accounts",
    "Corporate Cab Hire Income": "Sales Accounts",
    "Software & Hosting": "Indirect Expenses",
    "Telephone & Internet": "Indirect Expenses",
    "Electricity Charges": "Indirect Expenses",
    "Fuel & Petrol": "Direct Expenses",
    "FASTag & Toll": "Direct Expenses",
    "Driver Advances": "Loans & Advances (Asset)",
    "Vehicle Hire / Taxi": "Direct Expenses",
    "UPI / Bank Receipts": "Sundry Debtors",
    "UPI / Bank Payments": "Sundry Creditors",
    "Suspense - Receipts": "Suspense A/c",
    "Suspense - Payments": "Suspense A/c",
    "Gateway Charges": "Indirect Expenses",
    "Input IGST": "Duties & Taxes",
}


def _entry(name: str, deemed_positive: bool, amount: str) -> str:
    return (
        "<ALLLEDGERENTRIES.LIST>"
        f"<LEDGERNAME>{escape(name)}</LEDGERNAME>"
        f"<ISDEEMEDPOSITIVE>{'Yes' if deemed_positive else 'No'}</ISDEEMEDPOSITIVE>"
        f"<AMOUNT>{amount}</AMOUNT>"
        "</ALLLEDGERENTRIES.LIST>"
    )


def _ledger_master(name: str, group: str) -> str:
    return (
        f'<LEDGER NAME="{escape(name)}" ACTION="Create">'
        f"<NAME>{escape(name)}</NAME><PARENT>{escape(group)}</PARENT>"
        "<ISBILLWISEON>No</ISBILLWISEON>"
        "</LEDGER>"
    )


def _voucher(vtype: str, date: str, narration: str, legs: str) -> str:
    return (
        f'<VOUCHER VCHTYPE="{vtype}" ACTION="Create" OBJVIEW="Accounting Voucher View">'
        f"<DATE>{date}</DATE><EFFECTIVEDATE>{date}</EFFECTIVEDATE>"
        f"<VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>"
        f"<NARRATION>{escape(narration)}</NARRATION>"
        f"{legs}</VOUCHER>"
    )


def build_tally_xml(st: Statement, invoices: list[dict] | None = None,
                    bank_ledger: str | None = None, company: str | None = None,
                    include_masters: bool = True) -> bytes:
    info = st.info
    bank_ledger = bank_ledger or f"{info.bank} Bank"
    company = company or (info.account_name or "")
    invoices = invoices or []

    ledgers: dict[str, str] = {bank_ledger: "Bank Accounts"}
    messages: list[str] = []

    # --- purchase vouchers (invoices) ---
    for inv in invoices:
        try:
            taxable = Decimal(str(inv["taxable"]))
            igst = Decimal(str(inv["igst"] or 0))
            total = Decimal(str(inv["total"] or (taxable + igst)))
        except (TypeError, ValueError):
            continue
        supplier = str(inv.get("supplier") or "Sundry Creditor").strip()
        ledgers.setdefault("Gateway Charges", "Indirect Expenses")
        ledgers.setdefault("Input IGST", "Duties & Taxes")
        ledgers.setdefault(supplier, "Sundry Creditors")
        d = inv["date"].strftime("%Y%m%d")
        legs = (_entry("Gateway Charges", True, f"{-taxable:.2f}")
                + _entry("Input IGST", True, f"{-igst:.2f}")
                + _entry(supplier, False, f"{total:.2f}"))
        messages.append(_voucher("Purchase", d, f"Being purchase invoice {inv.get('number','')} - {supplier}", legs))

    # --- receipt / payment vouchers (bank) ---
    for t in st.transactions:
        ledgers.setdefault(t.ledger, LEDGER_GROUP.get(t.ledger, "Suspense A/c"))
        d = t.txn_date.strftime("%Y%m%d")
        amt = f"{t.amount:.2f}"
        neg = f"{-t.amount:.2f}"
        if t.dr_cr is DrCr.DEBIT:
            legs = _entry(t.ledger, True, neg) + _entry(bank_ledger, False, amt)
            messages.append(_voucher("Payment", d, t.narration, legs))
        else:
            legs = _entry(bank_ledger, True, neg) + _entry(t.ledger, False, amt)
            messages.append(_voucher("Receipt", d, t.narration, legs))

    # --- ledger masters first so vouchers never reference a missing ledger ---
    master_msgs = [_ledger_master(n, g) for n, g in ledgers.items()] if include_masters else []

    body = "".join(f'<TALLYMESSAGE xmlns:UDF="TallyUDF">{m}</TALLYMESSAGE>'
                   for m in master_msgs + messages)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>"
        "<BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>All Masters</REPORTNAME>"
        f"<STATICVARIABLES><SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES>"
        "</REQUESTDESC><REQUESTDATA>"
        f"{body}"
        "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"
    )
    return xml.encode("utf-8")
