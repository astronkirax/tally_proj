# AuditWedge 🧾

Upload a bank statement → get an **auto bank reconciliation**, an **auditor red-flag
report**, and a **Tally-ready working paper** — in seconds.

This is the Phase-1 MVP of the "audit-first" wedge: it *performs* the mechanical
scrutiny a CA/auditor does by hand, instead of just organising a workflow.

---

## What it does

1. **Reads** a digital PDF bank statement — **HDFC** via a fast native parser, and
   **any other bank** via the generic AI parser (DeepSeek) when a key is configured.
2. **Reconstructs** every transaction and recovers Debit/Credit from the balance column
   — a *self-checking* method that chains from the opening balance to the printed
   closing balance with **zero drift** (if it can't, it says so instead of guessing).
3. **Classifies** each line into a ledger + counterparty (rules first; optional Claude
   for the ambiguous rows).
4. **Flags** audit exceptions — near-zero balances, unvouched advances, unexplained
   receipts, possible duplicates, payee concentration, and (if you add the invoice
   Excel) invoices dated outside the period.
5. **Exports** an Excel working paper (5 sheets) and a Tally voucher XML you can import.

---

## Setup (one time)

You need **Python 3.12+**. In a terminal, from this `auditwedge` folder:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
> If PowerShell blocks activation, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**macOS / Linux / Git-Bash:**
```bash
python -m venv .venv
source .venv/Scripts/activate   # (.venv/bin/activate on mac/linux)
pip install -r requirements.txt
```

*(Optional)* to enable AI classification **and reading non-HDFC banks**: copy
`.env.example` to `.env` and paste your `DEEPSEEK_API_KEY`. The app works fully without
it for HDFC. Verify the key with: `python -m core.llm`

> **Data note:** the AI parser/classifier sends statement text to DeepSeek's API. For a
> production audit product you'll want client consent and an India-hosted model option;
> fine for development and pilots.

---

## Run the app

```powershell
streamlit run app/streamlit_app.py
```
Your browser opens at **http://localhost:8501**. Upload a bank statement PDF (and,
optionally, a purchase-invoice Excel), then use the tabs and the download buttons.

A sample statement is included at `tests/fixtures/hdfc_sample.pdf` if you want to try it.

---

## Run the tests

```powershell
pytest -q
```
The golden test proves the sample reconciles exactly (91 debits = ₹129,593.00,
40 credits = ₹129,564.56, closing ₹89.02).

---

## Project layout

```
auditwedge/
  core/                 # the engine (framework-independent — the real asset)
    schema.py           # canonical data models (Decimal money, Dr/Cr, flags)
    ingest/             # PDF -> transactions
      base.py           # running-balance reconstruction (the self-checking core)
      hdfc.py           # HDFC adapter (fast, free, offline)
      generic_llm.py    # generic AI parser — any bank, Dr/Cr still balance-verified
      registry.py       # detect bank -> native adapter, else AI parser
      invoices.py       # read invoice Excel + period cross-check
      pdf.py            # PDF text extraction
    llm.py              # DeepSeek client (OpenAI-compatible), JSON mode
    classify.py         # rules + optional DeepSeek fallback
    reconcile.py        # bank reconciliation / balance integrity
    exceptions.py       # the audit red-flag rules
    export/             # workpaper.py (Excel) + tally_xml.py (Tally import)
    pipeline.py         # analyze() — one call runs everything
  app/streamlit_app.py  # the MVP UI (thin, replaceable)
  tests/                # golden + end-to-end tests, with fixtures
```

## Banks

Any bank already works through the **generic AI parser** (needs `DEEPSEEK_API_KEY`).
For a bank you process a lot, add a **dedicated native adapter** — it's faster, free and
offline: create `core/ingest/<bank>.py` implementing `BankAdapter` (`matches()` +
`parse()`), reuse `pair_by_running_balance` from `base.py`, and add the class to
`ADAPTERS` in `registry.py`. The registry uses the native adapter when it matches and
falls back to AI otherwise — either way, Dr/Cr is verified against the balance column.

## Deploy (later, free)

Push to a private GitHub repo and connect it to **Streamlit Community Cloud** — it runs
`app/streamlit_app.py` for free. When the wedge is validated, the UI graduates to a
proper web frontend (FastAPI + Next.js) while this `core/` engine carries over unchanged.

---

*Draft outputs are for auditor review and sign-off — AuditWedge is a co-pilot, not a
replacement for professional judgement.*
