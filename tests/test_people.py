"""Identity, families, amounts and timing. No network, no API key, no model call."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from agents.extract import merge_rows
from agents.identity import family_groups, identity_tokens, resolve_identities
from agents.names import holder_type
from agents.people import build_people
from agents.rules_ipo import listing_basis, lock_in_rule, price_basis, proceeds, retained, timing

URL = "https://example.test/offer.pdf"
SPEC = SimpleNamespace(event_id="sample_ipo")


def _no_model(left, right, event_id):
    raise AssertionError(f"model called for {left['name']} / {right['name']}")


def _holders(*names: str) -> list[dict]:
    return [{"name": name, "holder_type": holder_type(name)[0], "quotes": [name]} for name in names]


def _evidence(field: str, section: str, pdf_index: int = 3) -> dict:
    return {
        "field": field,
        "pdf_index": pdf_index,
        "printed_page": "12",
        "quote": "q",
        "section": section,
        "source_url": URL,
        "field_kept": True,
    }


def _seller(**overrides) -> dict:
    person = {
        "name_as_printed": "Asha Example",
        "shares_offered": "45,000",
        "qualifier": "Up to",
        "shares_held_pre_offer": "864,000",
        "waca_per_share": "46.00",
        "role_as_printed": "Promoter Selling Shareholder",
        "evidence": [
            _evidence("name_as_printed", "selling_shareholders"),
            _evidence("shares_offered", "selling_shareholders"),
            _evidence("shares_held_pre_offer", "promoter_holding", 4),
            _evidence("waca_per_share", "waca", 5),
        ],
    }
    person.update(overrides)
    return person


def _offer(price: str | None = "₹1,352*") -> dict:
    return {
        "offer_price": price,
        "listing_date": "March 11, 2026",
        "evidence": [_evidence("offer_price", "announcement", 1), _evidence("listing_date", "announcement", 1)],
    }


def test_roman_numeral_and_hyphen_spellings_merge():
    result = resolve_identities(
        _holders("Xponentia Opportunities Fund - II", "Xponentia Opportunities Fund II"), "e", _no_model
    )
    assert result["groups"] == [[0, 1]]
    assert result["log"][0]["method"] == "same_tokens"
    assert identity_tokens("Fund - II") == ["fund", "2"]


def test_no_dot_spellings_merge():
    result = resolve_identities(_holders("SVS Trust No IV", "SVS Trust No. IV"), "e", _no_model)
    assert result["groups"] == [[0, 1]]
    assert result["log"][0]["outcome"] == "merge"


def test_holding_and_holdings_merge():
    result = resolve_identities(
        _holders("Example Global Holding Private Limited", "Example Global Holdings Private Limited"),
        "e",
        _no_model,
    )
    assert result["groups"] == [[0, 1]]


def test_two_shahs_stay_separate_and_share_a_family_group():
    result = resolve_identities(_holders("Atul Hiralal Shah", "Bakul Hiralal Shah"), "e", _no_model)
    assert result["groups"] == [[0], [1]]
    assert result["log"][0]["method"] == "different_first_name"
    families = family_groups(
        [
            {"name": "Atul Hiralal Shah", "holder_type": "person"},
            {"name": "Bakul Hiralal Shah", "holder_type": "person"},
        ]
    )
    assert families[0]["members"] == ["Atul Hiralal Shah", "Bakul Hiralal Shah"]
    assert "surname 'shah' and middle name 'hiralal'" in families[0]["reasons"][0]


def test_name_inside_another_name_is_a_family_not_a_merge():
    result = resolve_identities(_holders("Priyanka Manish Sharma", "Manish Sharma"), "e", _no_model)
    assert result["groups"] == [[0], [1]]
    families = family_groups(
        [
            {"name": "Priyanka Manish Sharma", "holder_type": "person"},
            {"name": "Manish Sharma", "holder_type": "person"},
        ]
    )
    assert families[0]["reasons"] == ["'Priyanka Manish Sharma' contains 'Manish Sharma'"]


def test_close_score_asks_the_model_once_and_unsure_is_flagged():
    asked = []

    def unsure(left, right, event_id):
        asked.append((left["name"], right["name"]))
        return {"outcome": "unsure", "reason": "cannot tell", "method": "llm"}

    result = resolve_identities(_holders("Example Growth Partners Fund", "Example Growth Partner Fund"), "e", unsure)
    assert len(asked) == 1
    assert result["groups"] == [[0], [1]]
    assert result["log"][0]["llm_outcome"] == "unsure"
    assert result["flags"][0] == ["identity with 'Example Growth Partner Fund' unsure"]


def test_holder_types():
    assert holder_type("Example Ventures LLP")[0] == "entity"
    assert holder_type("Example Kumar Sample HUF")[0] == "family_vehicle"
    assert holder_type("Example Family Trust")[0] == "family_vehicle"
    assert holder_type("Example S.A.R.L.")[0] == "entity"
    assert holder_type("Prof. Asha Example")[0] == "person"
    assert holder_type("Example")[0] == "unsure"
    assert holder_type("A91 Example")[0] == "unsure"


def test_up_to_45000_at_1352_is_up_to_6_08_crore():
    figure = proceeds(_seller(), price_basis(_offer()))
    assert figure["status"] == "computed"
    assert figure["display"].startswith("up to ₹6.08 crore")
    assert figure["working"] == "45,000 × ₹1,352 = ₹6.08 crore"
    assert figure["crore_high"] == "6.08"
    assert [item["field"] for item in figure["inputs"]] == ["shares_offered", "offer_price"]
    assert figure["inputs"][0]["evidence"][0]["link"] == f"{URL}#page=3"


def test_no_verified_price_makes_amounts_unknown():
    price = price_basis(_offer(price=None))
    assert price["kind"] == "unknown"
    assert proceeds(_seller(), price) == {"status": "unknown", "reason": "no verified offer price or price band"}
    kept = retained(_seller(), price)
    assert kept["status"] == "shares_only"
    assert "crore" not in str(kept)


def test_price_with_two_numbers_is_not_guessed():
    assert price_basis(_offer(price="₹1,352 per Equity Share of face value ₹10"))["kind"] == "unknown"


def test_price_band_gives_a_range_and_retained_is_an_estimate():
    band = {
        "price_band_low": "1,287",
        "price_band_high": "1,352",
        "evidence": [_evidence("price_band_low", "price"), _evidence("price_band_high", "price")],
    }
    price = price_basis(band)
    assert price["kind"] == "price_band"
    assert proceeds(_seller(), price)["working"] == "45,000 × ₹1,287 to ₹1,352 = ₹5.79 to ₹6.08 crore"
    kept = retained(_seller(), price_basis(_offer()))
    assert kept["label"] == "estimate, valued at offer price"
    assert kept["working"] == "(864,000 − 45,000) × ₹1,352 = ₹110.73 crore"
    assert kept["shares_display"] == "at least 819,000 shares, if all offered shares are sold"


def test_role_with_no_sourced_rule_gives_unknown_timing():
    listing = {"status": "unknown", "reason": "listing date not verified"}
    assert lock_in_rule("Anchor Investor") is None
    assert timing(_seller(role_as_printed="Anchor Investor"), listing)["retained"]["status"] == "unknown"
    assert timing(_seller(role_as_printed=None), listing)["retained"]["reason"] == "no role printed"
    assert timing(_seller(), listing)["proceeds"]["status"] == "unknown"
    assert lock_in_rule("Promoter Group Selling Shareholder")["id"] == "pre_offer_capital"
    assert lock_in_rule("Promoter Selling Shareholder")["id"] == "minimum_promoters_contribution"
    assert lock_in_rule("Promoters")["id"] == "minimum_promoters_contribution"


def test_build_people_merges_spellings_and_keeps_roles_per_section():
    rows = merge_rows(
        [
            {
                "name_as_printed": "Example Opportunities Fund - II",
                "role_as_printed": "Investor Selling Shareholders",
                "shares_offered": "45,000",
                "qualifier": "Up to",
                "section": "selling_shareholders",
                "evidence": [
                    _evidence("name_as_printed", "selling_shareholders"),
                    _evidence("shares_offered", "selling_shareholders"),
                ],
            },
            {
                "name_as_printed": "Example Opportunities Fund II",
                "shares_held_pre_offer": "100,000",
                "role_as_printed": "Selling Shareholders",
                "section": "promoter_holding",
                "evidence": [
                    _evidence("name_as_printed", "promoter_holding", 4),
                    _evidence("shares_held_pre_offer", "promoter_holding", 4),
                ],
            },
            {
                "name_as_printed": "Example Opportunities Fund II",
                "shares_held_pre_offer": "100,000",
                "section": "shareholding_pattern",
                "evidence": [
                    _evidence("name_as_printed", "shareholding_pattern", 6),
                    _evidence("shares_held_pre_offer", "shareholding_pattern", 6),
                ],
            },
        ]
    )
    result = build_people({"rows": rows, "offer_facts": _offer()}, SPEC, ask=_no_model, as_of=date(2026, 3, 1))
    assert result["counts"]["people"] == 1
    person = result["people"][0]
    assert person["names_as_printed"] == ["Example Opportunities Fund - II", "Example Opportunities Fund II"]
    assert person["role_as_printed"] == "Investor Selling Shareholders"
    assert person["role_by_section"] == {
        "selling_shareholders": "Investor Selling Shareholders",
        "promoter_holding": "Selling Shareholders",
    }
    assert person["conflicts"] == {}
    assert person["confidence"]["level"] == "high"
    assert person["timing"]["proceeds"]["status"] == "at_listing"
    assert person["timing"]["retained"]["rule"] == "pre_offer_capital"
    assert person["amounts"]["retained"]["shares"] == "55000"


def test_merged_conflict_is_kept_and_lowers_confidence():
    rows = merge_rows(
        [
            {**_seller(), "section": "selling_shareholders"},
            {
                "name_as_printed": "Asha Example",
                "shares_held_pre_offer": "900,000",
                "section": "shareholding_pattern",
                "evidence": [_evidence("shares_held_pre_offer", "shareholding_pattern", 6)],
            },
        ]
    )
    person = build_people({"rows": rows, "offer_facts": _offer()}, SPEC, ask=_no_model)["people"][0]
    assert person["shares_held_pre_offer"] is None
    assert person["conflicts"]["shares_held_pre_offer"] == ["864,000", "900,000"]
    assert person["amounts"]["retained"]["status"] == "unknown"
    assert person["confidence"]["level"] == "medium"
    assert "pre-offer holdings differ across sections" in person["confidence"]["reasons"]


@pytest.mark.parametrize("name", ["Example Ventures LLP", "Example Capital Fund I"])
def test_entities_are_never_put_in_family_groups(name):
    people = [{"name": name, "holder_type": "entity"}, {"name": "Other " + name, "holder_type": "entity"}]
    assert family_groups(people) == []


def test_seller_whose_seller_row_failed_gets_unknown_not_full_holding():
    rows = merge_rows(
        [
            {
                "name_as_printed": "Example Opportunities Fund II",
                "shares_held_pre_offer": "3,000",
                "role_as_printed": "Selling Shareholders",
                "section": "promoter_holding",
                "evidence": [
                    _evidence("name_as_printed", "promoter_holding", 4),
                    _evidence("shares_held_pre_offer", "promoter_holding", 4),
                ],
            }
        ]
    )
    failed = [{"name_as_printed": "Example Opportunities Fund - II", "section": "selling_shareholders"}]
    person = build_people(
        {"rows": rows, "unattributed": failed, "offer_facts": _offer()}, SPEC, ask=_no_model
    )["people"][0]
    assert person["seller_status"] == "unverified"
    assert person["amounts"]["proceeds"]["status"] == "unknown"
    assert person["amounts"]["retained"]["status"] == "unknown"
    assert person["timing"]["proceeds"]["status"] == "unknown"
    assert person["flags"]


def test_listing_date_in_the_past_means_money_in_hand():
    listing = listing_basis(_offer(), as_of=date(2026, 11, 14))
    assert listing["listed_on"] == "2026-03-11" and listing["past"] is True
    assert timing(_seller(), listing)["proceeds"]["status"] == "in_hand"
    ahead = listing_basis(_offer(), as_of=date(2026, 3, 1))
    assert timing(_seller(), ahead)["proceeds"]["status"] == "at_listing"
    odd = listing_basis({**_offer(), "listing_date": "the eleventh of March"}, as_of=date(2026, 11, 14))
    assert odd["listed_on"] is None and odd["past"] is False


def test_unknown_price_still_shows_the_verified_shares_offered():
    from agents.rules_ipo import amount_display

    person = _seller(seller_status="verified")
    person["amounts"] = {"proceeds": proceeds(person, price_basis(_offer(price=None))), "retained": {"status": "unknown"}}
    assert amount_display(person) == "up to 45,000 shares offered; value unknown: no verified offer price or price band"
    unverified = _seller(seller_status="verified", shares_offered=None)
    unverified["amounts"] = {"proceeds": {"status": "unknown", "reason": "shares offered not verified"}, "retained": {}}
    assert amount_display(unverified) == "unknown: shares offered not verified"


def test_timetable_date_gives_scheduled_timing_and_an_announcement_wins():
    from decimal import Decimal

    from agents.rank import triggers

    scheduled_only = {"listing_date_scheduled": "On or before Friday, November 06, 2026",
                      "evidence": [_evidence("listing_date_scheduled", "timetable", 71)]}
    listing = listing_basis(scheduled_only, as_of=date(2026, 11, 15))
    assert listing["status"] == "scheduled" and listing["listed_on"] == "2026-11-06" and listing["days_since"] == 9
    proceeds_timing = timing(_seller(seller_status="verified"), listing)["proceeds"]
    assert proceeds_timing["status"] == "scheduled"
    assert proceeds_timing["when"] == ("listing scheduled for On or before Friday, November 06, 2026 per the offer "
                                       "document's timetable; not confirmed by a listing notice")
    person = _seller(seller_status="verified")
    person["amounts"] = {"proceeds": {"status": "computed", "crore_high": "5.00"}, "retained": {}}
    person["timing"] = {"proceeds": proceeds_timing, "retained": {}}
    found = triggers(person, Decimal("1.0"))[0]
    # A timetable date that has passed counts as past: weight listed_per_timetable, not scheduled.
    assert (found["timing_weight"], found["recency_weight"], found["days_since"]) == ("0.9", "1.0", 9)
    assert found["timing_status"] == "listed_per_timetable"
    both = {**scheduled_only, "listing_date": "March 11, 2026",
            "evidence": scheduled_only["evidence"] + [_evidence("listing_date", "announcement", 1)]}
    assert listing_basis(both, as_of=date(2026, 11, 15))["status"] == "verified"
