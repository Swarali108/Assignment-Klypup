"""Recall fixes: table-row check, name on another page, roles defined after names, lock-in wording.

Strings and hand-built table rows only. No network, no model call, no PDF file.
"""

from __future__ import annotations

import agents.verify as verify_module
from agents.people import printed_role
from agents.rule_sources import find_rule_sources
from agents.verify import verify
from tools.tables import rows_confirm

URL = "https://example.test/offer.pdf"

# A pre-offer holding table as pdfplumber returns it: the wrapped name is one cell.
TABLE_ROWS = [
    ["Sr. No.", "Name of the Shareholder", "Number of Equity Shares", "% of pre-Offer capital"],
    ["Selling Shareholders", None, None, None],
    ["1.", "Ravi Sample", "2,269,500", "5.13"],
    ["2.", "Asha Family Trust (represented\nby Example Trustee & Services\nPrivate Limited)", "1,935,000", "4.37"],
    ["Total (C)", None, "24,291,000", "54.91"],
]
WRAPPED = "Asha Family Trust (represented by Example Trustee & Services Private Limited)"


def _page(index: int, text: str) -> dict:
    return {"pdf_index": index, "printed_page": str(index), "source_url": URL, "text": text}


def test_row_confirms_wrapped_name():
    assert rows_confirm(TABLE_ROWS, WRAPPED, "1,935,000")
    assert rows_confirm(TABLE_ROWS, "Asha Family Trust (represented by Example Trustee and Services Private Limited)", "19,35,000")
    # The value of another row, a part of the name, or a number only in the name cell never confirm.
    assert not rows_confirm(TABLE_ROWS, WRAPPED, "2,269,500")
    assert not rows_confirm(TABLE_ROWS, "Asha Family Trust", "1,935,000")
    assert not rows_confirm([["1.", "Fund 8", "4.37"]], "Fund 8", "8")
    assert not rows_confirm([["10.", "Ravi Sample", "1,000"]], "Ravi Sample", "10")


def test_rejected_amount_is_kept_by_table_row(tmp_path, monkeypatch):
    """Row binding fails on the flat text; the ruled table row confirms it, so the value stays."""
    text = (
        "2. Asha Family Trust (represented by Example 1,935,000 4.37 Trustee & Services Private Limited)\n"
        "3. Ravi Sample 2,269,500 5.13"
    )
    row = {
        "name_as_printed": WRAPPED,
        "shares_held_pre_offer": "1,935,000",
        "evidence": [
            {"field": "name_as_printed", "pdf_index": 22, "quote": "Asha Family Trust (represented by Example"},
            {"field": "shares_held_pre_offer", "pdf_index": 22, "quote": "Trustee & Services Private Limited)"},
        ],
    }
    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    import hashlib

    (tmp_path / f"{hashlib.sha256(URL.encode()).hexdigest()}.bin").write_bytes(b"%PDF-fixture")
    monkeypatch.setattr(verify_module, "row_confirms", lambda path, index, name, value: rows_confirm(TABLE_ROWS, name, value))
    kept, _orphans, rejections = verify([row], [_page(22, text)])
    assert kept[0]["shares_held_pre_offer"] == "1,935,000"
    assert not rejections
    item = [e for e in kept[0]["evidence"] if e["field"] == "shares_held_pre_offer"][0]
    assert item["verified_by"] == "table_row"


