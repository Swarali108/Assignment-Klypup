"""ui/components.py: document text is escaped, unknowns carry reasons, pills carry words. No network."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import tools.llm  # noqa: F401  (loads .env now, so the tests below control the environment)
from ui import components as c

SCRIPT = "<script>alert(1)</script>"
APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _entry(**changes) -> dict:
    entry = {
        "person_id": "p_x", "rank": 1, "name_as_printed": SCRIPT, "holder_type": "person",
        "role_as_printed": "<b>Promoter</b>", "why_money": "sells <img src=x onerror=alert(1)> shares",
        "amount_display": "up to ₹6.08 crore", "timing_status": "unlocked", "timing_display_status": "in_hand",
        "timing_display": "in hand since <i>today</i>",
        "confidence": "high", "money_now_crore": "6.08", "rank_reasons": [SCRIPT],
    }
    return {**entry, **changes}


def _person() -> dict:
    evidence = {"source_url": "https://example.org/doc.pdf", "pdf_index": 20, "printed_page": "16",
                "field": "name_as_printed", "quote": SCRIPT}
    return {
        "person_id": "p_x", "name_as_printed": SCRIPT, "evidence": [evidence], "flags": [SCRIPT],
        "family_group": {"id": "family_1", "reason": SCRIPT}, "follow_on": [],
        "confidence": {"level": "high", "reasons": [SCRIPT]},
        "amounts": {"proceeds": {"status": "computed", "display": SCRIPT, "working": SCRIPT,
                                 "inputs": [{"field": "shares_offered",
                                             "evidence": [{k: v for k, v in evidence.items() if k != "field"}]}]},
                    "retained": {"status": "unknown", "reason": SCRIPT}},
        "timing": {"proceeds": {"status": "in_hand", "when": SCRIPT,
                                "sources": [{"link": "javascript:alert(1)", "pdf_index": 3, "quotes": [SCRIPT]}]}},
    }


def test_a_script_in_any_document_value_is_escaped_everywhere():
    entry, person = _entry(), _person()
    brief = {"lines": [SCRIPT, "two", "three"], "brief_source": "template", "fallback_reason": SCRIPT,
             "template_problem": SCRIPT}
    pieces = [
        c.card_html(entry),
        c.detail_html(entry, person, brief),
        c.event_block(SCRIPT, "ipo", "e1", [{"url": "https://example.org/a.pdf", "doc_type": "rhp", "note": SCRIPT}], {}),
        c.kpi_cards({"callable": [entry], "entities": []}, {"totals": {"cost_usd": 0.0, "fresh_usd": 0.001}}),
        c.completeness_html({SCRIPT: {"status": "not checked", "reason": SCRIPT}}),
    ]
    for piece in pieces:
        text = "".join(piece) if isinstance(piece, list) else piece
        assert "<script>" not in text and "<img" not in text and "<b>Promoter" not in text
        assert "&lt;script&gt;" in text


def test_only_http_links_become_links():
    assert 'href="javascript' not in c.detail_html(_entry(), _person(), None)
    chip = c.chip({"link": "https://example.org/doc.pdf#page=20", "field": "shares_offered", "label": "p. 16", "quote": 'a "q"'})
    assert 'href="https://example.org/doc.pdf#page=20"' in chip and 'target="_blank"' in chip
    assert 'title="a &quot;q&quot;"' in chip


def test_evidence_chips_open_the_cited_page():
    refs = c.evidence_refs(_person()["amounts"]["proceeds"])
    assert refs == [{"link": "https://example.org/doc.pdf#page=20", "field": "shares_offered", "label": "p. 16",
                     "quote": SCRIPT}]


def test_unknown_is_muted_with_the_reason_as_tooltip():
    assert c.unknown('pre-offer holding "not" verified') == (
        '<span class="mc-unknown" title="pre-offer holding &quot;not&quot; verified">unknown</span>')
    assert c.amount_text("unknown: price not verified") == c.unknown("price not verified")
    assert "unknown" in c.role_badge(None) and "unknown" in c.listing_html({"status": "unknown", "reason": "r"})
    assert "unknown" in c.kpi_cards({"callable": [_entry(money_now_crore="0")], "entities": []}, None)[2]


@pytest.mark.parametrize(("status", "words", "tone"), [
    ("in_hand", "In hand", "green"), ("scheduled", "Scheduled", "amber"), ("locked_in", "Locked in", "grey"),
    ("partly_unlocked", "Partly unlocked", "grey"), ("unknown", "Timing unknown", "red-outline"),
    (None, "Timing unknown", "red-outline"),
])
def test_timing_pill_always_has_words(status, words, tone):
    pill = c.timing_pill(status, "full words")
    assert f">{words}<" in pill and f"mc-tone-{tone}" in pill and 'title="full words"' in pill


def test_step_lines_are_read_as_run_py_prints_them():
    row = c.parse_step_line("STEP extract done 5.6s calls=7 cached=6 cost=$0.001111")
    assert row == {"step": "extract", "seconds": "5.6", "calls": "7", "cached": "6", "cost": "0.001111"}
    assert "&#36;0.001111" in c.step_html(row) and "7 calls (6 cached)" in c.step_html(row)
    assert c.parse_total_line("total          19.3     10       6   0.001852")["cost"] == "0.001852"
    assert c.parse_step_line("STEP extract start") is None


def test_largest_entry_picks_a_stored_entry():
    entries = [_entry(rank=1, money_now_crore="2"), _entry(rank=2, money_now_crore="9.5"), _entry(rank=3, money_now_crore="0")]
    assert c.largest_entry(entries)["rank"] == 2
    assert c.largest_entry([_entry(money_now_crore="0")]) is None


def test_every_page_and_event_renders(monkeypatch):
    """Every page, and on Prospects every event with cards and table view, renders without an error."""
    monkeypatch.setenv("APP_PASSWORD", "")
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception
    for page in ("home", "insights", "network", "reports", "prospects"):
        app.session_state["page"] = page
        app.run()
        assert not app.exception, (page, app.exception)
    # Prospects lists only processed events (shown by company), so every option has cards.
    labels = app.selectbox(key="prospects_event").options
    assert labels[0] == "All processed events" and len(labels) > 1
    for index in range(len(labels)):
        box = app.selectbox(key="prospects_event")
        box.set_value(_option_value(box, index)).run()
        assert not app.exception, (labels[index], app.exception)
        assert app.expander, labels[index]
        app.toggle(key="prospects_table").set_value(True).run()
        assert not app.exception, (labels[index], "table view")
        app.toggle(key="prospects_table").set_value(False).run()


def _option_value(box, index: int) -> str:
    """The value behind the select box's index-th option (AppTest lists labels)."""
    from app import EVENTS
    from ui.shell import ALL_EVENTS
    from ui import dashboard_data as data
    values = [ALL_EVENTS] + [event["spec"].event_id for event in data.processed(data.load_events(EVENTS, EVENTS.parent / "outputs"))]
    return values[index]


def test_a_quote_across_lines_stays_inside_one_html_block():
    piece = c.chip({"link": "https://example.org/a.pdf#page=1", "field": "x", "label": "p. 1", "quote": "a\n\n    b"})
    assert "\n" not in piece and 'title="a b"' in piece


def test_separators_keep_their_spaces():
    assert c.join(["without cache ", c.usd(0.5), " · x"]) == "without cache &#36;0.500000 · x"


def test_card_pill_follows_the_displayed_timing_not_the_ranking_trigger():
    card = c.card_html(_entry())
    assert ">In hand<" in card and ">Unlocked<" not in card
    unknown_card = c.card_html(_entry(timing_display_status="unknown", timing_display="unknown: listing date not verified"))
    assert ">Timing unknown<" in unknown_card and 'title="listing date not verified"' in unknown_card
