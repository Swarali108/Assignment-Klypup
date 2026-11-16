"""Tier-1 checks for the w2 core fixes: follow-up needs a date, undoing a call clears the first-call time,
a bulk deal has one label everywhere, and stored 'N days ago' phrases are counted to as_of()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVENT, PERSON = "sedemac_ipo", "p_devang_mehta"
URL = f"/api/rm/{EVENT}/{PERSON}"


@pytest.fixture()
def client(as_role):
    return as_role("admin")


def test_follow_up_needs_a_date(client):
    assert client.put(URL, json={"status": "follow_up", "note": "x", "follow_up_date": ""}).status_code == 422
    assert client.put(URL, json={"status": "follow_up"}).status_code == 422
    assert client.get(URL).json()["status"] == "to_call"
    ok = client.put(URL, json={"status": "follow_up", "follow_up_date": "2026-11-20"})
    assert ok.status_code == 200 and ok.json()["follow_up_date"] == "2026-11-20"
    # a follow-up that already has a date can be re-saved without sending it again
    assert client.put(URL, json={"status": "follow_up", "note": "later"}).status_code == 200


def test_back_to_to_call_clears_first_called_at(client):
    called = client.put(URL, json={"status": "called"}).json()
    assert called["first_called_at"]
    again = client.put(URL, json={"status": "follow_up", "follow_up_date": "2026-11-20"}).json()
    assert again["first_called_at"] == called["first_called_at"]
    undone = client.put(URL, json={"status": "to_call", "follow_up_date": ""}).json()
    assert undone["status"] == "to_call" and undone["first_called_at"] is None


def test_bulk_deal_has_one_label_on_every_screen(client):
    event_id = "aaa_technologies_bulk_deal_2026w46"
    events = client.get("/api/events").json()["events"]
    row = next(e for e in events if e["id"] == event_id)
    assert row["type"] == "block_deal" and row["type_label"] == "Bulk deal"
    today = client.get("/api/today").json()["items"]
    labels = {i["event"]["type_label"] for i in today if i["event"]["id"] == event_id}
    assert labels <= {"Bulk deal"}
    for item in today:
        if item["event"]["id"] == event_id and item.get("sources") and len(item["sources"]) == 1:
            assert item["sources"] == ["Bulk deal"]


def test_stored_age_phrases_are_counted_to_as_of(client, monkeypatch):
    from api import views

    monkeypatch.setenv("AURELIA_AS_OF", "2026-11-20")
    ranked = json.loads((ROOT / "outputs" / EVENT / "ranked.json").read_text(encoding="utf-8"))
    stored = next(e for e in ranked["callable"] if e["person_id"] == "p_manish_sharma")
    assert stored["trigger"]["kind"] == "unlock" and stored["trigger"]["ends_on"] == "2026-09-09"
    assert "(67 days ago)" in stored["rank_reasons"][0]
    card = client.get(f"/api/people/{EVENT}/p_manish_sharma").json()
    fresh = (views.as_of() - views.date.fromisoformat("2026-09-09")).days
    assert fresh == 72
    assert f"({fresh} days ago)" in card["rank_reasons"][0] and "67 days ago" not in card["rank_reasons"][0]
    assert f"({fresh} days ago)" in card["why"]
    # a model-written brief is filled again from its stored template, never edited as text
    devang = client.get(f"/api/people/{EVENT}/{PERSON}").json()
    assert any(f"{fresh} days ago" in line for line in devang["brief"]["lines"])
    assert not any("67 days ago" in line for line in devang["brief"]["lines"])


def test_age_phrases_are_left_alone_without_a_date():
    from api import views

    assert views.with_fresh_ages("lock-in ended (67 days ago); 167 days ago", {"67 days ago": "72 days ago"}) \
        == "lock-in ended (72 days ago); 167 days ago"
    assert views.age_swaps({"out": {"people": {}}, "spec": None}, {"triggers": [{"kind": "unlock", "days_since": 5}]}, {}) == {}


def test_every_stored_age_counts_from_one_run_day_per_event():
    """The date anchors age_swaps uses (an unlock's ends_on, the event's money date) reproduce one run day for
    every trigger of an event; if an anchor were wrong, its triggers would imply a different run day."""
    from datetime import date, timedelta

    from api import store, views

    checked = 0
    for event in store.load_events():
        if not event["processed"]:
            continue
        ranked = event["out"].get("ranked") or {}
        people = views.people_by_id(event)
        money = views.money_date(event)["date_iso"]
        run_days = set()
        for entry in ranked.get("callable", []) + ranked.get("entities", []) + ranked.get("context", []):
            proceeds = ((people.get(entry["person_id"]) or {}).get("timing") or {}).get("proceeds") or {}
            for trigger in entry.get("triggers") or [entry.get("trigger") or {}]:
                if trigger.get("days_since") is None:
                    continue
                if trigger.get("kind") == "unlock":
                    iso = trigger.get("ends_on")
                elif trigger.get("kind") == "proceeds" and proceeds.get("status") != "settles":
                    iso = money
                else:
                    iso = None
                if iso:
                    run_days.add(date.fromisoformat(iso[:10]) + timedelta(days=trigger["days_since"]))
                    checked += 1
        assert len(run_days) <= 1, (event["spec"].event_id, sorted(run_days))
    assert checked > 50
