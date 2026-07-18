"""Unified LLM access — DeepSeek by default (OpenAI-compatible), swappable via env.

Config (in .env):
  DEEPSEEK_API_KEY   the key
  LLM_BASE_URL       default https://api.deepseek.com
  LLM_MODEL          default deepseek-v4-flash  (use deepseek-v4-pro for max quality)

Everything here degrades gracefully: if no key is set, :func:`llm_available` is False
and callers fall back to their deterministic paths.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE = "https://api.deepseek.com"


def _api_key() -> str | None:
    return os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")


def llm_available() -> bool:
    return bool(_api_key())


def model() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    base = os.getenv("LLM_BASE_URL", DEFAULT_BASE if os.getenv("DEEPSEEK_API_KEY") else None)
    kwargs = {"api_key": _api_key(), "timeout": 300.0, "max_retries": 2}
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def chat_json(system: str, user: str, *, model_name: str | None = None,
              max_tokens: int = 8000, thinking: bool = False):
    """Call the model in JSON mode. Returns parsed JSON (dict/list) or None on failure.

    Thinking mode is OFF by default: our tasks (extraction, classification) are
    mechanical, and thinking just makes them slower and pricier. On deepseek-v4 models
    we disable it explicitly; set ``thinking=True`` to allow it.
    """
    if not llm_available():
        return None
    mdl = model_name or model()
    extra = {}
    if not thinking and mdl.startswith("deepseek-v4"):
        extra["extra_body"] = {"thinking": {"type": "disabled"}}
    try:
        resp = _client().chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=max_tokens,
            **extra,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:  # surface API errors (rate limits, auth, timeouts) in the logs
        import sys
        print(f"[llm.chat_json] {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return None


def ping() -> tuple[bool, str]:
    """Quick connectivity check for the CLI / setup. Returns (ok, message)."""
    if not llm_available():
        return False, "No DEEPSEEK_API_KEY set."
    out = chat_json(
        "You reply only in JSON.",
        'Reply with {"ok": true}.',
        max_tokens=50,
    )
    if out and out.get("ok"):
        return True, f"DeepSeek reachable — model '{model()}'."
    return False, "Key set but the API call failed (check key / network / model name)."


if __name__ == "__main__":  # python -m core.llm  -> quick check
    ok, msg = ping()
    print(("OK: " if ok else "FAIL: ") + msg)
