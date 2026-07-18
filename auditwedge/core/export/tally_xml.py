"""Generate Tally-importable voucher XML from a classified statement.

Each bank line becomes a voucher the CA can import into TallyPrime:
  * money OUT of bank  -> Payment voucher: Dr <expense/party>, Cr Bank
  * money IN to bank   -> Receipt voucher: Dr Bank, Cr <income/party>

Tally sign convention: the debit leg carries a NEGATIVE <AMOUNT> with
<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>; the credit leg is POSITIVE with No.
Ledger names come from the classifier — the CA can remap on import.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from core.schema import DrCr, Statement


def _entry(name: str, deemed_positive: bool, amount: str) -> str:
    return (
        "<ALLLEDGERENTRIES.LIST>"
        f"<LEDGERNAME>{escape(name)}</LEDGERNAME>"
        f"<ISDEEMEDPOSITIVE>{'Yes' if deemed_positive else 'No'}</ISDEEMEDPOSITIVE>"
        f"<AMOUNT>{amount}</AMOUNT>"
        "</ALLLEDGERENTRIES.LIST>"
    )


def build_tally_xml(st: Statement, bank_ledger: str | None = None, company: str | None = None) -> bytes:
    info = st.info
    bank_ledger = bank_ledger or f"{info.bank} Bank"
    company = company or (info.account_name or "")

    vouchers: list[str] = []
    for t in st.transactions:
        d = t.txn_date.strftime("%Y%m%d")
        amt = f"{t.amount:.2f}"
        neg = f"{-t.amount:.2f}"
        narration = escape(t.narration)
        if t.dr_cr is DrCr.DEBIT:  # money out -> Payment
            vtype = "Payment"
            legs = _entry(t.ledger, True, neg) + _entry(bank_ledger, False, amt)
        else:  # money in -> Receipt
            vtype = "Receipt"
            legs = _entry(bank_ledger, True, neg) + _entry(t.ledger, False, amt)
        vouchers.append(
            f'<VOUCHER VCHTYPE="{vtype}" ACTION="Create" OBJVIEW="Accounting Voucher View">'
            f"<DATE>{d}</DATE><EFFECTIVEDATE>{d}</EFFECTIVEDATE>"
            f"<VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>"
            f"<NARRATION>{narration}</NARRATION>"
            f"{legs}</VOUCHER>"
        )

    messages = "".join(f'<TALLYMESSAGE xmlns:UDF="TallyUDF">{v}</TALLYMESSAGE>' for v in vouchers)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>"
        "<BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME>"
        f"<STATICVARIABLES><SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES>"
        "</REQUESTDESC><REQUESTDATA>"
        f"{messages}"
        "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"
    )
    return xml.encode("utf-8")