def test_without_cached_pdf_the_rejection_stays(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    row = {
        "name_as_printed": "Ravi Sample",
        "shares_held_pre_offer": "9,999",
        "evidence": [
            {"field": "name_as_printed", "pdf_index": 1, "quote": "Ravi Sample"},
            {"field": "shares_held_pre_offer", "pdf_index": 1, "quote": "Ravi Sample 2,269,500"},
        ],
    }
    kept, _orphans, rejections = verify([row], [_page(1, "Ravi Sample 2,269,500 5.13")])
    assert kept[0]["shares_held_pre_offer"] is None
    assert rejections[0]["reason"] == "value not in quote"


def test_name_ok_on_other_page_when_cited_page_garbled():
    pages = [
        _page(2, "Asha Example, Ravi Sample and Meera Testname are the Promoter Group (the \"Sellers\")."),
        _page(3, "1. Asha Example 2. Ravi Sample 3. MeeraTestnurrname"),
    ]
    row = {
        "name_as_printed": "Meera Testname",
        "evidence": [{"field": "name_as_printed", "pdf_index": 3, "quote": "3. MeeraTestnurrname"}],
    }
    kept, orphans, rejections = verify([row], pages)
    assert not orphans and not rejections
    item = kept[0]["evidence"][0]
    assert item["pdf_index"] == 2 and item["citation_corrected"] is True
    assert item["quote"] == "Meera Testname" and item["quote_as_cited"] == "3. MeeraTestnurrname"


def test_name_missing_from_every_page_is_still_rejected():
    row = {"name_as_printed": "Nobody Here", "evidence": [{"field": "name_as_printed", "pdf_index": 1, "quote": "x"}]}
    _kept, orphans, _rejections = verify([row], [_page(1, "Asha Example"), _page(2, "Ravi Sample")])
    assert orphans and orphans[0]["reason"] in ("name not on page", "quote not on page")


def test_role_defined_after_the_names_is_kept():
    cover = (
        "OFFER FOR SALE OF UP TO 300 EQUITY SHARES BY MEERA TESTNAME (THE “INVESTOR SELLING SHAREHOLDER”), "
        "UP TO 100 EQUITY SHARES BY ASHA EXAMPLE, UP TO 200 EQUITY SHARES BY RAVI SAMPLE "
        "(TOGETHER, THE “PROMOTER SELLING SHAREHOLDERS”)"
    )

    def row(name: str) -> dict:
        return {
            "name_as_printed": name,
            "role_as_printed": "PROMOTER SELLING SHAREHOLDERS",
            "evidence": [
                {"field": "name_as_printed", "pdf_index": 3, "quote": f"BY {name}"},
                {"field": "role_as_printed", "pdf_index": 3, "quote": "(TOGETHER, THE “PROMOTER SELLING SHAREHOLDERS”)"},
            ],
        }

    rows = [row("ASHA EXAMPLE"), row("RAVI SAMPLE"), row("MEERA TESTNAME")]
    kept, _orphans, rejections = verify(rows, [_page(3, cover)])
    roles = {item["name_as_printed"]: item["role_as_printed"] for item in kept}
    assert roles["ASHA EXAMPLE"] == roles["RAVI SAMPLE"] == "PROMOTER SELLING SHAREHOLDERS"
    # Her own group was defined before this one closes, so this role is not hers.
    assert roles["MEERA TESTNAME"] is None
    assert [r["row"] for r in rejections] == ["MEERA TESTNAME"]


def test_printed_role_from_any_section():
    assert printed_role({"waca": "Promoter Selling Shareholder"}, ("selling_shareholders",)) == "Promoter Selling Shareholder"
    assert printed_role({"waca": "A", "promoter_holding": "B"}, ("promoter_holding",)) == "B"
    assert printed_role({}, ("selling_shareholders",)) is None


def _rule_pages(text: str) -> list[dict]:
    return [_page(1, "Other text."), _page(2, text)]


def test_lockin_variant_eighteen_months():
    text = (
        "An aggregate of 20% of the fully diluted post-Offer capital held by our Promoters shall be locked-in "
        "for a period of eighteen months from the date of Allotment and the Equity Shares held by our Promoters "
        "in excess of Promoters' Contribution, shall be locked in for a period of six months, from the date of "
        "Allotment. The entire pre – Issue Equity Share capital will be locked-in for a period of 6 (six) months "
        "from the date of Allotment."
    )
    sources = find_rule_sources(_rule_pages(text))
    promoter = sources["minimum_promoters_contribution"]
    assert promoter["variant"] == "default"
    assert all(period["found"] for period in promoter["periods"].values())
    assert sources["pre_offer_capital"]["periods"]["pre-Offer capital"]["found"] is True


def test_lockin_three_year_main_board_wording():
    text = (
        "An aggregate of 20% of the post-Issue capital shall be locked in for a period of three years as minimum "
        "promoters' contribution from the date of Allotment, and the Promoters' shareholding in excess of 20% shall "
        "be locked in for a period of one year from the date of Allotment."
    )
    promoter = find_rule_sources(_rule_pages(text))["minimum_promoters_contribution"]
    assert promoter["variant"] == "three_year"
    assert all(period["found"] for period in promoter["periods"].values())


def test_ofs_listing_rule_needs_payment_wording():
    expenses = (
        "The Selling Shareholders agree that upon commencement of listing and trading of the Equity Shares, each "
        "Selling Shareholder shall reimburse our Company for such expenses directly from the Public Offer Account."
    )
    assert find_rule_sources(_rule_pages(expenses))["ofs_proceeds_at_listing"]["found"] is False
    paid = (
        "Upon receipt of the listing and trading approvals, the amounts lying in the Public Offer Account shall be "
        "transferred to the Selling Shareholders."
    )
    found = find_rule_sources(_rule_pages(paid))["ofs_proceeds_at_listing"]
    assert found["found"] is True and found["pdf_index"] == 2
