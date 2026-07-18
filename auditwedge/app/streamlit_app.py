"""AuditWedge — MVP web UI (Streamlit).

Thin presentation layer over the engine in ``core``. When the wedge is validated this
gets replaced by a proper web frontend; the engine below it does not change.

Run:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import pathlib
import sys

# make the package importable when Streamlit runs this file directly
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from core.export.tally_xml import build_tally_xml  # noqa: E402
from core.export.workpaper import build_workpaper  # noqa: E402
from core.ingest.registry import ADAPTERS  # noqa: E402
from core.llm import llm_available  # noqa: E402
from core.pipeline import analyze  # noqa: E402
from core.schema import DrCr  # noqa: E402

NATIVE_BANKS = {a.bank_name for a in ADAPTERS}

load_dotenv()

st.set_page_config(page_title="AuditWedge", page_icon="🧾", layout="wide")

SEV_UI = {"high": st.error, "medium": st.warning, "low": st.info}


@st.cache_data(show_spinner=False)
def run_analysis(pdf_bytes: bytes, xlsx_bytes: bytes | None, use_llm: bool):
    return analyze(pdf_bytes, xlsx_bytes, use_llm=use_llm)


def txn_dataframe(statement) -> pd.DataFrame:
    rows = [{
        "#": t.row,
        "Date": t.txn_date.isoformat(),
        "Narration": t.narration,
        "Ref / UTR": t.ref_no or "",
        "Debit": float(t.amount) if t.dr_cr is DrCr.DEBIT else None,
        "Credit": float(t.amount) if t.dr_cr is DrCr.CREDIT else None,
        "Balance": float(t.balance),
        "Ledger": t.ledger,
        "Counterparty": t.counterparty or "",
        "Type": t.counterparty_type or "",
        "Conf.": round(t.confidence, 2),
        "Source": t.source,
    } for t in statement.transactions]
    return pd.DataFrame(rows)


def ledger_dataframe(statement) -> pd.DataFrame:
    agg: dict = {}
    for t in statement.transactions:
        a = agg.setdefault(t.ledger, {"Category": t.category, "# Txns": 0, "Debit": 0.0, "Credit": 0.0})
        a["# Txns"] += 1
        a["Debit" if t.dr_cr is DrCr.DEBIT else "Credit"] += float(t.amount)
    df = pd.DataFrame([{"Ledger": k, **v} for k, v in agg.items()])
    return df.sort_values(by=["Debit", "Credit"], ascending=False, ignore_index=True)


# ---- header ----------------------------------------------------------------
st.title("🧾 AuditWedge")
st.caption("Upload a bank statement → auto reconciliation + auditor red-flags + a Tally-ready working paper.")

with st.sidebar:
    st.header("Inputs")
    pdf = st.file_uploader("Bank statement (PDF)", type=["pdf"])
    xlsx = st.file_uploader("Purchase invoices (Excel, optional)", type=["xlsx"])
    have_key = llm_available()
    use_llm = st.toggle(
        "Use AI (DeepSeek) for ambiguous rows",
        value=have_key,
        disabled=not have_key,
        help="Optional. Sends only the low-confidence narrations to DeepSeek. Requires DEEPSEEK_API_KEY in .env.",
    )
    if not have_key:
        st.caption("💡 AI off (no DEEPSEEK_API_KEY set). Rules still classify most rows, and only HDFC PDFs can be read.")
    st.divider()
    if have_key:
        st.caption("Banks: **HDFC** instant native parser · **any other bank** via the AI parser.")
    else:
        st.caption("Banks: **HDFC** (set DEEPSEEK_API_KEY to read other banks via AI).")

if pdf is None:
    st.info("👈 Upload a bank statement PDF to begin. Digital PDFs (net-banking downloads) are supported in this MVP.")
    st.stop()

try:
    with st.spinner("Reading statement, classifying, and scanning for red flags… "
                    "(non-HDFC banks are read by AI and can take a minute)"):
        res = run_analysis(pdf.getvalue(), xlsx.getvalue() if xlsx else None, use_llm)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not process this statement: {exc}")
    st.stop()

st_obj, recon, flags, stats = res.statement, res.recon, res.flags, res.stats
info = st_obj.info

# ---- KPI row ---------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Transactions", len(st_obj.transactions))
c2.metric("Debits", f"₹{recon.total_debits:,.0f}", f"{recon.dr_count} txns", delta_color="off")
c3.metric("Credits", f"₹{recon.total_credits:,.0f}", f"{recon.cr_count} txns", delta_color="off")
c4.metric("Closing balance", f"₹{recon.closing_balance_computed:,.2f}")
highs = sum(1 for f in flags if f.severity.value == "high")
c5.metric("Red flags", len(flags), f"{highs} high", delta_color="inverse")

if recon.balance_chains and recon.matches_statement_summary:
    st.success(f"✅ Reconciled — balance chains to ₹{recon.closing_balance_computed:,.2f} with zero drift and ties to the bank's printed summary.")
elif recon.balance_chains:
    st.warning("⚠️ Balance chains cleanly, but could not confirm against a printed summary.")
else:
    st.error(f"❌ Balance chain drift ₹{recon.max_drift} — parse needs review.")

parser_used = "native parser" if info.bank in NATIVE_BANKS else "AI parser (DeepSeek)"
st.caption(f"**{info.account_name}**  ·  {info.bank}  ·  A/C {info.account_no}  ·  "
           f"{info.from_date} → {info.to_date}  ·  _read via {parser_used}_")

# ---- downloads -------------------------------------------------------------
d1, d2, _ = st.columns([1, 1, 3])
d1.download_button(
    "⬇️ Working paper (Excel)",
    data=build_workpaper(st_obj, recon, flags, stats),
    file_name=f"AuditWedge_{info.account_no or 'statement'}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
d2.download_button(
    "⬇️ Tally vouchers (XML)",
    data=build_tally_xml(st_obj),
    file_name=f"Tally_{info.account_no or 'vouchers'}.xml",
    mime="application/xml",
    use_container_width=True,
)

# ---- tabs ------------------------------------------------------------------
tab_flags, tab_txns, tab_recon = st.tabs(
    [f"🚩 Exceptions ({len(flags)})", f"📄 Transactions ({len(st_obj.transactions)})", "📊 Reconciliation"]
)

with tab_flags:
    if not flags:
        st.success("No exceptions raised.")
    else:
        st.write(f"**{len(flags)}** findings — {highs} high, "
                 f"{sum(1 for f in flags if f.severity.value=='medium')} medium, "
                 f"{sum(1 for f in flags if f.severity.value=='low')} low. Ranked most-severe first.")
        for f in flags:
            box = SEV_UI.get(f.severity.value, st.info)
            amt = f"  ·  ₹{f.amount:,.2f}" if f.amount is not None else ""
            row = f"  ·  txn #{f.row}" if f.row else ""
            box(f"**[{f.severity.value.upper()}] {f.title}**{amt}{row}\n\n{f.detail}")

with tab_txns:
    st.caption("Rows with low confidence (suspense / unclassified) are what a reviewer should check first.")
    st.dataframe(
        txn_dataframe(st_obj),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Debit": st.column_config.NumberColumn(format="%.2f"),
            "Credit": st.column_config.NumberColumn(format="%.2f"),
            "Balance": st.column_config.NumberColumn(format="%.2f"),
        },
    )

with tab_recon:
    a, b = st.columns(2)
    with a:
        st.subheader("Bank reconciliation")
        st.dataframe(pd.DataFrame([
            {"Item": "Opening balance", "Amount": float(recon.opening_balance)},
            {"Item": "Add: Total credits", "Amount": float(recon.total_credits)},
            {"Item": "Less: Total debits", "Amount": -float(recon.total_debits)},
            {"Item": "Computed closing", "Amount": float(recon.closing_balance_computed)},
            {"Item": "Closing per bank", "Amount": float(recon.closing_balance_reported or 0)},
        ]), use_container_width=True, hide_index=True,
            column_config={"Amount": st.column_config.NumberColumn(format="%.2f")})
        for note in recon.notes:
            st.caption("• " + note)
    with b:
        st.subheader("Ledger summary")
        st.dataframe(ledger_dataframe(st_obj), use_container_width=True, hide_index=True,
                     column_config={"Debit": st.column_config.NumberColumn(format="%.2f"),
                                    "Credit": st.column_config.NumberColumn(format="%.2f")})
