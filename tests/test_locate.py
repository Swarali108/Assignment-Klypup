"""Locate sections on a fake six-page filing. No files and no network."""

from __future__ import annotations

from pathlib import Path

import hashlib

import pytest

from agents.locate import locate, normalise, score_page
from agents.spec import load_event_spec
from config.sections import SECTIONS, STRUCTURE
from run import _print_table
from tools.pdf import printed_page_from_text

ROOT_EVENT = Path(__file__).resolve().parents[1] / "events" / "example_ipo.json"


def _page(pdf_index: int, printed_page: str | None, lines: list[str]) -> dict:
    return {"pdf_index": pdf_index, "printed_page": printed_page, "text": "\n".join(lines)}


def _filing() -> list[dict]:
    """Six pages. Page 1 is a heading variant. Page 5 is table-like."""
    return [
        _page(
            1,
            "12",
            [
                "DETAILS OF SELLING SHAREHOLDERS",
                "The selling shareholders are listed in this section.",
            ],
        ),
        _page(
            2,
            "13",
            [
                "THE OFFER",
                "This offer comprises a fresh issue and an offer for sale.",
                "The fresh issue of equity shares is distinct from the offer for sale of equity shares.",
                "",
                "",
                "",
                "",
                "",
                "A shareholding pattern is discussed later in prose.",
            ],
        ),
        _page(
            3,
            "14",
            [
                "WEIGHTED AVERAGE COST OF ACQUISITION",
                "The weighted average cost of acquisition is tabulated for the sellers.",
            ],
        ),
        _page(
            4,
            None,
            [
                "SHAREHOLDING OF OUR PROMOTERS",
                "The promoters' contribution is set out below.",
                "Promoter holding is stated as a count of shares.",
                "LOCK-IN",
                "The shares are locked-in for the stated lock in period.",
            ],
        ),
        _page(
            5,
            "16",
            [
                "Notes",
                "This page is a table.",
                "",
                "",
                "",
                "",
                "",
                "",
                "shareholding pattern 1200 45.5 540",
            ],
        ),
        _page(
            6,
            "17",
            [
                "KEY MANAGERIAL PERSONNEL",
                "The chief financial officer and the whole-time director are included.",
                "EMPLOYEE STOCK OPTION SCHEME",
                "The employee stock option scheme covers the employee stock options granted under the ESOP.",
                "Price band, floor price, cap price, offer price and buyback price",
                "BUYBACK ENTITLEMENT",
                "The intention to participate is disclosed. The acceptance ratio applies to the buyback entitlement.",
                "The promoters intend to participate in the tender.",
                "",
                "The selling shareholders are named again in the narrative below.",
            ],
        ),
    ]


def test_each_section_ranks_its_page_first():
    found = locate(_filing(), "ipo")
    assert [hit["pdf_index"] for hit in found["selling_shareholders"][:2]] == [1, 6]
    assert found["selling_shareholders"][0]["printed_page"] == "12"
    assert found["selling_shareholders"][0]["matched_terms"][0] == "details of selling shareholders"
    assert found["offer_structure"][0]["pdf_index"] == 2
    assert found["waca"][0]["pdf_index"] == 3
    assert found["promoter_holding"][0]["pdf_index"] == 4
    assert found["promoter_holding"][0]["printed_page"] is None
    assert found["lock_in"][0]["pdf_index"] == 4
    assert found["shareholding_pattern"][0]["pdf_index"] == 5
    assert found["shareholding_pattern"][0]["score"] > found["shareholding_pattern"][1]["score"]
    assert found["kmp"][0]["pdf_index"] == 6
    assert found["esop"][0]["pdf_index"] == 6
    assert found["price"][0]["pdf_index"] == 6
    assert found["buyback_entitlement"][0]["pdf_index"] == 6
    assert "esop" in found["esop"][0]["matched_terms"]


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValueError, match="merger"):
        locate(_filing(), "merger")


def test_printed_page_prefers_the_footer_number():
    assert printed_page_from_text("12\nOffer\n\n— 99 —\n") == "99"
    assert printed_page_from_text("7\na\nb\nc\nd\n") == "7"
    assert printed_page_from_text("Chapter\nNo number on this page\n") is None


def test_normalise_folds_quotes_hyphens_and_whitespace():
    assert normalise("It\u2019s \u201cA\u201d") == "it's \"a\""
    assert normalise("A\u2018B\u2019") == "a'b'"
    assert normalise("A\u2010B\u2011C\u2012D\u2013E\u2014F") == "a-b-c-d-e-f"
    assert normalise("selling\nshareholders") == "selling shareholders"
    assert normalise("  a \t b  ") == "a b"


def test_apostrophe_and_hyphen_variants_match():
    text = "The promoters\u2019 contribution follows.\nShares are under lock\u2010in today."
    _score, holding = score_page(text, SECTIONS["promoter_holding"])
    _score, locked = score_page(text, SECTIONS["lock_in"])
    assert "promoters' contribution" in holding
    assert "lock-in" in locked


def test_phrase_split_across_lines_matches():
    text = "Details of selling\nshareholders"
    score, matched = score_page(text, SECTIONS["selling_shareholders"])
    assert score > 0
    assert matched[0] == "details of selling shareholders"


def test_shorter_term_inside_a_longer_one_is_not_counted():
    _score, matched = score_page("Details of selling shareholders", SECTIONS["selling_shareholders"])
    assert matched == ["details of selling shareholders"]


def test_repeated_term_does_not_outrank_a_structure_table():
    spam = _page(1, "1", ["selling shareholder"] * 40)
    table = _page(2, "2", list(STRUCTURE["selling_shareholders"]))
    found = locate([spam, table], "ipo")
    hits = found["selling_shareholders"]
    assert [hit["pdf_index"] for hit in hits[:2]] == [2, 1]
    assert hits[0]["score"] > hits[1]["score"]


def test_printed_table_shows_the_document_prefix(capsys):
    url = "https://example.test/offer.pdf"
    doc = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    _print_table(
        {
            "price": [
                {
                    "printed_page": "3",
                    "pdf_index": 3,
                    "score": 4,
                    "matched_terms": ["offer price"],
                    "source_url": url,
                }
            ]
        }
    )
    printed = capsys.readouterr().out
    assert doc in printed
    assert len(doc) == 8
    assert "offer price" in printed


def test_example_event_file_validates():
    spec = load_event_spec(ROOT_EVENT)
    assert spec.event_id == "example-ipo"
    assert spec.event_type == "ipo"
    assert spec.documents[0].doc_type == "rhp"


def test_issuer_shareholding_pattern_outranks_a_subsidiary_write_up():
    """A subsidiary's "Capital structure and shareholding pattern" block must not beat the issuer's own table."""
    from agents.locate import score_page
    from config.sections import SECTIONS

    subsidiary = ("Capital structure and shareholding pattern\nThe shareholding pattern of Alpha Sub is as follows:\n"
                  "1. Our Company 24,289 99.99%\nCapital structure and shareholding pattern\n"
                  "The shareholding pattern of Beta Sub is as follows:\n1. Our Company 9,999 99.99%")
    issuer = ("10. Shareholding Pattern of our Company\nThe table below presents the shareholding pattern of our "
              "Company as on the date of this offer document.")
    terms = SECTIONS["shareholding_pattern"]
    sub_score, sub_terms = score_page(subsidiary, terms)
    own_score, _ = score_page(issuer, terms)
    assert own_score > sub_score
    assert "capital structure and shareholding pattern" not in sub_terms  # counter-terms are not shown as matches
