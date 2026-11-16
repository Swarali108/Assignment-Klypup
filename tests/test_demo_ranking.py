"""RM call tiers, the context list, display text and digit-safe briefs. No network, no model call."""

from __future__ import annotations

import re
from datetime import date

from agents import rules_ipo, rules_ofs
from agents.brief import brief_for
from agents.extract import merge_rows
from agents.people import build_people
from agents.rank import rank_people
from tests.test_rank_brief_report import _evidence, _offer


def _cash(crore: str) -> dict:
    return {"status": "computed", "crore_low": crore, "crore_high": crore, "display": f"₹{crore} crore",
            "working": f"shares × price = ₹{crore} crore"}


def _kept(crore: str) -> dict:
    return {**_cash(crore), "display": f"₹{crore} crore (estimate, valued at offer price)", "shares": "1000"}


def _in_hand(days: int) -> dict:
    return {"status": "in_hand", "when": f"in hand since the listing ({days} days ago)", "days_since": days}


def _person(name: str, *, holder: str = "person", seller: str = "no", proceeds: dict | None = None,
            proceeds_timing: dict | None = None, retained: dict | None = None, retained_timing: dict | None = None,
            participation: str | None = None, **extra) -> dict:
    person = {
        "person_id": "p_" + name.lower().replace(" ", "_"),
        "name_as_printed": name,
        "name_clean": name.lower(),
        "holder_type": holder,
        "role_as_printed": "Promoters",
        "seller_status": seller,
        "shares_offered": None,
        "qualifier": None,
        "shares_held_pre_offer": None,
        "confidence": {"level": "medium", "reasons": []},
        "amounts": {"proceeds": proceeds or {"status": "not_applicable", "reason": "not in the seller table"},
                    "retained": retained or {"status": "unknown", "reason": "pre-offer holding not verified"}},
        "timing": {"proceeds": proceeds_timing or {"status": "not_applicable", "reason": "not in the seller table"},
                   "retained": retained_timing or {"status": "locked_in", "period": "6 months", "display": "locked"}},
        "family_group": None,
        "flags": [],
    }
    if participation:
        person["participation"] = participation
    person.update(extra)
    return person


def _names(entries: list[dict]) -> list[str]:
    return [entry["name_as_printed"] for entry in entries]


def test_cash_now_outranks_holding():
    seller = _person("Asha Seller", seller="verified", proceeds=_cash("10.00"), proceeds_timing=_in_hand(20))
    holder = _person("Bina Holder", retained=_kept("100.00"))
    ranked = rank_people([holder, seller])
    assert _names(ranked["callable"]) == ["Asha Seller", "Bina Holder"]
    assert [entry["call_tier"] for entry in ranked["callable"]] == ["cash_now", "holding"]
    assert ranked["callable"][0]["call_tier_label"] == "Cash in hand"
    assert ranked["callable"][0]["rank_reasons"][0].startswith("Cash in hand:")


def test_buyback_non_tendering_goes_to_context():
    no = _person("Chetan Promoter", participation="not tendering",
                 proceeds={"status": "not_tendering", "display": "not tendering", "reason": "states: not to participate"})
    maybe = _person("Divya Holder", participation="unknown", proceeds={"status": "unknown", "reason": "tender intention not verified"},
                    proceeds_timing={"status": "unknown", "reason": "no verified payment or closing date"})
    ranked = rank_people([no, maybe], "buyback")
    assert _names(ranked["context"]) == ["Chetan Promoter"]
    assert "no money from this event" in ranked["context"][0]["context_reason"]
    assert _names(ranked["callable"]) == ["Divya Holder"]


def test_unknown_amount_sorts_below_known_in_tier():
    unknown = _person("Aarav Unknown", seller="verified", proceeds={"status": "unknown", "reason": "price not verified"},
                      proceeds_timing=_in_hand(5))
    known = _person("Zoya Known", seller="verified", proceeds=_cash("0.50"), proceeds_timing=_in_hand(5))
    ranked = rank_people([unknown, known])
    assert _names(ranked["callable"]) == ["Zoya Known", "Aarav Unknown"]
    assert {entry["call_tier"] for entry in ranked["callable"]} == {"cash_now"}
    assert ranked["callable"][1]["amount_known"] is False


def test_past_scheduled_listing_counts_as_past():
    as_of = date(2026, 11, 15)
    offer = {"listing_date_scheduled": "Tuesday, November 03, 2026", "evidence": []}
    listing = rules_ipo.listing_basis(offer, as_of)
    assert listing["status"] == "scheduled" and listing["days_since"] == 12
    person = _person("Esha Seller", seller="verified", proceeds=_cash("5.00"), shares_offered="10,000")
    person["timing"]["proceeds"] = rules_ipo.timing(person, listing, as_of=as_of)["proceeds"]
    entry = rank_people([person])["callable"][0]
    assert entry["call_tier"] == "cash_now"
    assert entry["call_tier_label"] == "Cash in hand"
    assert "scheduled" not in entry["timing_display"].lower()
    assert "3 Nov 2026" in entry["timing_display"] and "12 days ago" in entry["timing_display"]
    assert entry["timing_display_status"] == "listed_per_timetable"


