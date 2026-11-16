"""Cross-event index and follow-on matches. No network, no model call."""

from __future__ import annotations

import json
from types import SimpleNamespace

from tools.people_index import LIKELY, MAX_MATCHES, POSSIBLE, follow_on, link_event, load_index


def _person(name: str, holder_type: str = "person", person_id: str | None = None) -> dict:
    return {
        "person_id": person_id or "p_" + name.lower().replace(" ", "_"),
        "name_as_printed": name,
        "holder_type": holder_type,
        "role_as_printed": "Promoters",
        "seller_status": "no",
        "amounts": {"proceeds": {"status": "not_applicable", "reason": "x"},
                    "retained": {"status": "unknown", "reason": "pre-offer holding not verified"}},
        "timing": {"proceeds": {"status": "in_hand", "since": "2026-03-11", "when": "in hand"}},
    }


def _doc(*people: dict) -> dict:
    return {"as_of": "2026-11-14", "people": list(people), "counts": {}}


def _spec(event_id: str) -> SimpleNamespace:
    return SimpleNamespace(event_id=event_id, event_type="ipo", company=f"{event_id} Ltd")


def test_three_token_person_and_entity_are_likely_two_tokens_possible(tmp_path):
    index = tmp_path / "index.json"
    link_event(_doc(_person("Asha Ravi Example"), _person("Asha Example"), _person("Example Holdings Limited", "entity")),
               _spec("first"), index)
    second = link_event(
        _doc(_person("Asha Ravi Example"), _person("Asha Example"), _person("Example Holding Ltd", "entity")),
        _spec("second"), index,
    )
    strengths = {p["name_as_printed"]: [m["match_strength"] for m in p["follow_on"]] for p in second["people"]}
    assert strengths == {"Asha Ravi Example": [LIKELY], "Asha Example": [POSSIBLE], "Example Holding Ltd": [LIKELY]}
    match = second["people"][0]["follow_on"][0]
    assert match["event_id"] == "first" and match["company"] == "first Ltd" and match["trigger_date"] == "2026-03-11"
    assert second["counts"] == {"index_lookups": 3, "follow_on_matches": 3}


def test_different_first_name_and_different_tokens_never_match(tmp_path):
    index = tmp_path / "index.json"
    link_event(_doc(_person("Atul Hiralal Shah")), _spec("first"), index)
    second = link_event(_doc(_person("Bakul Hiralal Shah"), _person("Hiralal Shah Atul Example")), _spec("second"), index)
    assert all(p["follow_on"] == [] for p in second["people"])


def test_rerunning_an_event_replaces_its_entries(tmp_path):
    index = tmp_path / "index.json"
    link_event(_doc(_person("Asha Ravi Example")), _spec("first"), index)
    link_event(_doc(_person("Asha Ravi Example"), _person("Ravi Kumar Sample")), _spec("first"), index)
    entries = load_index(index)
    assert [e["name_as_printed"] for e in entries] == ["Asha Ravi Example", "Ravi Kumar Sample"]
    again = link_event(_doc(_person("Asha Ravi Example")), _spec("first"), index)
    assert again["people"][0]["follow_on"] == []
    assert json.loads(index.read_text(encoding="utf-8"))["stop_rules"]


def test_at_most_ten_matches_per_person():
    entry = {"name_as_printed": "Asha Ravi Example", "identity_tokens": ["asha", "example", "ravi"], "holder_type": "person"}
    others = [{**entry, "event_id": f"event_{number:02d}", "company": "x", "role": None, "amount": "x", "trigger_date": None}
              for number in range(15)]
    assert len(follow_on(entry, others)) == MAX_MATCHES
