#!/usr/bin/env python3
"""Minimal LLM provider shim — the ONLY place the engine talks to a model.

Owned by task 03 (rules assistant); task 01's coach imports `complete()` from
here rather than writing a second provider path. Raw HTTP via urllib because
engine/ is stdlib-only by design (CLAUDE.md gotcha 6) — no anthropic SDK, no
requests.

Configuration (env):
    MTG_LLM_API_KEY   required for any call; absent means "not configured"
                      and callers must degrade gracefully, never crash.
    MTG_LLM_MODEL     default claude-haiku-4-5 — the specs' cost target
                      (~$0.003/question, cached forever) calls for the small
                      cheap tier; set a bigger model here if quality warrants.

Never log or echo the key. Never commit one.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5"


class LLMError(RuntimeError):
    """The provider call failed (network, HTTP error, or empty response)."""


class LLMNotConfigured(LLMError):
    """No API key in the environment — callers should degrade, not crash."""


def default_model() -> str:
    return os.environ.get("MTG_LLM_MODEL", DEFAULT_MODEL)


def configured() -> bool:
    return bool(os.environ.get("MTG_LLM_API_KEY"))


def complete(system: str, user: str, *, model: str | None = None,
             api_key: str | None = None, max_tokens: int = 1024,
             timeout: float = 120.0) -> str:
    """One synchronous completion; returns the response text.

    Raises LLMNotConfigured when no key is available, LLMError on any
    provider failure. Callers own caching and retries.
    """
    key = api_key or os.environ.get("MTG_LLM_API_KEY", "")
    if not key:
        raise LLMNotConfigured("MTG_LLM_API_KEY is not set")
    body = json.dumps({
        "model": model or default_model(),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers={
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001 — the status code is the signal
            pass
        raise LLMError(f"provider returned HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"provider unreachable: {e.reason}") from e
    if data.get("stop_reason") == "refusal":
        raise LLMError("the model declined this request")
    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")
    if not text.strip():
        raise LLMError(
            f"no text in response (stop_reason={data.get('stop_reason')})")
    return text
