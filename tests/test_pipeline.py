"""Orchestration: Path A filter+enrich, Path B radar warning, dedup, queue rows.

store is stubbed so the test never touches jobs.db; llm is stubbed off so
classify/draft use their deterministic fallbacks.
"""

from datetime import date

import pytest

from outreach import pipeline, queue


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(pipeline.classify.llm, "call_text", lambda *a, **k: None)
    monkeypatch.setattr(pipeline.draft.llm, "call_json", lambda *a, **k: None)
    monkeypatch.setattr(pipeline.store, "init", lambda: None)
    monkeypatch.setattr(pipeline.store, "find_duplicate", lambda *a, **k: None)
    monkeypatch.setattr(pipeline.store, "record_item", lambda *a, **k: 1)


TODAY = date(2026, 9, 7)


def test_discovered_filters_and_enriches():
    jobs = [
        {"company": "Stripe", "title": "ML Engineer, New Grad",
         "description": "Work on payments fraud models.", "url": "http://x/1", "date_posted": ""},
        {"company": "IBM", "title": "Data Scientist",
         "description": "clean role", "url": "http://x/2", "date_posted": ""},  # radar-dropped
        {"company": "Acme", "title": "Senior ML Engineer",
         "description": "clean", "url": "http://x/3", "date_posted": ""},       # title-dropped
    ]
    out = pipeline.process_discovered(jobs, today=TODAY)
    assert len(out["items"]) == 1
    item = out["items"][0]
    assert item["company"] == "Stripe"
    assert item["industry"] == "fintech"                       # payments/fraud rule
    assert item["matched_repo"].endswith("governed-fraud-detection")
    assert item["draft_message"].startswith("[DRAFT]")
    assert item["source"] == "discovered"
    reasons = {d["company"]: d["reason"] for d in out["dropped"]}
    assert "IBM" in reasons and "do_not_apply" in reasons["IBM"]
    assert "Acme" in reasons and "title level" in reasons["Acme"]


def test_applied_radar_warning_still_queues():
    confs = [{"subject": "Thanks for applying",
              "sender": "Micron <careers@myworkday.com>",
              "body": "Thank you for applying to Data Engineer at Micron Technology, Inc."}]
    out = pipeline.process_applied(confs, today=TODAY)
    assert len(out["items"]) == 1              # she already applied → still queued
    assert out["items"][0]["source"] == "applied"
    assert len(out["warnings"]) == 1 and "Micron" in out["warnings"][0]
    assert "cooldown until" in out["warnings"][0]


def test_linkedin_urls_are_search_only():
    people, alumni = queue.linkedin_urls("Two Sigma")
    assert people.startswith("https://www.linkedin.com/search/results/people/")
    assert "Two%20Sigma" in people and "machine%20learning" in people
    assert "Stevens" in alumni
    # No auth, no profile scraping — just a search URL.
    assert "/in/" not in people


def test_queue_dry_run_writes_nothing(capsys):
    items = [{"date": "2026-09-07", "source": "applied", "company": "Merck",
              "role": "Data Analyst", "posting_url": "", "industry": "healthcare",
              "matched_repo": "https://github.com/riya0920/preauth-decision-gateway",
              "draft_message": "[DRAFT] hi", "draft_short": "[DRAFT] hi", "notes": ""}]
    n = queue.write_items(items, dry_run=True)
    assert n == 1
    assert "DRY RUN" in capsys.readouterr().out
