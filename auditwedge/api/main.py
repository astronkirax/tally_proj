"""AuditWedge API — a thin FastAPI layer over the core engine.

POST /api/analyze  (multipart: statement + optional invoices/masters) -> structured JSON
GET  /api/download/{job_id}/{artifact}  -> workpaper | tally | vouchers | gstr3b | gstr1 | itr
GET  /api/templates/masters[?example=true]  -> blank/example masters Excel
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402

from api.serialize import serialize_result  # noqa: E402
from core.export.tally_xml import build_tally_xml  # noqa: E402
from core.export.vouchers_excel import tally_xml_to_excel  # noqa: E402
from core.export.workpaper import build_workpaper  # noqa: E402
from core.financials.gst import gstr1_bytes, gstr3b_bytes  # noqa: E402
from core.financials.itr import itr_bytes  # noqa: E402
from core.financials.masters import example_template, read_masters, write_template  # noqa: E402
from core.ingest.invoices import load_invoices  # noqa: E402
from core.pipeline import analyze  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XML = "application/xml"
JSON = "application/json"

app = FastAPI(title="AuditWedge API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# In-memory job store (single instance). Holds the analysis result so downloads don't re-parse.
JOBS: dict[str, dict] = {}
_MAX_JOBS = 40


def _xlsx_headers(name: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@app.get("/api/health")
def health():
    return {"ok": True, "service": "auditwedge"}


@app.get("/api/templates/masters")
def masters_template(example: bool = False):
    data = example_template() if example else write_template()
    name = "client_masters_example.xlsx" if example else "client_masters_template.xlsx"
    return Response(data, media_type=XLSX, headers=_xlsx_headers(name))


@app.post("/api/analyze")
async def do_analyze(
    statement: UploadFile = File(...),
    invoices: UploadFile | None = File(None),
    masters: UploadFile | None = File(None),
    password: str = Form(""),
    use_llm: bool = Form(False),
):
    pdf = await statement.read()
    inv_bytes = await invoices.read() if invoices is not None else None
    mst_bytes = await masters.read() if masters is not None else None
    try:
        m = read_masters(mst_bytes) if mst_bytes else None
        res = analyze(pdf, inv_bytes, use_llm=use_llm, password=password or None, masters=m)
    except Exception as e:  # parse / password / masters errors -> 400 with a clear message
        raise HTTPException(status_code=400, detail=str(e))

    job_id = uuid.uuid4().hex[:16]
    if len(JOBS) >= _MAX_JOBS:
        JOBS.pop(next(iter(JOBS)))
    JOBS[job_id] = {"res": res, "inv": inv_bytes}

    payload = serialize_result(res)
    payload["job_id"] = job_id
    return JSONResponse(payload)


@app.get("/api/download/{job_id}/{artifact}")
def download(job_id: str, artifact: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found — re-run the analysis.")
    res = job["res"]
    info = res.statement.info
    acct = info.account_no or "statement"
    inv = load_invoices(job["inv"]) if job["inv"] else []

    def tally():
        return build_tally_xml(res.statement, invoices=inv, bank_ledger=f"{info.bank} Bank",
                               company=info.account_name or "")

    if artifact == "workpaper":
        data = build_workpaper(res.statement, res.recon, res.flags, res.stats,
                               financials=res.financials, gst=res.gst, itr=res.itr)
        return Response(data, media_type=XLSX, headers=_xlsx_headers(f"AuditWedge_{acct}.xlsx"))
    if artifact == "tally":
        return Response(tally(), media_type=XML, headers=_xlsx_headers(f"Tally_{acct}.xml"))
    if artifact == "vouchers":
        return Response(tally_xml_to_excel(tally()), media_type=XLSX,
                        headers=_xlsx_headers(f"Vouchers_{acct}.xlsx"))
    if artifact in ("gstr3b", "gstr1", "itr"):
        if res.gst is None or res.itr is None:
            raise HTTPException(status_code=400, detail="Upload client masters to generate GST/ITR.")
        data = {"gstr3b": lambda: gstr3b_bytes(res.gst, "cab"),
                "gstr1": lambda: gstr1_bytes(res.gst, "cab"),
                "itr": lambda: itr_bytes(res.itr)}[artifact]()
        return Response(data, media_type=JSON, headers=_xlsx_headers(f"{artifact.upper()}_{acct}.json"))

    raise HTTPException(status_code=404, detail=f"Unknown artifact '{artifact}'.")