def test_fund_like_unsure_holder_is_entity():
    fund = _person("Lightspeed Venture Partners Select IV Mauritius", holder="unsure", seller="verified",
                   proceeds=_cash("40.00"), proceeds_timing=_in_hand(10))
    person = _person("Farah Seller", seller="verified", proceeds=_cash("1.00"), proceeds_timing=_in_hand(10))
    ranked = rank_people([fund, person])
    assert _names(ranked["entities"]) == ["Lightspeed Venture Partners Select IV Mauritius"]
    assert _names(ranked["callable"]) == ["Farah Seller"]


def test_promoter_unlock_with_unknown_split_not_zero():
    unlocked = {"status": "partly_unlocked", "display": "promoter shares above the 20%: unlocked since 9 Sep 2026",
                "periods": [{"label": "promoter shares above the 20%", "months": 6, "share_of_retained": "unknown",
                             "ends_on": "2026-09-09", "status": "unlocked_since", "days_since": 67}]}
    promoter = _person("Gopal Promoter", retained=_kept("966.75"), retained_timing=unlocked)
    small = _person("Aditi Small", retained=_kept("0.24"))
    old_seller = _person("Abhay Old Seller", seller="verified", proceeds=_cash("0.24"), proceeds_timing=_in_hand(249))
    ranked = rank_people([small, old_seller, promoter])
    first = ranked["callable"][0]
    assert first["name_as_printed"] == "Gopal Promoter"
    assert first["call_tier"] == "unlock" and first["call_tier_label"] == "Shares just unlocked"
    assert float(first["score"]) > 0
    assert "not printed" in first["rank_reasons"][0]
    tiers = {entry["name_as_printed"]: entry["call_tier"] for entry in ranked["callable"]}
    assert tiers["Aditi Small"] == "holding" and tiers["Abhay Old Seller"] == "holding"


def test_amount_display_no_doubled_words():
    person = _person("Hari Seller", seller="verified", shares_offered="Up to 3,702,694 Equity Shares", qualifier="Up to",
                     proceeds={"status": "unknown", "reason": "no verified offer price or price band"})
    texts = [rules_ipo.amount_display(person), rules_ipo.why_money(person), rules_ofs.why_money(person)]
    ofs_seller = {**person, "shares_offered": None}
    texts.append(rules_ofs.proceeds(ofs_seller, {"floor": 66, "total": "Up to 38,10,000 Equity Shares", "offer": {}})["reason"])
    for text in texts:
        lowered = text.lower()
        assert "up to up to" not in lowered and "shares shares" not in lowered, text
        assert "equity shares shares" not in lowered, text
    assert "up to 3,702,694 shares" in texts[0]
    assert "up to 38,10,000 shares" in texts[3]


def _brief_person() -> tuple[dict, dict]:
    rows = merge_rows([
        {"name_as_printed": "Kiran Example", "role_as_printed": "Promoter Selling Shareholder",
         "shares_offered": "42,000", "section": "selling_shareholders",
         "evidence": [_evidence("name_as_printed", "selling_shareholders"),
                      _evidence("shares_offered", "selling_shareholders")]},
        {"name_as_printed": "Kiran Example", "shares_held_pre_offer": "71,400", "section": "promoter_holding",
         "evidence": [_evidence("name_as_printed", "promoter_holding", 4),
                      _evidence("shares_held_pre_offer", "promoter_holding", 4)]},
    ])
    no_model = lambda *args: (_ for _ in ()).throw(AssertionError("no model call expected"))
    people = build_people({"rows": rows, "offer_facts": _offer()}, type("Spec", (), {"event_id": "sample_ipo"})(),
                          no_model, as_of=date(2026, 3, 20))["people"]
    person = people[0]
    return person, rank_people(people)["callable"][0]


def test_brief_digits_come_from_fields():
    person, entry = _brief_person()
    assert person["amounts"]["retained"]["shares"] == "29400"
    # 42,000 is a real value (shares offered), so a "number is somewhere in the fields" check would pass it.
    wrong = lambda fields, person_id, event_id, **retry: [
        "Kiran Example sells in the offer for sale.", "They retain 42,000 shares after the sale.", "Paid at listing."]
    brief = brief_for(person, entry, "sample_ipo", wrong)
    assert brief["brief_source"] == "template"
    assert "42,000" in brief["fallback_reason"]
    assert "retain 42,000" not in " ".join(brief["lines"])

    placeholders = lambda fields, person_id, event_id, **retry: [
        "{name} sells {shares_offered} in the offer for sale.", "They keep {retained_shares} after the sale.",
        "Proceeds of {proceeds} arrive {timing}."]
    brief = brief_for(person, entry, "sample_ipo", placeholders)
    assert brief["brief_source"] == "llm", brief["attempts"]
    assert brief["lines"][1] == "They keep 29,400 shares after the sale."
    values = " ".join(brief["placeholders"].values())
    for number in re.findall(r"\d[\d,.]*\d|\d", " ".join(brief["lines"])):
        assert number in values, number
