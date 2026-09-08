"""Filter kill-words, title levels, experience, age, mega-pool, radar."""

from datetime import date, datetime, timedelta, timezone

from outreach import do_not_apply as dna
from outreach.filter import filter_job

ENTRIES = dna.load()
TODAY = date(2026, 9, 7)


def _job(**kw):
    base = {"company": "Acme AI", "title": "Machine Learning Engineer",
            "description": "Build ML pipelines.", "date_posted": ""}
    base.update(kw)
    return base


def test_passes_clean_job():
    r = filter_job(_job(), today=TODAY, dna_entries=ENTRIES)
    assert r.passed and r.reason is None and r.tags == {}


def test_killword_no_sponsorship():
    r = filter_job(_job(description="We do not provide sponsorship for this role."),
                   today=TODAY, dna_entries=ENTRIES)
    assert not r.passed and "not provide sponsorship" in r.reason


def test_killword_clearance_and_citizens():
    assert not filter_job(_job(description="Active security clearance required."),
                          today=TODAY, dna_entries=ENTRIES).passed
    assert not filter_job(_job(description="Open to US citizens only."),
                          today=TODAY, dna_entries=ENTRIES).passed


def test_title_levels_dropped():
    for bad in ["Senior ML Engineer", "Staff Data Scientist", "ML Intern",
                "Engineering Lead", "Principal Engineer", "ML Co-op", "PhD Researcher"]:
        assert not filter_job(_job(title=bad), today=TODAY, dna_entries=ENTRIES).passed, bad


def test_lead_word_boundary_not_overzealous():
    # "Leadership" contains "lead" but must NOT trip the title filter.
    r = filter_job(_job(title="ML Engineer, Leadership Analytics"),
                   today=TODAY, dna_entries=ENTRIES)
    assert r.passed


def test_experience_requirement():
    assert not filter_job(_job(description="Requires 3+ years of experience."),
                          today=TODAY, dna_entries=ENTRIES).passed
    assert not filter_job(_job(description="Need 12 years experience."),
                          today=TODAY, dna_entries=ENTRIES).passed
    # 2 years is allowed (below the threshold).
    assert filter_job(_job(description="1-2 years experience preferred."),
                      today=TODAY, dna_entries=ENTRIES).passed


def test_stale_posting_dropped_only_with_date():
    old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    fresh = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    assert not filter_job(_job(date_posted=old), today=TODAY, dna_entries=ENTRIES).passed
    assert filter_job(_job(date_posted=fresh), today=TODAY, dna_entries=ENTRIES).passed
    # Unknown date → never dropped for age.
    assert filter_job(_job(date_posted=""), today=TODAY, dna_entries=ENTRIES).passed


def test_do_not_apply_cooldown_drops():
    r = filter_job(_job(company="IBM Corporation"), today=TODAY, dna_entries=ENTRIES)
    assert not r.passed and "do_not_apply" in r.reason
    # After cooldown it passes again.
    assert filter_job(_job(company="IBM"), today=date(2027, 3, 1), dna_entries=ENTRIES).passed


def test_mega_pool_tagged_not_dropped():
    r = filter_job(_job(company="Google"), today=TODAY, dna_entries=ENTRIES)
    assert r.passed and r.tags.get("referral_only") is True
