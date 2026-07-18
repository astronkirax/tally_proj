"""PDF -> text extraction (digital PDFs only in v1; OCR comes in Phase 2).

Handles password-protected statements (very common for bank PDFs): if a password is
supplied it's used to unlock the file; if the file is locked and no/wrong password is
given, a clear :class:`PdfPasswordError` is raised so the UI can prompt for it.
"""
from __future__ import annotations

import fitz  # PyMuPDF

from core.ingest.base import PdfPasswordError


def extract_text(source, password: str | None = None) -> str:
    """Extract text from a PDF (path / bytes / file-like), unlocking it if needed."""
    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(source), filetype="pdf")
    elif hasattr(source, "read"):
        doc = fitz.open(stream=source.read(), filetype="pdf")
    else:
        doc = fitz.open(source)
    try:
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                raise PdfPasswordError(
                    "This PDF is password-protected. Enter its password in the sidebar "
                    "(banks commonly use your PAN, date of birth, or account number)."
                )
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
