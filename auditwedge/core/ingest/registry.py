"""Bank-format detection + the one entry point the rest of the app calls."""
from __future__ import annotations

from core.ingest.base import BankAdapter, NoTextError, ParseError
from core.ingest.generic_llm import GenericLLMAdapter
from core.ingest.hdfc import HDFCAdapter
from core.ingest.kvb import KVBAdapter
from core.ingest.pdf import extract_text
from core.llm import llm_available
from core.schema import Statement

# Dedicated (fast, free, offline) adapters. Register new banks here — most specific
# first. Any bank NOT matched here routes to the generic AI parser when a key is set.
ADAPTERS: list[type[BankAdapter]] = [HDFCAdapter, KVBAdapter]


def detect(text: str) -> BankAdapter | None:
    for adapter_cls in ADAPTERS:
        if adapter_cls.matches(text):
            return adapter_cls()
    return None


def supported_banks() -> list[str]:
    names = [a.bank_name for a in ADAPTERS]
    if llm_available():
        names.append("+ any bank via AI parser")
    return names


def load_statement(source, password: str | None = None, allow_ai: bool = True) -> Statement:
    """PDF (path / bytes / upload) -> canonical :class:`Statement`.

    Tries a dedicated adapter first; falls back to the generic AI parser for any other
    bank when a DeepSeek key is configured. ``password`` unlocks protected PDFs.
    """
    text = extract_text(source, password=password)
    if len(text.strip()) < 40:
        raise NoTextError(
            "No readable text found in this PDF. If it is a scanned image or photo, "
            "OCR isn't supported yet — please upload a digital (text) statement."
        )
    adapter = detect(text)
    if adapter is None:
        if allow_ai and llm_available():
            adapter = GenericLLMAdapter()
        else:
            raise ParseError(
                "Could not detect the bank format. Dedicated support: "
                + ", ".join(a.bank_name for a in ADAPTERS)
                + ". Set DEEPSEEK_API_KEY to enable the generic AI parser for other banks."
            )
    return adapter.parse(text)
