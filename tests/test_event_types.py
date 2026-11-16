"""Lock-in dates, recency, brief limits, and the buyback and OFS rules. No network, no model call."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from agents.brief import brief_problem, word_count
from agents.dates import add_months, parse_printed_date
from agents.people import build_people
from agents.rank import rank_people, recency_weight
from agents.rules_buyback import PRO_RATA, acceptance_ratio, participation
from agents.rules_ipo import lock_in_period
from agents.rules_ofs import FLOOR_LABEL
from agents.spec import EventSpec
from config.event_types import event_config

URL = "https://example.test/doc.pdf"


def _evidence(field: str, section: str, pdf_index: int = 3) -> dict:
    return {"field": field, "pdf_index": pdf_index, "printed_page": "12", "quote": "q",
            "section": section, "source_url": URL, "field_kept": True}


def _verified(allotted: str) -> dict:
    return {"status": "verified", "date_as_printed": allotted, "allotted_on": parse_printed_date(allotted).isoformat()}


@pytest.mark.parametrize(
    ("allotted", "months", "ends"),
    [
        ("March 9, 2026", 6, date(2026, 9, 9)),
        ("March 9, 2026", 18, date(2027, 9, 9)),
        ("August 31, 2026", 6, date(2027, 2, 28)),
        ("August 31, 2027", 6, date(2028, 2, 29)),
        ("January 31, 2026", 18, date(2027, 7, 31)),
        ("March 31, 2026", 18, date(2027, 9, 30)),
    ],
)
def test_lock_in_end_dates_including_month_ends(allotted, months, ends):
    assert add_months(parse_printed_date(allotted), months) == ends
    period = lock_in_period({"label": "x", "months": months, "share_of_retained": "all"}, _verified(allotted), date(2026, 11, 14))
    assert period["ends_on"] == ends.isoformat()
    assert f"+ {months} months" in period["working"]


def test_lock_in_says_locked_until_or_unlocked_since():
    allotment = _verified("March 9, 2026")
    six = lock_in_period({"label": "pre-Offer capital", "months": 6, "share_of_retained": "all"}, allotment, date(2026, 11, 14))
    assert six["status"] == "unlocked_since" and six["days_since"] == 66
    assert "unlocked since 9 Sep 2026" in six["display"]
    assert "allotment 9 Mar 2026 + 6 months = 9 Sep 2026" in six["display"]
    eighteen = lock_in_period({"label": "MPC", "months": 18, "share_of_retained": "unknown"}, allotment, date(2026, 11, 14))
    assert eighteen["status"] == "locked_until" and "locked until 9 Sep 2027" in eighteen["display"]
    unknown = lock_in_period({"label": "x", "months": 6, "share_of_retained": "all"}, {"status": "unknown", "reason": "allotment date not verified"}, date(2026, 11, 14))
    assert unknown["status"] == "end_unknown" and unknown["ends_on"] is None


@pytest.mark.parametrize(
    ("days", "weight"),
    [(0, "1.0"), (30, "1.0"), (31, "0.6"), (90, "0.6"), (91, "0.3"), (400, "0.3"), (None, "1.0")],
)
def test_recency_bands(days, weight):
    assert recency_weight(days)[0] == Decimal(weight)


def test_printed_dates_with_weekdays_and_ordinals():
    assert parse_printed_date("Tuesday June 9, 2026") == date(2026, 6, 9)
    assert parse_printed_date("21st April, 2026") == date(2026, 4, 21)
    assert parse_printed_date("21 st April, 2026") == date(2026, 4, 21)
    assert parse_printed_date("220d April,2026") is None


def _fields(**overrides) -> dict:
    fields = {"name": "Asha Example", "event_is": "recent", "event_age": "12 days ago",
              "amount": "up to ₹6.08 crore", "timing": "in hand"}
    fields.update(overrides)
    return fields


def test_a_line_over_25_words_fails_the_brief():
    long_line = " ".join(["word"] * 26)
    assert brief_problem(["one line", long_line, "three"], _fields()) == "line 2 has 26 words, limit 25"
    assert brief_problem(["one line", " ".join(["word"] * 25), "three"], _fields()) is None
    assert word_count("Asha Example sells shares", "Asha Example") == 2


def test_old_trigger_cannot_be_called_timely_and_proceeds_are_not_an_estimate():
    old = _fields(event_is="old", event_age="248 days ago")
    assert "timely" in brief_problem(["A call is timely.", "two", "three"], old)
    assert brief_problem(["It was 248 days ago.", "two", "three"], old) is None
    assert "estimate" in brief_problem(["Proceeds are an estimate.", "two", "three"], _fields())
    assert brief_problem(["Retained value is an estimate.", "two", "three"], _fields()) is None


def _buyback_people(rows: list[dict], offer: dict) -> dict:
    spec = SimpleNamespace(event_id="sample_buyback", event_type="buyback")
    return build_people({"rows": rows, "offer_facts": offer}, spec, ask=lambda *a: {"outcome": "different"},
                        as_of=date(2026, 6, 1))


def _buyback_offer() -> dict:
    return {"buyback_price": "680", "closing_date": "Tuesday June 02, 2026",
            "evidence": [_evidence("buyback_price", "buyback_terms", 1), _evidence("closing_date", "buyback_terms", 3)]}


def test_buyback_up_to_with_pro_rata_text():
    rows = [{"name_as_printed": "Asha Example", "role_as_printed": "Promoters", "shares_held_pre_offer": "1,00,000",
             "shares_intended": "10,000", "qualifier": "up to", "section": "promoter_intention",
             "evidence": [_evidence("name_as_printed", "promoter_intention"), _evidence("shares_intended", "promoter_intention")]}]
    person = _buyback_people(rows, _buyback_offer())["people"][0]
    figure = person["amounts"]["proceeds"]
    assert figure["display"] == "up to ₹0.68 crore; acceptance is pro rata, so actual may be lower"
    assert figure["label"] == PRO_RATA
    assert figure["working"] == "10,000 × ₹680 = ₹0.68 crore"
    assert person["timing"]["proceeds"]["when"] == "after the buyback closes on 2 Jun 2026"


def test_promoter_who_will_not_tender_has_no_amount():
    rows = [{"name_as_printed": "Asha Example", "role_as_printed": "Promoters", "shares_held_pre_offer": "1,00,000",
             "intention_as_printed": "have expressed their intention not to participate in the Buyback",
             "section": "promoter_intention",
             "evidence": [_evidence("name_as_printed", "promoter_intention"), _evidence("intention_as_printed", "promoter_intention")]}]
    result = _buyback_people(rows, _buyback_offer())
    person = result["people"][0]
    assert person["participation"] == "not tendering"
    assert person["amounts"]["proceeds"]["status"] == "not_tendering"
    assert "crore" not in str(person["amounts"])
    ranked = rank_people(result["people"], "buyback")
    assert ranked["callable"] == []
    entry = ranked["context"][0]
    assert entry["amount_display"] == "not tendering"
    assert entry["tier"] == "non_seller"
    assert "no money from this event" in entry["context_reason"]


def test_acceptance_ratio_and_participation_words():
    assert acceptance_ratio("1:4") == Decimal("0.25")
    assert acceptance_ratio("25%") == Decimal("0.25")
    assert acceptance_ratio("27 Equity Shares for every 866") is None
    assert participation({"intention_as_printed": "will not tender any shares"}) == "not tendering"
    assert participation({"shares_intended": "100"}) == "tendering"
    assert participation({}) == "unknown"


def test_ofs_floor_price_label_and_unknown_split():
    rows = [
        {"name_as_printed": "Example Holdings Limited", "role_as_printed": "Promoter Group", "shares_offered": "30,00,000",
         "qualifier": "up to", "section": "ofs_sellers",
         "evidence": [_evidence("name_as_printed", "ofs_sellers", 1), _evidence("shares_offered", "ofs_sellers", 1)]},
        {"name_as_printed": "Asha Example", "role_as_printed": "Promoter Group", "section": "ofs_sellers",
         "evidence": [_evidence("name_as_printed", "ofs_sellers", 2)]},
    ]
    offer = {"floor_price": "INR 66.00/- (Rupees Sixty Six Only)", "sale_date": "21st April, 2026",
             "total_shares_offered": "Up to 38,10,000", "settlement_as_printed": "settlement shall take place on T+1 Day",
             "evidence": [_evidence("floor_price", "ofs_terms", 6), _evidence("sale_date", "ofs_terms", 3),
                          _evidence("total_shares_offered", "ofs_terms", 2), _evidence("settlement_as_printed", "ofs_terms", 8)]}
    spec = SimpleNamespace(event_id="sample_ofs", event_type="ofs_stock_exchange")
    people = build_people({"rows": rows, "offer_facts": offer}, spec, ask=lambda *a: {"outcome": "different"},
                          as_of=date(2026, 4, 25))["people"]
    entity = next(p for p in people if p["holder_type"] == "entity")
    figure = entity["amounts"]["proceeds"]
    assert figure["display"] == f"up to ₹19.80 crore ({FLOOR_LABEL})"
    assert figure["working"] == "30,00,000 × ₹66.00 floor = ₹19.80 crore"
    timing = entity["timing"]["proceeds"]
    assert timing["when"] == "settles after the sale on 21 Apr 2026 (4 days ago)"
    assert timing["settlement_as_printed"] == "settlement shall take place on T+1 Day"
    person = next(p for p in people if p["holder_type"] == "person")
    assert person["amounts"]["proceeds"] == {
        "status": "unknown",
        "reason": "the notice prints up to 38,10,000 shares for all sellers together, not this seller's own shares",
    }


def test_event_spec_accepts_ofs_stock_exchange():
    spec = EventSpec.model_validate({"event_id": "sample_ofs", "event_type": "ofs_stock_exchange", "company": "Example Ltd",
                                     "documents": [{"url": URL, "doc_type": "announcement"}]})
    assert spec.event_type == "ofs_stock_exchange"
    assert event_config("ofs_stock_exchange")["whole_document"]["doc_types"] == ("announcement",)
    with pytest.raises(ValueError):
        event_config("acquisition")


def test_fresh_unlock_weighs_half_and_says_shares_not_cash():
    from agents.rank import triggers

    person = {
        "seller_status": "no",
        "amounts": {"proceeds": {"status": "not_applicable"}, "retained": {"status": "computed", "crore_high": "10.00"}},
        "timing": {"proceeds": {"status": "not_applicable"}, "retained": {"periods": [
            {"status": "unlocked_since", "days_since": 10, "ends_on": "2026-09-09", "label": "pre-Offer capital",
             "share_of_retained": "all"}]}},
    }
    found = triggers(person, Decimal("1.0"))
    assert found[0]["timing_weight"] == "0.5"
    assert found[0]["score"] == str(Decimal("10.00") * Decimal("1.0") * Decimal("0.5") * Decimal("1.0"))
    assert "shares, not cash" in found[0]["label"]


def test_entitlement_ratio_estimate_is_capped_and_labelled():
    from agents.rules_buyback import entitlement_ratio, proceeds

    assert entitlement_ratio("10 Equity Share for every 197 Equity Shares held on the Record Date") == Decimal(10) / 197
    assert entitlement_ratio("28 Equity Shares out of every 627") == Decimal(28) / 627
    assert entitlement_ratio("11 for every 5") is None
    assert entitlement_ratio("1:4") is None
    offer = {"buyback_price": "250", "entitlement_ratio": "10 Equity Shares for every 197 Equity Shares held",
             "evidence": [_evidence("buyback_price", "buyback_terms"), _evidence("entitlement_ratio", "buyback_terms")]}
    context = {"offer": offer, "price": Decimal(250), "ratio": None, "entitlement": entitlement_ratio(offer["entitlement_ratio"])}
    person = {"participation": "tendering", "shares_intended": "1,97,000", "shares_held_pre_offer": "19,70,000",
              "evidence": [_evidence("shares_intended", "promoter_intention"), _evidence("shares_held_pre_offer", "promoter_intention")]}
    figure = proceeds(person, context)
    # 19,70,000 held × 10/197 = 1,00,000 shares, below the 1,97,000 intended: ₹2.50 crore.
    assert figure["label"] == "estimate"
    assert figure["crore_low"] == figure["crore_high"] == "2.50"
    small = {**person, "shares_intended": "50,000"}
    assert proceeds(small, context)["crore_high"] == "1.25"


def test_offer_fact_kept_when_value_is_printed_but_quote_misses_it():
    from agents.verify import verify_offer

    page = {"pdf_index": 6, "printed_page": "6",
            "text": "“Buyback Price” Price at which Equity Shares will be bought back from the Eligible Shareholders "
                    "i.e. ₹ 250/- (Rupees Two Hundred and Fifty only) per fully paid up Equity Share, payable in cash."}
    facts = {"buyback_price": "₹ 250/- (Rupees Two Hundred and Fifty only)",
             "evidence": [{"field": "buyback_price", "pdf_index": 6, "printed_page": "6",
                           "quote": "Price at which Equity Shares will be bought back from the Eligible"}]}
    kept, rejected = verify_offer(facts, [page], ("buyback_price",))
    assert kept["buyback_price"] == facts["buyback_price"] and rejected == []
    assert kept["evidence"][-1]["quote"] == facts["buyback_price"]
    missing = {**facts, "buyback_price": "₹ 300/- (Rupees Three Hundred only)"}
    kept, rejected = verify_offer(missing, [page], ("buyback_price",))
    assert kept["buyback_price"] is None and rejected[0]["reason"] == "value not in quote"
