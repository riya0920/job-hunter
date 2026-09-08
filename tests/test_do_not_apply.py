"""Fuzzy company matching + cooldown logic."""

from datetime import date

from outreach import do_not_apply as dna

ENTRIES = dna.load()  # the real 65-company radar file


def test_normalize_strips_suffixes():
    assert dna.normalize("IBM Corporation") == "ibm"
    assert dna.normalize("Micron Technology, Inc.") == "micron"
    assert dna.normalize("Visa Inc.") == "visa"
    assert dna.normalize("Smith+Nephew") == "smith nephew"


def test_matches_legal_suffix_variants():
    assert dna.find_entry("IBM", ENTRIES)["company"] == "IBM"
    assert dna.find_entry("IBM Corporation", ENTRIES)["company"] == "IBM"
    assert dna.find_entry("Micron", ENTRIES)["company"] == "Micron"
    assert dna.find_entry("Micron Technology, Inc.", ENTRIES)["company"] == "Micron"
    assert dna.find_entry("Visa Inc", ENTRIES)["company"] == "Visa"


def test_does_not_match_unrelated_prefix():
    # "Microsoft" must NOT match the radar's "Micron".
    assert dna.find_entry("Microsoft", ENTRIES) is None
    # A company not on the list.
    assert dna.find_entry("Anthropic", ENTRIES) is None


def test_cooldown_blocked_vs_expired():
    # IBM cooldown_until 2027-02-28.
    blocked = dna.check("IBM Corporation", today=date(2026, 9, 7), entries=ENTRIES)
    assert blocked is not None and blocked["blocked"] is True
    assert blocked["rejections"] == 11

    # After the cooldown date it is no longer blocked.
    expired = dna.check("IBM", today=date(2027, 3, 1), entries=ENTRIES)
    assert expired is not None and expired["blocked"] is False


def test_check_none_for_unlisted():
    assert dna.check("Anthropic", today=date(2026, 9, 7), entries=ENTRIES) is None
