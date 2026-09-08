"""Golden-file tests for Gmail confirmation extraction across 5 ATS formats.

The Claude call is forced off so we exercise the deterministic regex fallback
(offline, no key). When a key is present in production, Claude runs first and
the fallback is the safety net.
"""

import json
import os

import pytest

from outreach import extract

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")


def _load_email(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    header, _, body = raw.partition("\n\n")
    subject = sender = ""
    for line in header.splitlines():
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
        elif line.lower().startswith("from:"):
            sender = line.split(":", 1)[1].strip()
    return subject, sender, body.strip()


def _expected():
    with open(os.path.join(GOLDEN_DIR, "expected.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("fname", list(_expected().keys()))
def test_extraction_matches_golden(fname, monkeypatch):
    # Force the offline fallback path.
    monkeypatch.setattr(extract.llm, "call_json", lambda *a, **k: None)

    subject, sender, body = _load_email(os.path.join(GOLDEN_DIR, fname))
    got = extract.extract(subject, sender, body)
    exp = _expected()[fname]

    assert got["ats"] == exp["ats"], f"{fname}: ats {got['ats']!r} != {exp['ats']!r}"
    assert got["company"] == exp["company"], f"{fname}: company {got['company']!r} != {exp['company']!r}"
    assert got["role"] == exp["role"], f"{fname}: role {got['role']!r} != {exp['role']!r}"
