"""Lock-in and proceeds-timing rules are found in the event's own pages. No network, no model call."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import config.lock_in as lock_in
from agents.rule_sources import anchor_pattern, find_rule_sources
from agents.rules_ipo import timing

URL = "https://example.test/rhp.pdf"
LOCK_IN_TEXT = (
    "Details of Promoters' contribution and lock-in. An aggregate of 20% held by our Promoters is "
    "required to be locked in for a period of 18 months. The shareholding of the Promoter in excess of "
    "20% shall be locked in for a period of six months from the date of Allotment. "
    "The entire pre-Offer Equity Share capital will be locked-in for a period of six months from the "
    "date of Allotment."
)
# The proceeds rule needs a sentence that says the sellers are paid at listing.
# (An expense-reimbursement sentence no longer counts: see tests/test_recall.py.)
LISTING_TEXT = (
    "Upon receipt of the listing and trading approvals, the amounts in the Public Offer Account "
    "will be transferred to the Selling Shareholders."
)


def _pages(with_rules: bool) -> list[dict]:
    pages = [{"pdf_index": index, "printed_page": str(index - 4), "source_url": URL, "text": "Other text."} for index in range(1, 60)]
    if with_rules:
        pages[39] = {**pages[39], "text": LOCK_IN_TEXT}
        pages[44] = {**pages[44], "text": LISTING_TEXT}
    return pages


def _seller(role: str) -> dict:
    return {"name_as_printed": "Asha Example", "role_as_printed": role, "seller_status": "verified",
            "shares_offered": "100", "shares_held_pre_offer": "1,000",
            "evidence": [{"field": "name_as_printed", "section": "selling_shareholders", "field_kept": True}]}


def _listing() -> dict:
    return {"status": "verified", "date_as_printed": "March 11, 2026", "listed_on": "2026-03-11", "past": True,
            "days_since": 248, "age": "8 months ago", "inputs": []}


def _allotment() -> dict:
    return {"status": "verified", "date_as_printed": "March 9, 2026", "allotted_on": "2026-03-09", "inputs": []}


def test_config_names_no_document():
    text = Path(lock_in.__file__).read_text(encoding="utf-8")
    assert not re.search(r"https?://", text)
    assert "pdf_index" not in text and "printed_page" not in text
    for rule in lock_in.LOCK_IN_RULES:
        assert all(period["anchors"] for period in rule["periods"])


def test_rule_on_pdf_40_is_cited_at_pdf_40():
    sources = find_rule_sources(_pages(with_rules=True))
    found = sources["pre_offer_capital"]["periods"]["pre-Offer capital"]
    assert found["found"] is True
    assert found["pdf_index"] == 40
    assert found["link"] == f"{URL}#page=40"
    assert "entire pre-Offer Equity Share capital" in found["quotes"][0]
    retained = timing(_seller("Selling Shareholders"), _listing(), _allotment(), date(2026, 11, 14), sources)["retained"]
    assert retained["status"] == "unlocked"
    assert retained["sources"][0]["pdf_index"] == 40
    proceeds = timing(_seller("Selling Shareholders"), _listing(), _allotment(), date(2026, 11, 14), sources)["proceeds"]
    assert proceeds["rule_found"] is True and proceeds["sources"][0]["pdf_index"] == 45


def test_lock_in_pages_are_searched_first():
    pages = _pages(with_rules=True)
    pages[9] = {**pages[9], "text": LOCK_IN_TEXT}
    sources = find_rule_sources(pages, [{"source_url": URL, "pdf_index": 40}])
    assert sources["pre_offer_capital"]["periods"]["pre-Offer capital"]["pdf_index"] == 40
    assert find_rule_sources(pages)["pre_offer_capital"]["periods"]["pre-Offer capital"]["pdf_index"] == 10


def test_an_rhp_without_the_rule_gives_unknown():
    sources = find_rule_sources(_pages(with_rules=False))
    result = timing(_seller("Promoter Selling Shareholder"), _listing(), _allotment(), date(2026, 11, 14), sources)
    assert result["retained"] == {
        "status": "unknown",
        "reason": "lock-in rule not found in this event's documents",
        "rule": "minimum_promoters_contribution",
        "role_used": "Promoter Selling Shareholder",
        "missing_periods": ["Minimum Promoters' Contribution", "promoter shares above the 20%"],
    }
    assert result["proceeds"]["when"].endswith("; at listing (not stated in this event's documents)")
    assert result["proceeds"]["rule_found"] is False
    assert result["proceeds"]["todo"]


def test_anchor_matches_across_hyphens_and_curly_quotes():
    assert anchor_pattern("locked in for a period of six months").search("locked-in for a period of six months")
    assert anchor_pattern("promoters' contribution").search("Promoters’ Contribution")
    assert not anchor_pattern("in excess of 20%").search("in excess of 200%")
