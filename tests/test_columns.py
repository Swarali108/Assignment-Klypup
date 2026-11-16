"""Column and Total-row blocks: a holder number under another field's header, or from a Total row, is rejected.

Hand-built table cells (text, left edge, right edge) only. No network, no model call, no PDF file.
Each table copies the shape of a real page; the names are made up.
"""

from __future__ import annotations

import hashlib

import pytest

import agents.verify as verify_module
from agents.verify import verify
from tools.tables import total_conflict, value_headers

URL = "https://example.test/offer.pdf"


def _cells(*texts: str, width: float = 100.0) -> list[tuple[str, float, float]]:
    """One table row: cells side by side, each `width` wide."""
    return [(text, index * width, (index + 1) * width) for index, text in enumerate(texts)]


@pytest.fixture
def table_page(tmp_path, monkeypatch):
    """Serve the given tables for any cited page, as if its PDF were cached."""
    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    (tmp_path / f"{hashlib.sha256(URL.encode()).hexdigest()}.bin").write_bytes(b"%PDF-fixture")

    def use(tables):
        monkeypatch.setattr(verify_module, "page_tables", lambda path, index: tables)

    return use


def _page(text: str, index: int = 5) -> dict:
    return {"pdf_index": index, "printed_page": str(index), "source_url": URL, "text": text}


def _row(name: str, field: str, value: str, quote: str, index: int = 5) -> dict:
    return {
        "name_as_printed": name,
        field: value,
        "evidence": [
            {"field": "name_as_printed", "pdf_index": index, "quote": name},
            {"field": field, "pdf_index": index, "quote": quote},
        ],
    }


# A seller table that prints the holding beside the shares offered (the SFC shape).
SELLERS = [[
    _cells("Name of the Selling Shareholder", "Number of Equity Shares held", "Maximum number of Offered Shares"),
    _cells("Meera Testname", "170,625", "50,000"),
]]
SELLERS_TEXT = "Name of the Selling Shareholder Number of Equity Shares held Maximum number of Offered Shares\nMeera Testname 170,625 50,000"


def test_holding_copied_into_shares_offered_is_rejected(table_page):
    table_page(SELLERS)
    row = _row("Meera Testname", "shares_offered", "170,625", "Meera Testname 170,625")
    kept, _orphans, rejections = verify([row], [_page(SELLERS_TEXT)])
    assert kept[0]["shares_offered"] is None
    assert rejections[0]["reason"] == "wrong column: number of equity shares held"


def test_value_under_its_own_header_is_kept(table_page):
    table_page(SELLERS)
    row = _row("Meera Testname", "shares_offered", "50,000", "Meera Testname 170,625 50,000")
    kept, _orphans, rejections = verify([row], [_page(SELLERS_TEXT)])
    assert kept[0]["shares_offered"] == "50,000"
    assert not rejections


# A buyback intention table with one promoter and a Total row (the Wipro shape).
INTENTION = [[
    _cells("Sl. No.", "Name of the Promoter", "Maximum No. of Equity"),
    _cells("", "", "Shares intended to be"),
    _cells("", "", "offered"),
    _cells("1.", "Ravi Sample", "26,20,91,650"),
    _cells("", "Total", "26,20,91,650"),
]]
INTENTION_TEXT = "Sl. No. Name of the Promoter Maximum No. of Equity Shares intended to be offered\n1. Ravi Sample 26,20,91,650\nTotal 26,20,91,650"


def test_holding_taken_from_intention_column_is_rejected(table_page):
    table_page(INTENTION)
    row = _row("Ravi Sample", "shares_held_pre_offer", "26,20,91,650", "Total 26,20,91,650")
    kept, _orphans, rejections = verify([row], [_page(INTENTION_TEXT)])
    assert kept[0]["shares_held_pre_offer"] is None
    assert rejections[0]["reason"].startswith("wrong column: maximum no. of equity shares intended to be offered")


def test_intention_from_the_same_column_is_kept(table_page):
    table_page(INTENTION)
    row = _row("Ravi Sample", "shares_intended", "26,20,91,650", "1. Ravi Sample 26,20,91,650")
    kept, _orphans, rejections = verify([row], [_page(INTENTION_TEXT)])
    assert kept[0]["shares_intended"] == "26,20,91,650"
    assert not rejections


# A share-history table: a holder's name heading, their transactions, then their own subtotal (the HD Fire shape).
HISTORY = [[
    _cells("Date of allotment", "Number of equity shares", "% of the pre-Offer equity share capital"),
    _cells("Asha Example", "", ""),
    _cells("September 14, 2006", "4,000", "0.05"),
    _cells("Total (E)", "7,458,000", "4.26"),
]]
HISTORY_TEXT = "Asha Example\nSeptember 14, 2006 4,000 0.05\nTotal (E) 7,458,000 4.26"


def test_own_subtotal_after_transactions_is_kept(table_page):
    table_page(HISTORY)
    row = _row("Asha Example", "shares_held_pre_offer", "7,458,000", "Total (E) 7,458,000 4.26")
    kept, _orphans, rejections = verify([row], [_page(HISTORY_TEXT)])
    assert kept[0]["shares_held_pre_offer"] == "7,458,000"
    assert not rejections


