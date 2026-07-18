"""PDF -> text extraction (digital PDFs only in v1; OCR comes in Phase 2)."""
from __future__ import annotations

import fitz  # PyMuPDF


def extract_text(source) -> str:
    """Extract text from a PDF.

    ``source`` may be a filesystem path, raw ``bytes``, or a file-like object with
    ``.read()`` (e.g. a Streamlit upload). Pages are joined with newlines, preserving
    the top-to-bottom reading order the parser relies on.
    """
    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(source), filetype="pdf")
    elif hasattr(source, "read"):
        doc = fitz.open(stream=source.read(), filetype="pdf")
    else:
        doc = fitz.open(source)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
