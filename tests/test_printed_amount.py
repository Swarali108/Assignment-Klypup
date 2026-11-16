"""Computed proceeds against the amount the document prints for the same shares. No network."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agents.figures import rupees_from_printed
from agents.rules_ipo import proceeds

URL = "https://example.org/offer.pdf"


def _person(shares: str, printed: str | None) -> dict:
    evidence = [{"field": "shares_offered", "pdf_index": 3, "printed_page": "1", "source_url": URL, "quote": shares,
                 "field_kept": True}]
    if printed:
        evidence.append({"field": "amount_as_printed", "pdf_index": 9, "printed_page": "7", "source_url": URL,
                         "quote": printed, "field_kept": True})
    return {"name_as_printed": "Asha Example", "seller_status": "verified", "shares_offered": shares,
            "amount_as_printed": printed, "qualifier": None, "evidence": evidence}


PRICE = {"kind": "offer_price", "low": Decimal("700"), "high": Decimal("700"), "inputs": [], "caveats": []}


@pytest.mark.parametrize(("text", "rupees"), [
    ("aggregating to ₹ 3,000.00 million^", Decimal("3000000000")), ("₹805.00MILLION", Decimal("805000000")),
    ("₹ 25.5 crore", Decimal("255000000")), ("₹ 1,250 lakh", Decimal("125000000")), ("₹ 2.1 billion", Decimal("2100000000")),
    ("₹ [●] million", None), ("2,000 shares aggregating to ₹ 5 million", None), ("₹ 5", None),
])
def test_printed_amounts_convert_to_rupees(text, rupees):
    assert rupees_from_printed(text) == rupees


def test_a_printed_amount_within_a_tenth_of_a_percent_matches():
    figure = proceeds(_person("1,150,000", "aggregating to ₹805.00 million"), PRICE)
    assert figure["printed_check"]["status"] == "matches"
    assert figure["printed_check"]["text"] == "matches the document's printed amount (p. 7)"
    assert not [c for c in figure["caveats"] if c.get("kind") == "printed_amount"]
    assert any(item["field"] == "amount_as_printed" for item in figure["inputs"])


def test_a_different_printed_amount_becomes_a_caveat_with_both_figures():
    figure = proceeds(_person("1,150,000", "aggregating to ₹800.00 million"), PRICE)
    check = figure["printed_check"]
    assert check["status"] == "differs" and check["difference_pct"] == "+0.63"
    caveat = next(c for c in figure["caveats"] if c.get("kind") == "printed_amount")
    assert "₹80.00 crore" in caveat["text"] and "₹80.50 crore" in caveat["text"] and "+0.63%" in caveat["text"]
    assert "p. 7" in caveat["text"] and "p. 1" in caveat["text"]


def test_no_comparison_at_a_price_band_or_without_a_printed_amount():
    band = {**PRICE, "kind": "price_band", "low": Decimal("650"), "high": Decimal("700")}
    assert proceeds(_person("1,150,000", "aggregating to ₹805.00 million"), band)["printed_check"]["status"] == "not_compared"
    assert "printed_check" not in proceeds(_person("1,150,000", None), PRICE)


def test_a_small_amount_matches_within_the_rounding_of_its_printed_figure():
    price = {**PRICE, "low": Decimal("151"), "high": Decimal("151")}
    figure = proceeds(_person("100", "aggregating to ₹0.02 million"), price)
    assert figure["printed_check"]["status"] == "matches"


def test_the_report_lists_a_mismatch_caveat_with_its_page_link():
    from agents.report import _figure_line

    figure = proceeds(_person("1,150,000", "aggregating to ₹800.00 million"), PRICE)
    line = _figure_line("Proceeds", figure)
    assert "+0.63% different" in line and "#page=9" in line
