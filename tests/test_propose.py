"""tools/propose.py on strings: document type, company, existing events, and the public-address guard. No network."""

from __future__ import annotations

import json

import pytest

from tools import propose as p

COVER = {
    "rhp": "RED HERRING PROSPECTUS Dated October 1, 2026 EXAMPLE WIDGETS LIMITED Our Company was incorporated...",
    "prospectus": ("PROSPECTUS Dated October 30, 2026 Example Widgets Limited (the “Company”) The Equity Shares offered "
                   "through the Red Herring Prospectus and this Prospectus are proposed to be listed"),
    "lof": ("LETTER OF OFFER THIS DOCUMENT IS IMPORTANT AND REQUIRES YOUR IMMEDIATE ATTENTION Buyback of Equity "
            "Shares of Example Widgets Limited (the “Company”)"),
    "pa": "EXAMPLE WIDGETS LIMITED PUBLIC ANNOUNCEMENT FOR THE ATTENTION OF EQUITY SHAREHOLDERS FOR THE BUYBACK OF SHARES",
    "ad": ("THIS IS A PUBLIC ANNOUNCEMENT FOR INFORMATION PURPOSES ONLY. THIS IS NOT A PROSPECTUS ANNOUNCEMENT. "
           "EXAMPLE WIDGETS LIMITED BASIS OF ALLOTMENT"),
    "ofs": "Offer for Sale through Stock Exchange Mechanism by promoters of Example Widgets Limited. Floor price ₹ 66",
    "draft": "DRAFT RED HERRING PROSPECTUS Example Widgets Limited",
}


@pytest.mark.parametrize(("key", "doc_type", "event_type"), [
    ("rhp", "rhp", "ipo"), ("prospectus", "prospectus", "ipo"), ("lof", "letter_of_offer", "buyback"),
    ("pa", "public_announcement", "buyback"), ("ad", "announcement", "ipo"),
    ("ofs", "announcement", "ofs_stock_exchange"), ("draft", None, None),
])
def test_first_page_rules_name_the_document(key, doc_type, event_type):
    found = p.rule_type(COVER[key])
    assert (found["doc_type"], found["event_type"]) == (doc_type, event_type)
    assert found["quote"] and found["quote"] in " ".join(COVER[key].split())


@pytest.mark.parametrize(("text", "company"), [
    ("Book Building Issue EXAMPLE WIDGETS LIMITED Example Widgets Limited (the “Company”) was formed", "Example Widgets Limited"),
    ("filed by Example Corporation of Goa Limited (the “Company”) with SEBI", "Example Corporation of Goa Limited"),
    ("RED HERRING PROSPECTUS EXAMPLE WIDGETS LIMITED Our Company", "EXAMPLE WIDGETS LIMITED"),
])
def test_the_company_is_read_from_the_page(text, company):
    assert p.rule_company(text)["company"] == company


def test_the_model_is_asked_only_when_rules_leave_something_open():
    asked = []
    settled = p.propose("u", ask=lambda text: asked.append(text) or None, reader=lambda url: [COVER["lof"]])
    assert settled["doc_type"] == "letter_of_offer" and settled["company"] == "Example Widgets Limited" and not asked
    answer = {"doc_type": "prospectus", "event_type": "ipo", "label": "prospectus", "quote": "Offer Document"}
    open_ = p.propose("u", ask=lambda text: answer, reader=lambda url: ["Offer Document of a company"])
    assert open_["doc_type"] == "prospectus" and open_["how"] == "model"


def test_a_model_answer_whose_quote_is_not_on_the_page_is_dropped(monkeypatch):
    monkeypatch.setattr(p, "llm_call", lambda **kwargs: {"doc_type": "prospectus", "event_type": "ipo",
                                                         "type_quote": "words that are not there"})
    assert p.model_propose("Offer Document of a company") is None


def test_unreadable_documents_say_why():
    assert "could not read" in p.propose("u", reader=lambda url: (_ for _ in ()).throw(OSError("timeout")))["error"]
    assert "no text layer" in p.propose("u", reader=lambda url: ["  "])["error"]


@pytest.mark.parametrize(("url", "refused"), [
    ("ftp://example.org/a.pdf", True), ("http://127.0.0.1/a.pdf", True), ("http://10.1.2.3/a.pdf", True),
    ("http://169.254.169.254/latest", True), ("https://8.8.8.8/a.pdf", False),
])
def test_only_public_web_addresses_are_read(url, refused):
    assert (p.public_url(url) is not None) == refused


def test_an_existing_event_is_found_by_document_or_by_company_type_and_month(tmp_path):
    (tmp_path / "auto").mkdir()
    (tmp_path / "auto" / "example_widgets_limited_ipo_202611.json").write_text(json.dumps({
        "event_id": "example_widgets_limited_ipo_202611", "event_type": "ipo", "company": "Example Widgets Ltd.",
        "documents": [{"url": "https://example.org/p.pdf", "doc_type": "prospectus"}]}), encoding="utf-8")
    assert p.existing_event(["https://example.org/p.pdf"], "", "", "", tmp_path) == "example_widgets_limited_ipo_202611"
    assert p.existing_event(["https://example.org/other.pdf"], "Example Widgets Limited", "ipo", "202611", tmp_path) \
        == "example_widgets_limited_ipo_202611"
    assert p.existing_event(["https://example.org/other.pdf"], "Example Widgets Limited", "ipo", "202701", tmp_path) is None
    assert p.existing_event(["https://example.org/other.pdf"], "Example Widgets Limited", "buyback", "202611", tmp_path) is None
