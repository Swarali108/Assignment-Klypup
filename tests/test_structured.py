"""Structured signal events (block deals, insider sales): records -> people -> ranked -> briefs -> report.

Tier 1: no network, no API key. Fixtures in tests/fixtures/signals/ are built by hand from the shared
record schema; names and companies in them are made up.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import run
from agents import brief as brief_module
from agents import rules_structured as rs
from agents.rank import rank_people
from agents.spec import EventSpec
from tools.llm import LLMError

FIXTURES = Path(__file__).parent / "fixtures" / "signals"
AS_OF = date(2026, 11, 15)


def _records(kind: str) -> list[dict]:
    return json.loads((FIXTURES / f"{kind}.json").read_text(encoding="utf-8"))["records"]


def _event(kind: str, event_id: str) -> tuple[EventSpec, dict]:
    """The grouped event with this id and its people.json, as of AS_OF."""
    spec = EventSpec.model_validate(next(s for s in rs.group_records(_records(kind)) if s["event_id"] == event_id))
    records, meta = rs.load_records(FIXTURES / f"{kind}.json", spec.records)
    return spec, rs.build_people(spec, records, meta, as_of=AS_OF)


def _person(doc: dict, person_id: str) -> dict:
    return next(p for p in doc["people"] if p["person_id"] == person_id)


WEEK = "example_industries_block_deal_2026w46"


# ---------- amounts ----------

def test_amount_is_quantity_times_price_in_decimal():
    value, how, flag = rs.record_value({"quantity": 1240000, "price_inr": "1,234.50", "value_inr": None})
    assert (value, how, flag) == (Decimal("1530780000.00"), "quantity_x_price", None)
    assert rs.money_words(value) == "₹153.08 crore"


def test_printed_value_wins_and_a_mismatch_is_flagged():
    value, how, flag = rs.record_value({"quantity": 1000, "price_inr": "100", "value_inr": "1,50,000",
                                        "exchange": "NSE", "row_ref": "row 1"})
    assert (value, how) == (Decimal("150000"), "printed_value")
    assert "differs from quantity × price" in flag


def test_no_price_and_no_value_is_unknown_never_guessed():
    _spec, doc = _event("block_deal", WEEK)
    seller = _person(doc, "p_r_k_sample")
    assert seller["amounts"]["proceeds"]["status"] == "unknown"
    assert "neither a trade value nor a price" in seller["amounts"]["proceeds"]["reason"]


def test_same_name_on_two_dates_is_one_person_with_the_sum():
    _spec, doc = _event("block_deal", WEEK)
    seller = _person(doc, "p_asha_example")
    figure = seller["amounts"]["proceeds"]
    # 12,40,000 × 1,234.50 + printed 7,44,00,000
    assert Decimal(figure["rupees_high"]) == Decimal("1530780000.00") + Decimal("74400000")
    assert figure["display"] == "₹160.52 crore"
    assert [day["trade_date"] for day in seller["trades"]] == ["2026-11-12", "2026-11-13"]
    assert seller["why_money"] == "sold 13,00,000 shares in block deals on 12 Nov 2026 and 13 Nov 2026"
    assert len(seller["evidence"]) == 2 and all(item["link"] and item["row_ref"] for item in seller["evidence"])


def test_indian_grouping_and_small_amounts():
    assert rs.indian(Decimal("1240000")) == "12,40,000"
    assert rs.indian(Decimal("1234.50")) == "1,234.50"
    assert rs.money_words(Decimal("480000")) == "₹4.80 lakh"
    assert rs.money_words(Decimal("20000")) == "₹20,000"


# ---------- timing ----------

def test_t_plus_one_skips_the_weekend_and_says_holidays_are_not_checked():
    assert rs.settles_on(date(2026, 11, 13)) == date(2026, 11, 16)  # Friday -> Monday
    timing = rs.settlement_timing([{"kind": "block_deal", "trade_date": "2026-11-12", "id": "x"}], AS_OF)
    assert timing["status"] == "settles" and timing["settles_on"] == "2026-11-13" and timing["days_since"] == 2
    assert "holidays not checked" in timing["note"]


def test_insider_modes_market_off_market_and_gift():
    _spec, doc = _event("insider_sale", "example_industries_insider_sale_2026w46")
    assert _person(doc, "p_ravi_kumar_sample")["timing"]["proceeds"]["status"] == "settles"
    off = _person(doc, "p_nina_sample")
    assert off["timing"]["proceeds"]["status"] == "unknown" and "off-market" in off["timing"]["proceeds"]["reason"]
    assert off["amounts"]["proceeds"]["display"] == "₹18.00 lakh"
    gift = _person(doc, "p_arun_sample")
    assert gift["seller_status"] == "no" and "Gift" in gift["context_reason"]
    assert _person(doc, "p_ravi_kumar_sample")["role_as_printed"] == "Promoter group"


# ---------- holder types, lists and tiers ----------

@pytest.mark.parametrize("name", ["SAMPLE ASIA MARKETS PTE", "EXAMPLE GROWTH SECURITIES", "SAMPLE LIFE INSURANCE",
                                  "EXAMPLE ARBITRAGE", "SAMPLE MUTUAL FUND A/C EXAMPLE SCHEME", "EXAMPLE BROKING LLP"])
def test_fund_and_broker_names_are_entities(name):
    assert rs.exchange_holder_type(name)[0] == "entity"


@pytest.mark.parametrize("name", ["ASHA EXAMPLE", "Ravi Kumar Sample", "R K SAMPLE"])
def test_person_names_stay_persons(name):
    assert rs.exchange_holder_type(name)[0] == "person"


def test_ranked_lists_buyers_in_context_funds_in_entities_and_tiers():
    spec, doc = _event("block_deal", WEEK)
    ranked = rank_people(doc["people"], spec.event_type)
    callable_ = {e["person_id"]: e for e in ranked["callable"]}
    assert set(callable_) == {"p_asha_example", "p_r_k_sample"}
    assert [e["person_id"] for e in ranked["entities"]] == ["p_sample_asia_markets_pte"]
    assert [e["person_id"] for e in ranked["context"]] == ["p_example_growth_securities_bought"]
    assert "buying is not coming into money" in ranked["context"][0]["context_reason"]
    # Known amount first, both cash now (sold within 30 days).
    assert [e["person_id"] for e in ranked["callable"]] == ["p_asha_example", "p_r_k_sample"]
    assert all(e["call_tier"] == "cash_now" for e in ranked["callable"])
    assert callable_["p_asha_example"]["call_tier_label"] == "Cash in hand"  # part settled on 13 Nov
    assert callable_["p_r_k_sample"]["confidence"] == "medium"  # printed with initials


def test_seller_older_than_thirty_days_is_cash_received_earlier():
    spec, doc = _event("block_deal", "example_industries_block_deal_2026w36")
    entry = rank_people(doc["people"], spec.event_type)["callable"][0]
    assert (entry["call_tier"], entry["call_tier_label"]) == ("holding", "Cash received earlier")


def test_same_name_buying_and_selling_is_two_entries_never_netted():
    records = [
        {"id": "a", "kind": "block_deal", "exchange": "NSE", "company": "Example Industries Limited",
         "trade_date": "2026-11-12", "name_as_printed": "ASHA EXAMPLE", "side": "sell", "quantity": 100,
         "price_inr": "10", "link": "https://example.test/a", "row_ref": "row 1"},
        {"id": "b", "kind": "block_deal", "exchange": "NSE", "company": "Example Industries Limited",
         "trade_date": "2026-11-12", "name_as_printed": "ASHA EXAMPLE", "side": "buy", "quantity": 40,
         "price_inr": "10", "link": "https://example.test/a", "row_ref": "row 2"},
    ]
    spec = EventSpec.model_validate(rs.group_records(records)[0])
    doc = rs.build_people(spec, records, {}, as_of=AS_OF)
    seller = _person(doc, "p_asha_example")
    assert seller["amounts"]["proceeds"]["rupees_high"] == "1000"
    assert _person(doc, "p_asha_example_bought")["seller_status"] == "no"


# ---------- grouping and the spec ----------

def test_group_records_by_company_kind_and_week():
    specs = rs.group_records(_records("block_deal"))
    assert [s["event_id"] for s in specs] == ["example_industries_block_deal_2026w36", WEEK]
    week = specs[1]
    # The BSE row ("EXAMPLE INDUSTRIES LTD") joins the NSE rows; the buyer-only company has no event.
    assert week["records"] == ["bd01", "bd02", "bd03", "bd04", "bd05"]
    assert week["company"] == "Example Industries Limited" and week["documents"] == []
    assert week["records_file"] == "outputs/signals/block_deal.json" and week["event_date"] == "2026-11-13"
    for spec in specs:
        EventSpec.model_validate(spec)


def test_bulk_deal_is_a_block_deal_event_with_its_own_words_and_file():
    record = {**_records("block_deal")[0], "id": "bk1", "kind": "bulk_deal"}
    spec = rs.group_records([record])[0]
    assert spec["event_type"] == "block_deal" and spec["records_file"] == "outputs/signals/bulk_deal.json"
    doc = rs.build_people(EventSpec.model_validate(spec), [record], {}, as_of=AS_OF)
    assert "in a bulk deal" in doc["people"][0]["why_money"]


def test_spec_rules_for_structured_and_document_events():
    base = {"event_id": "x_block_deal_2026w46", "event_type": "block_deal", "company": "Example Ltd"}
    with pytest.raises(ValueError):
        EventSpec.model_validate(base)  # no records
    with pytest.raises(ValueError):
        EventSpec.model_validate({**base, "records": ["a"], "records_file": "../secrets.json"})
    with pytest.raises(ValueError):
        EventSpec.model_validate({"event_id": "x_ipo", "event_type": "ipo", "company": "Example Ltd", "documents": []})
    ipo = EventSpec.model_validate({"event_id": "x_ipo", "event_type": "ipo", "company": "Example Ltd",
                                    "documents": [{"url": "https://example.test/a.pdf", "doc_type": "rhp"}]})
    assert "records" not in ipo.model_dump(exclude_none=True)


# ---------- run.py end to end, and the API views on its outputs ----------

def _no_model(*_args, **_kwargs):
    raise LLMError("LLM_API_KEY is missing. No request was sent.")


def _run_all(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setenv("RUN_ID", "run-structured")
    monkeypatch.setenv("RUNS_CSV_PATH", str(tmp_path / "runs.csv"))
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setattr(run, "fetch", lambda url: (_ for _ in ()).throw(AssertionError("no fetch expected")))
    monkeypatch.setattr(brief_module, "ask_model", _no_model)
    monkeypatch.setattr(run, "ask_model", _no_model)  # run.py imported the name itself
    (tmp_path / "outputs" / "signals").mkdir(parents=True)
    shutil.copy(FIXTURES / "block_deal.json", tmp_path / "outputs" / "signals" / "block_deal.json")
    spec = next(s for s in rs.group_records(_records("block_deal")) if s["event_id"] == WEEK)
    event_path = tmp_path / "events" / f"{WEEK}.json"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(json.dumps(spec), encoding="utf-8")
    assert run.main(["--event", str(event_path), "--step", "all"]) == 0
    return tmp_path / "outputs" / WEEK


def test_run_all_writes_every_output_without_fetch_or_model(tmp_path, monkeypatch, capsys):
    folder = _run_all(tmp_path, monkeypatch)
    for name in ("people.json", "ranked.json", "briefs.json", "report.md", "cost.json", "timeline.json"):
        assert (folder / name).is_file(), name
    assert not (folder / "extract.json").exists() and not (folder / "locate.json").exists()
    timeline = json.loads((folder / "timeline.json").read_text(encoding="utf-8"))
    assert [step["step"] for step in timeline["steps"]] == ["people", "rank", "brief", "report"]
    briefs = json.loads((folder / "briefs.json").read_text(encoding="utf-8"))["briefs"]
    assert [b["person_id"] for b in briefs] == ["p_asha_example", "p_r_k_sample"]
    for item in briefs:
        assert item["brief_source"] == "template" and item["template_problem"] is None
    assert "13,00,000 shares in block deals" in briefs[0]["lines"][0]
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert "Documents: none (built from exchange records)" in report
    assert "NSE block deals 12-Nov-2026 row 3" in report
    assert "STEP people done" in capsys.readouterr().out


def test_document_steps_do_not_apply(tmp_path, monkeypatch, capsys):
    folder = _run_all(tmp_path, monkeypatch)
    assert run.main(["--event", str(tmp_path / "events" / f"{WEEK}.json"), "--step", "extract"]) == 0
    assert "does not apply" in capsys.readouterr().out
    assert not (folder / "extract.json").exists()


def test_api_views_read_the_structured_outputs(tmp_path, monkeypatch, app_env):
    from api import views

    folder = _run_all(tmp_path, monkeypatch)
    spec = EventSpec.model_validate(json.loads((tmp_path / "events" / f"{WEEK}.json").read_text(encoding="utf-8")))
    out = {name: (json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
                  if (folder / f"{name}.json").is_file() else None)
           for name in ("extract", "people", "ranked", "briefs", "cost", "timeline", "check")}
    event = {"spec": spec, "raw": {}, "path": tmp_path, "auto": True, "out": out, "processed": True}
    lists = views.event_lists(event)
    assert [item["person"]["id"] for item in lists["callable"]] == ["p_asha_example", "p_r_k_sample"]
    assert [item["person"]["id"] for item in lists["entities"]] == ["p_sample_asia_markets_pte"]
    assert [item["person"]["id"] for item in lists["context"]] == ["p_example_growth_securities_bought"]
    assert lists["callable"][0]["amount"]["display"] and lists["callable"][0]["event"]["type_label"] == "Block deal"
    card = views.person_card(event, "p_asha_example", None)
    assert card["name_evidence"] and card["name_evidence"][0]["source_url"].startswith("https://example.test/")
    assert views.type_label("insider_sale") == "Insider sale"


# ---------- hardening: odd rows the exchange files can carry ----------

def _insider(**overrides) -> dict:
    row = {"id": "r1", "kind": "insider_sale", "exchange": "NSE", "company": "Example Industries Limited",
           "trade_date": "2026-11-12", "name_as_printed": "Ravi Kumar Sample", "category": "promoter", "side": "sell",
           "quantity": 1000, "price_inr": None, "value_inr": "1,00,000", "mode": "Market Sale",
           "link": "https://example.test/insider", "row_ref": "NSE PIT row 1"}
    return {**row, **overrides}


def _insider_doc(rows: list[dict], as_of: date = AS_OF) -> dict:
    spec = EventSpec.model_validate(rs.group_records(rows, require_seller=False)[0])
    return rs.build_people(spec, rows, {}, as_of=as_of)


def test_unknown_side_is_skipped_and_reported_never_a_seller():
    doc = _insider_doc([_insider(), _insider(id="r2", side=None, name_as_printed="Nina Sample"),
                        _insider(id="r3", side=" SELL ", name_as_printed="Arun Sample")])
    assert sorted(p["person_id"] for p in doc["people"]) == ["p_arun_sample", "p_ravi_kumar_sample"]
    assert doc["records_source"]["records_skipped_unknown_side"] == ["r2"]


def test_same_insider_disclosure_on_both_exchanges_is_counted_once():
    doc = _insider_doc([_insider(), _insider(id="r2", exchange="BSE", row_ref="BSE PIT row 4")])
    person = doc["people"][0]
    assert person["amounts"]["proceeds"]["rupees_high"] == "100000"
    assert len(person["evidence"]) == 2 and "counted once" in person["flags"][0]


@pytest.mark.parametrize("mode", ["Revoke", "Invocation of pledge", "ESOS", "Gift", "Inter-se transfer by gift"])
def test_non_cash_modes_are_context(mode):
    doc = _insider_doc([_insider(mode=mode)])
    assert doc["people"][0]["seller_status"] == "no" and doc["people"][0]["context_reason"]


def test_unknown_mode_stays_a_seller_with_low_confidence_and_a_flag():
    person = _insider_doc([_insider(mode=None)])["people"][0]
    assert person["seller_status"] == "verified" and person["confidence"]["level"] == "low"
    assert any("mode unsure" in flag for flag in person["flags"])


def test_initials_that_look_like_legal_forms_stay_persons():
    assert rs.exchange_holder_type("NV SAMPLE")[0] == "person"
    assert rs.exchange_holder_type("SA EXAMPLE KUMAR")[0] == "person"
    assert rs.exchange_holder_type("EXAMPLE HOLDING SA")[0] == "entity"


def test_off_market_seller_ages_out_of_cash_now():
    doc = _insider_doc([_insider(mode="Off Market", trade_date="2026-09-01")])
    timing = doc["people"][0]["timing"]["proceeds"]
    assert timing["status"] == "unknown" and timing["days_since"] == 75
    entry = rank_people(doc["people"], "insider_sale")["callable"][0]
    assert entry["call_tier"] == "holding"


def test_no_matching_records_is_an_error_not_an_empty_list(tmp_path):
    with pytest.raises(LookupError):
        rs.load_records(FIXTURES / "block_deal.json", ["not-a-record"])
    with pytest.raises(FileNotFoundError):
        rs.load_records(tmp_path / "missing.json", ["bd01"])


def test_names_that_slug_alike_get_distinct_ids():
    doc = _insider_doc([_insider(), _insider(id="r2", name_as_printed="Ravi-Kumar Sample.", quantity=5)])
    ids = [p["person_id"] for p in doc["people"]]
    assert len(ids) == len(set(ids))


def test_insider_event_end_to_end_through_run_and_views(tmp_path, monkeypatch, app_env):
    from api import views

    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setenv("RUN_ID", "run-insider")
    monkeypatch.setenv("RUNS_CSV_PATH", str(tmp_path / "runs.csv"))
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setattr(brief_module, "ask_model", _no_model)
    monkeypatch.setattr(run, "ask_model", _no_model)  # run.py imported the name itself
    (tmp_path / "outputs" / "signals").mkdir(parents=True)
    shutil.copy(FIXTURES / "insider_sale.json", tmp_path / "outputs" / "signals" / "insider_sale.json")
    spec_dict = rs.group_records(_records("insider_sale"))[0]
    event_path = tmp_path / "events" / f"{spec_dict['event_id']}.json"
    event_path.parent.mkdir(parents=True)
    event_path.write_text(json.dumps(spec_dict), encoding="utf-8")
    assert run.main(["--event", str(event_path), "--step", "all"]) == 0
    folder = tmp_path / "outputs" / spec_dict["event_id"]
    briefs = json.loads((folder / "briefs.json").read_text(encoding="utf-8"))["briefs"]
    assert all(item["template_problem"] is None for item in briefs)
    out = {name: (json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
                  if (folder / f"{name}.json").is_file() else None)
           for name in ("extract", "people", "ranked", "briefs", "cost", "timeline", "check")}
    event = {"spec": EventSpec.model_validate(spec_dict), "raw": {}, "path": event_path, "auto": True, "out": out,
             "processed": True}
    lists = views.event_lists(event)
    assert {item["person"]["id"] for item in lists["callable"]} == {"p_ravi_kumar_sample", "p_nina_sample"}
    assert {item["person"]["id"] for item in lists["context"]} == {"p_arun_sample", "p_kavya_sample_bought"}
    ravi = next(item for item in lists["callable"] if item["person"]["id"] == "p_ravi_kumar_sample")
    assert ravi["amount"]["value_cr"] == 0.48 and ravi["person"]["role"] == "Promoter group"
    card = views.person_card(event, "p_nina_sample", None)
    assert card["timing"]["status"] == "unknown" and card["event"]["type_label"] == "Insider sale"


def test_a_printed_value_of_zero_is_unknown_not_zero_rupees():
    """A real NSE insider filing printed 'value 0' for 3,09,034 shares in mode Others: no amount may be shown."""
    from agents.rules_structured import record_value

    row = {"quantity": 309034, "value_inr": "0", "price_inr": None}
    assert record_value(row) == (None, None, None)
    assert record_value({"quantity": 10, "value_inr": None, "price_inr": "0.00"}) == (None, None, None)
    assert record_value({"quantity": 10, "value_inr": None, "price_inr": "5"})[0] == 50