# A holdings table whose Total row sums every holder; the last holder's row prints their own figure.
HOLDINGS = [[
    _cells("Name", "Number of Equity Shares held"),
    _cells("Ravi Sample", "1,000,000"),
    _cells("Asha Example", "250,000"),
    _cells("Total", "1,250,000"),
]]
HOLDINGS_TEXT = "Name Number of Equity Shares held\nRavi Sample 1,000,000\nAsha Example 250,000\nTotal 1,250,000"


def test_total_row_bound_to_the_last_holder_is_rejected(table_page):
    table_page(HOLDINGS)
    row = _row("Asha Example", "shares_held_pre_offer", "1,250,000", "Total 1,250,000")
    kept, _orphans, rejections = verify([row], [_page(HOLDINGS_TEXT)])
    assert kept[0]["shares_held_pre_offer"] is None
    assert rejections[0]["reason"] == "total row, not this person's row"


def test_merged_pre_and_post_headings_cover_their_columns():
    """"Pre-Offer" and "Post-Offer" are each one cell across two columns."""
    tables = [[
        [("Name", 0, 100), ("Pre-Offer", 100, 300), None, ("Post-Offer", 300, 500), None],
        _cells("", "Number of Equity Shares", "%", "Number of Equity Shares", "%"),
        _cells("Ravi Sample", "864,000", "1.95", "819,000", "1.71"),
        _cells("Asha Example", "500,000", "1.13", "500,000", "1.04"),
    ]]
    assert value_headers(tables, "Ravi Sample", "819,000") == ["post-offer number of equity shares"]
    assert value_headers(tables, "Ravi Sample", "864,000") == ["pre-offer number of equity shares"]
    # A non-seller prints the same figure before and after: one of the two headers is the right one.
    assert len(value_headers(tables, "Asha Example", "500,000")) == 2


def test_post_offer_figure_is_not_a_pre_offer_holding(table_page):
    tables = [[
        [("Name", 0, 100), ("Pre-Offer", 100, 200), ("Post-Offer", 200, 300)],
        _cells("Ravi Sample", "864,000", "819,000"),
    ]]
    table_page(tables)
    row = _row("Ravi Sample", "shares_held_pre_offer", "819,000", "Ravi Sample 864,000 819,000")
    kept, _orphans, rejections = verify([row], [_page("Name Pre-Offer Post-Offer\nRavi Sample 864,000 819,000")])
    assert kept[0]["shares_held_pre_offer"] is None
    assert rejections[0]["reason"] == "wrong column: post-offer"


def test_cases_the_table_cannot_settle_are_left_alone():
    # A cell printing shares and rupees together (the Zetwerk shape) is not decided.
    joint = [[
        _cells("Name", "Number of Equity Shares held"),
        _cells("Ravi Sample", "14,230,672 Equity Shares of face value of ₹1 each aggregating to ₹2,148.83 million"),
    ]]
    assert value_headers(joint, "Ravi Sample", "14,230,672") == []
    # A table continued from the page before has no heading rows.
    continued = [[_cells("Ravi Sample", "170,625", "50,000")]]
    assert value_headers(continued, "Ravi Sample", "170,625") == []
    # A name that is only part of the cell's name is not this holder's row.
    assert value_headers(SELLERS, "Meera", "170,625") == []
    assert not total_conflict(HISTORY, "Asha Example", "7,458,000")


def test_header_naming_neither_field_changes_nothing(table_page):
    tables = [[_cells("Name", "Number of Equity Shares"), _cells("Ravi Sample", "170,625")]]
    table_page(tables)
    row = _row("Ravi Sample", "shares_offered", "170,625", "Ravi Sample 170,625")
    kept, _orphans, rejections = verify([row], [_page("Name Number of Equity Shares\nRavi Sample 170,625")])
    assert kept[0]["shares_offered"] == "170,625"
    assert not rejections


def test_without_cached_pdf_nothing_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(verify_module, "page_tables", lambda path, index: SELLERS)
    row = _row("Meera Testname", "shares_offered", "170,625", "Meera Testname 170,625")
    kept, _orphans, rejections = verify([row], [_page(SELLERS_TEXT)])
    assert kept[0]["shares_offered"] == "170,625"
    assert not rejections


def test_table_row_rescue_does_not_bring_back_a_wrong_column(table_page, monkeypatch):
    """The text check fails, the ruled row has the value, but under the holding column."""
    table_page(SELLERS)
    monkeypatch.setattr(verify_module, "row_confirms", lambda path, index, name, value: True)
    row = _row("Meera Testname", "shares_offered", "170,625", "Number of Equity Shares held")
    kept, _orphans, rejections = verify([row], [_page(SELLERS_TEXT)])
    assert kept[0]["shares_offered"] is None
    assert rejections[0]["reason"] == "wrong column: number of equity shares held"
