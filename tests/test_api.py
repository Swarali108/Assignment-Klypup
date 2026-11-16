"""Tier-1 API checks against the committed outputs/: money fields equal stored values, unknown -> null."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(as_role):
    """An admin-signed-in client with an isolated database and the model stubbed out."""
    return as_role("admin")


def _people(event_id: str) -> dict:
    """people.json persons by id."""
    doc = json.loads((ROOT / "outputs" / event_id / "people.json").read_text(encoding="utf-8"))
    return {p["person_id"]: p for p in doc["people"]}


def test_person_amount_matches_stored(client):
    """The top cash-now seller's value_cr is people.json proceeds crore_high, as a float."""
    people = _people("zetwerk_manufacturing_businesses_limited_ipo_202610")
    calls = client.get("/api/events/zetwerk_manufacturing_businesses_limited_ipo_202610/people").json()["callable"]
    seller = next(item for item in calls if item["tier"] == "cash_now" and item["amount"]["value_cr"] is not None)
    stored = people[seller["person"]["id"]]["amounts"]["proceeds"]["crore_high"]
    assert seller["amount"]["value_cr"] == float(Decimal(stored))
    card = client.get(f"/api/people/zetwerk_manufacturing_businesses_limited_ipo_202610/{seller['person']['id']}").json()
    proceeds = next(a for a in card["amounts"] if a["key"] == "proceeds")
    assert proceeds["value_cr"] == float(Decimal(stored))
    assert proceeds["working"] == people[seller["person"]["id"]]["amounts"]["proceeds"]["working"]


def test_unknown_amount_is_null(client):
    """An OFS seller whose own shares are not printed: value_cr is None and the display says not disclosed."""
    calls = client.get("/api/events/spacenet_ofs/people").json()["callable"]
    assert calls
    for item in calls:
        assert item["amount"]["value_cr"] is None
        assert "not disclosed" in item["amount"]["display"].lower()
        assert item["amount"]["reason"]
        assert "0" not in item["amount"]["display"]


def test_cash_total_is_sum_of_stored(client):
    """An event's cash total is the sum of its cash-now people's stored crore_high."""
    people = _people("zetwerk_manufacturing_businesses_limited_ipo_202610")
    summary = next(e for e in client.get("/api/events").json()["events"] if e["id"] == "zetwerk_manufacturing_businesses_limited_ipo_202610")
    calls = client.get("/api/events/zetwerk_manufacturing_businesses_limited_ipo_202610/people").json()["callable"]
    total = sum(Decimal(people[i["person"]["id"]]["amounts"]["proceeds"]["crore_high"])
                for i in calls if i["tier"] == "cash_now" and i["amount"]["value_cr"] is not None)
    assert summary["cash_cr"] == float(total)


def test_rm_state_roundtrip(client):
    """PUT then GET returns what was saved, and the queue shows it."""
    saved = client.put("/api/rm/sedemac_ipo/p_mallika_r_iyer",
                       json={"status": "called", "note": "Spoke briefly", "follow_up_date": "2026-11-20"}).json()
    assert saved["status"] == "called"
    got = client.get("/api/rm/sedemac_ipo/p_mallika_r_iyer").json()
    assert (got["status"], got["note"], got["follow_up_date"]) == ("called", "Spoke briefly", "2026-11-20")
    assert client.put("/api/rm/sedemac_ipo/p_mallika_r_iyer", json={"status": "bogus"}).status_code == 422


def test_empty_event_has_reason(client):
    """An event with no one to call explains why."""
    body = client.get("/api/events/jio_platforms_limited_ipo_202610/people").json()
    assert body["callable"] == [] and body["empty_reason"]


def test_ask_falls_back_without_model_and_uses_only_question_numbers(client):
    """Model failure -> rule filters; every result meets the bound written in the question."""
    body = client.post("/api/ask", json={"q": "promoters with cash in hand above 50 crore"}).json()
    assert body["interpreted_by"] == "rules"
    assert body["filters"]["min_cr"] == 50 and body["filters"]["tier"] == "cash_now"
    assert all(p["amount"]["value_cr"] >= 50 for p in body["people"])


def test_ask_drops_model_number_not_in_question():
    """A bound the model invents (not written in the question) is dropped."""
    from api.ask import ask

    items = [{"amount": {"value_cr": 10.0}, "event": {"type": "ipo", "company": "X Ltd"},
              "person": {"name": "A", "role": "Promoter"}, "tier": "cash_now", "timing": {"status": "in_hand"},
              "confidence": {"level": "high"}}]
    result = ask("promoters with cash", items, [], model=lambda q: {"tier": "cash_now", "min_cr": 75})
    assert result["interpreted_by"] == "assistant"
    assert "min_cr" not in result["filters"]
    assert result["count"] == 1


