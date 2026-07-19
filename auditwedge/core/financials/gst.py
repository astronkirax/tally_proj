"""GST computation + government JSON (GSTR-3B / GSTR-1).

Two treatments (as the auditor's Summary shows):
  * **Cab Services @5%** on gross turnover
  * **Commission @18%** on the commission income

Tax is split CGST+SGST for intra-state supply (default — local cab rides) or IGST for
inter-state. The JSON targets the standard GSTN offline-tool shapes; validate against the
current tool version before filing (GSTR-3B is the primary summary return).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from core.financials.masters import Masters
from core.financials.statements import SummaryReport

Q = Decimal("0.01")


def _f(x: Decimal) -> float:
    return float(Decimal(x).quantize(Q))


@dataclass
class GstScenario:
    label: str
    taxable: Decimal
    rate: Decimal      # e.g. 5 or 18
    igst: Decimal
    cgst: Decimal
    sgst: Decimal

    @property
    def total_tax(self) -> Decimal:
        return (self.igst + self.cgst + self.sgst).quantize(Q)


@dataclass
class GstReturn:
    gstin: str
    state_code: str
    ret_period: str            # MMYYYY of the period end
    intra_state: bool
    cab: GstScenario
    commission: GstScenario
    monthly_cab: list[tuple[str, Decimal]] = field(default_factory=list)  # (month, turnover)


def _split(taxable: Decimal, rate: Decimal, intra: bool) -> GstScenario:
    tax = (taxable * rate / Decimal("100")).quantize(Q)
    if intra:
        half = (tax / 2).quantize(Q)
        return GstScenario("", taxable.quantize(Q), rate, Decimal("0"), half, tax - half)
    return GstScenario("", taxable.quantize(Q), rate, tax, Decimal("0"), Decimal("0"))


def build_gst(summary: SummaryReport, masters: Masters, intra_state: bool = True) -> GstReturn:
    state = (masters.gstin or "37")[:2]
    period = f"{masters.period_to.month:02d}{masters.period_to.year}"
    cab = _split(summary.stmt_turnover, Decimal("5"), intra_state)
    cab.label = "Cab Services @5% on gross turnover"
    comm = _split(summary.commission_base, Decimal("18"), intra_state)
    comm.label = "Commission @18% on commission income"
    return GstReturn(masters.gstin, state, period, intra_state, cab, comm,
                     monthly_cab=list(masters.monthly_turnover))


# --------------------------------------------------------------------------- JSON
def gstr3b_json(gstin: str, ret_period: str, sc: GstScenario) -> dict:
    """GSTR-3B summary JSON (section 3.1 outward taxable supplies)."""
    return {
        "gstin": gstin,
        "ret_period": ret_period,
        "sup_details": {
            "osup_det": {"txval": _f(sc.taxable), "iamt": _f(sc.igst),
                         "camt": _f(sc.cgst), "samt": _f(sc.sgst), "csamt": 0},
            "osup_zero": {"txval": 0, "iamt": 0, "csamt": 0},
            "osup_nil_exmp": {"txval": 0},
            "isup_rev": {"txval": 0, "iamt": 0, "camt": 0, "samt": 0, "csamt": 0},
            "osup_nongst": {"txval": 0},
        },
        "inter_sup": {"unreg_details": [], "comp_details": [], "uin_details": []},
        "itc_elg": {"itc_avl": [], "itc_rev": [], "itc_net": {}, "itc_inelg": []},
        "inward_sup": {"isup_details": []},
        "intr_ltfee": {},
    }


def gstr1_json(gstin: str, ret_period: str, state_code: str, sc: GstScenario) -> dict:
    """Simplified GSTR-1 JSON — B2C (small) + HSN summary for passenger transport (9964)."""
    sply_ty = "INTRA" if sc.igst == 0 else "INTER"
    return {
        "gstin": gstin,
        "fp": ret_period,
        "version": "GST3.0.4",
        "hash": "hash",
        "b2cs": [{
            "sply_ty": sply_ty, "pos": state_code, "typ": "OE",
            "txval": _f(sc.taxable), "rt": float(sc.rate),
            "iamt": _f(sc.igst), "camt": _f(sc.cgst), "samt": _f(sc.sgst), "csamt": 0,
        }],
        "hsn": {"data": [{
            "num": 1, "hsn_sc": "9964", "desc": "Passenger transport services",
            "uqc": "OTH", "qty": 0, "val": _f(sc.taxable + sc.total_tax),
            "txval": _f(sc.taxable), "rt": float(sc.rate),
            "iamt": _f(sc.igst), "camt": _f(sc.cgst), "samt": _f(sc.sgst), "csamt": 0,
        }]},
    }


def gstr3b_bytes(ret: GstReturn, treatment: str = "cab") -> bytes:
    sc = ret.cab if treatment == "cab" else ret.commission
    return json.dumps(gstr3b_json(ret.gstin, ret.ret_period, sc), indent=2).encode("utf-8")


def gstr1_bytes(ret: GstReturn, treatment: str = "cab") -> bytes:
    sc = ret.cab if treatment == "cab" else ret.commission
    return json.dumps(gstr1_json(ret.gstin, ret.ret_period, ret.state_code, sc), indent=2).encode("utf-8")
