"""Thin Anthropic wrapper used by extraction / classification / drafting.

Every call is defensive: no ANTHROPIC_API_KEY, a missing SDK, or any error
returns None so callers fall back to their deterministic path. That keeps
--dry-run and the unit tests fully offline.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from .config import MODEL

_client = None
_client_tried = False


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and _get_client() is not None


def _get_client():
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # lazy: only when a key is present

        _client = anthropic.Anthropic()
    except Exception as e:  # pragma: no cover - depends on env
        print(f"[LLM] Anthropic client unavailable: {e}")
        _client = None
    return _client


def call_text(system: str, user: str, max_tokens: int = 400) -> Optional[str]:
    """Return the model's text response, or None on any failure."""
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "".join(parts).strip() or None
    except Exception as e:  # pragma: no cover - network path
        print(f"[LLM] call failed: {e}")
        return None


def call_json(system: str, user: str, max_tokens: int = 400) -> Optional[dict]:
    """Return a parsed JSON object from the model, or None on any failure."""
    text = call_text(system, user, max_tokens=max_tokens)
    if not text:
        return None
    return _first_json_object(text)


def _first_json_object(text: str) -> Optional[dict]:
    """Best-effort: pull the first {...} block and parse it."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None