def test_uses_pipeline_call_tier_and_context_when_present(client, tmp_path, monkeypatch):
    """With the new ranked.json fields (call_tier, household_id, context) the API follows them as stored."""
    import shutil

    from api import store

    outputs = tmp_path / "outputs"
    shutil.copytree(ROOT / "outputs" / "sedemac_ipo", outputs / "sedemac_ipo")
    ranked_path = outputs / "sedemac_ipo" / "ranked.json"
    ranked = json.loads(ranked_path.read_text(encoding="utf-8"))
    moved = ranked["callable"].pop()
    for entry in ranked["callable"]:
        entry["call_tier"], entry["call_tier_label"] = "holding", "Holds shares"
        entry["household_id"] = None
    ranked["callable"][0]["call_tier"], ranked["callable"][0]["call_tier_label"] = "unlock", "Shares just unlocked"
    ranked["context"] = [{**moved, "context_reason": "not tendering"}]
    ranked_path.write_text(json.dumps(ranked), encoding="utf-8")
    monkeypatch.setattr(store, "OUTPUTS_DIR", outputs)
    body = client.get("/api/events/sedemac_ipo/people").json()
    assert body["callable"][0]["tier"] == "unlock"
    assert {i["tier"] for i in body["callable"][1:]} == {"holding"}
    assert [i["person"]["id"] for i in body["context"]] == [moved["person_id"]]
    assert body["context"][0]["context_reason"] == "Not tendering"


def test_ask_model_path_calls_llm_with_registered_schema(monkeypatch):
    """model_filters goes through tools.llm.llm_call with the AskFilters schema; its answer is used."""
    import tools.llm as llm
    from api.ask import SCHEMA_NAME, ask, model_filters

    seen = {}

    def fake_llm_call(agent_name, messages, schema_name, prompt_version, event_id, person_id=None, model=None):
        seen.update(agent=agent_name, schema=schema_name, registered=schema_name in llm.SCHEMAS)
        return {"tier": "cash_now", "role_contains": "promoter", "min_cr": 50}

    monkeypatch.setattr(llm, "llm_call", fake_llm_call)
    items = [{"amount": {"value_cr": 60.0}, "event": {"type": "ipo", "company": "X Ltd"},
              "person": {"name": "A", "role": "Promoter"}, "tier": "cash_now", "timing": {"status": "in_hand"},
              "confidence": {"level": "high"}}]
    result = ask("promoters with cash in hand above 50 crore", items, [], model=model_filters)
    assert seen == {"agent": "ask", "schema": SCHEMA_NAME, "registered": True}
    assert result["interpreted_by"] == "assistant" and result["filters"]["min_cr"] == 50 and result["count"] == 1


def test_ask_drops_a_timing_status_no_item_carries():
    """'cash in hand' is the tier; a model-invented timing_status such as in_hand must not empty the answer."""
    from api.ask import safe_filters

    out = safe_filters({"tier": "cash_now", "role_contains": "promoter", "timing_status": "in_hand", "min_cr": 50},
                       "promoters with cash in hand above 50 crore")
    assert out == {"tier": "cash_now", "role_contains": "promoter", "min_cr": 50.0}


def test_internal_wording_never_reaches_a_screen(client):
    """Stored engine wording is translated once, in the views, for every response."""
    from api import views

    assert views.clean("Holder type unsure: no entity marker and 9 words") == \
        "We could not confirm whether this holder is a person or an organisation"
    assert views.clean("Which of this promoter's shares fall in the 18% is not extracted.") == \
        "The filing does not say which of this promoter's shares fall in the 18%."
    banned = ("not extracted", "entity marker", "no entity or family marker")
    for event in client.get("/api/events").json()["events"]:
        if not event["people_count"]:
            continue
        people = client.get(f"/api/events/{event['id']}/people").json()
        text = json.dumps(people).lower()
        for group in ("callable", "entities", "context"):
            for item in people[group]:
                text += json.dumps(client.get(f"/api/people/{event['id']}/{item['person']['id']}").json()).lower()
        assert not [w for w in banned if w in text], event["id"]


def test_organisations_are_not_callable_and_family_trusts_are_labelled(client):
    """A fund or company printed as a holder sits in entities; a family trust stays callable and says so."""
    today = client.get("/api/today").json()["items"]
    names = [i["person"]["name"] for i in today]
    assert not any(n.startswith("CEAQ") for n in names)
    trusts = [i for i in today if i["person"]["holder_type"] == "family_vehicle"]
    assert trusts and all(i["person"]["kind_label"] in ("Family trust", "Family (HUF)") for i in trusts)
    assert any(i["person"]["kind_label"] == "Family trust" for i in trusts)


def test_calendar_lists_a_listing_date_with_no_known_cash(client):
    """Upcoming listing days appear even when nobody has a known amount; never as zero."""
    rows = client.get("/api/calendar").json()["items"]
    crystal = [r for r in rows if r["kind"] == "listing" and r["date_iso"] == "2026-11-26"]
    assert crystal and crystal[0]["total_cr"] is None and crystal[0]["label"] == "Listing day"
    assert all(r["total_cr"] != 0 for r in rows)


def test_tiny_amount_shows_rupees_not_zero_crore():
    from api.views import working_text
    figure = {"crore_high": "0.00", "rupees_high": "15100", "working": "100 × ₹151 = ₹0.00 crore"}
    assert working_text(figure) == "100 × ₹151 = ₹15,100"
    big = {"crore_high": "300.00", "rupees_high": "3000000000", "working": "x = ₹300.00 crore"}
    assert working_text(big) == "x = ₹300.00 crore"


def test_brief_line_with_tiny_amount_reads_in_rupees():
    from api.views import tidy_lines
    person = {"amounts": {"proceeds": {"rupees_high": "15100"}}}
    out = tidy_lines(["Proceeds of ₹0.00 crore have been in hand since in hand since about 23 Oct 2026."], person)
    assert out == ["Proceeds of ₹15,100 have been in hand since about 23 Oct 2026."]
