"""Quote and name matching for page layouts any offer document can have. Strings only, no network.

- interleaved table cells: a wrapped neighbouring cell's words sit inside the quote;
- footnote marks on the page that the quote leaves out ("1,150,000$");
- a text layer that lost its spaces ("EQUITYSHARESOFFACEVALUE").
"""

from __future__ import annotations

from agents.verify import _find_quote_spans, _locate_name_all, normalise, verify


def _row(name: str, shares: str, shares_quote: str, name_quote: str | None = None, page: int = 1) -> dict:
    return {"name_as_printed": name, "shares_offered": shares,
            "evidence": [{"field": "name_as_printed", "pdf_index": page, "printed_page": "", "quote": name_quote or name},
                         {"field": "shares_offered", "pdf_index": page, "printed_page": "", "quote": shares_quote}]}


INTERLEAVED = ("NAME OF THE SELLING SHAREHOLDER TYPE NUMBER OF SHARES Promoter Selling 4,329,004 Equity Shares^ of "
               "face value of ₹1 2.35 Asha Example Rao Shareholder each aggregating to ₹ 3,000.00 million^ Investor "
               "Selling 9,379,509 Equity Shares^ of face value of ₹1 114.15 Widget Holdings Ltd Shareholder each "
               "aggregating to ₹ 6,500.00 million^ ^Subject to finalization of Basis of Allotment.")


def test_interleaved_cells_pass_and_bind_to_the_name_inside_them():
    rows = [_row("Asha Example Rao", "4,329,004",
                 "4,329,004 Equity Shares^ of face value of ₹1 each aggregating to ₹ 3,000.00 million^"),
            _row("Widget Holdings Ltd", "9,379,509",
                 "9,379,509 Equity Shares^ of face value of ₹1 each aggregating to ₹ 6,500.00 million^")]
    kept, unattributed, rejections = verify(rows, [{"pdf_index": 1, "text": INTERLEAVED}])
    assert not unattributed and not rejections
    assert [row["shares_offered"] for row in kept] == ["4,329,004", "9,379,509"]


def test_a_quote_split_by_too_many_foreign_words_still_fails():
    page = "4,329,004 Equity Shares of face value " + "lorem " * 12 + "of ₹1 each aggregating to ₹ 3,000.00 million"
    assert _find_quote_spans("4,329,004 Equity Shares of face value of ₹1 each", normalise(page)) == []


def test_a_short_quote_never_matches_with_gaps():
    assert _find_quote_spans("Equity Shares", normalise("Equity of the Shares")) == []


MERGED = ("OFFER FOR SALE (THE“OFFER”)OF1,150,000$EQUITYSHARESOFFACEVALUEOF₹2EACHAGGREGATINGTO₹805.00MILLION"
          "BYASHAKONDAEXAMPLE,580,000$ EQUITYSHARESOFFACEVALUEOF₹2EACHAGGREGATINGTO₹406.00MILLIONBYRAVIKUMARRAO,"
          "230,000$EQUITYSHARESOFFACEVALUEOF₹2EACHAGGREGATINGTO₹161.00 MILLIONBYCELIA D’SOUZA(COLLECTIVELY)")


def test_marks_and_lost_spaces_on_the_page_do_not_reject_true_quotes():
    rows = [_row("ASHA KONDA EXAMPLE", "1,150,000",
                 "1,150,000 EQUITY SHARES OF FACE VALUE OF ₹2 EACH AGGREGATING TO ₹805.00 MILLION BY ASHA KONDA EXAMPLE",
                 name_quote="BY ASHA KONDA EXAMPLE"),
            _row("RAVI KUMAR RAO", "580,000",
                 "580,000 EQUITY SHARES OF FACE VALUE OF ₹2 EACH AGGREGATING TO ₹406.00 MILLION BY RAVI KUMAR RAO",
                 name_quote="580,000 EQUITY SHARES OF FACE VALUE OF ₹2 EACH AGGREGATING TO ₹406.00 MILLION BY RAVI KUMAR RAO")]
    kept, unattributed, rejections = verify(rows, [{"pdf_index": 1, "text": MERGED}])
    assert not unattributed, unattributed
    assert [row["shares_offered"] for row in kept] == ["1,150,000", "580,000"] and not rejections


def test_a_name_without_spaces_is_found_only_where_the_page_lost_its_spaces():
    assert _locate_name_all("RAVI KUMAR RAO", MERGED)
    spaced = "The shares of Raviku Marrao and others are offered by the selling shareholders named below in full."
    assert _locate_name_all("Ravi Kumar Rao", spaced) == []


def test_a_wrong_number_in_an_interleaved_quote_still_fails():
    rows = [_row("Asha Example Rao", "4,329,005",
                 "4,329,005 Equity Shares^ of face value of ₹1 each aggregating to ₹ 3,000.00 million^")]
    kept, _unattributed, rejections = verify(rows, [{"pdf_index": 1, "text": INTERLEAVED}])
    assert kept[0]["shares_offered"] is None and rejections[0]["reason"] == "quote not on page"


def test_a_name_quote_wrapped_in_a_table_cell_passes():
    page = "Name of holder Shares % Pre-offer Example Industries 5,937,841,645 89.58 N.A.^ Limited *As certified"
    rows = [{"name_as_printed": "Example Industries Limited", "shares_held_pre_offer": "5,937,841,645",
             "evidence": [{"field": "name_as_printed", "pdf_index": 1, "printed_page": "", "quote": "Example Industries Limited"},
                          {"field": "shares_held_pre_offer", "pdf_index": 1, "printed_page": "",
                           "quote": "Example Industries 5,937,841,645"}]}]
    kept, unattributed, _rejections = verify(rows, [{"pdf_index": 1, "text": page}])
    assert not unattributed and kept[0]["shares_held_pre_offer"] == "5,937,841,645"


def test_a_merged_name_with_an_apostrophe_is_found():
    assert _locate_name_all("CELIA D'SOUZA", MERGED)
