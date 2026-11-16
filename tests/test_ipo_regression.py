"""The IPO path gives the same people and ranking as the saved snapshot. No network, no model call.

tests/fixtures/sedemac_ipo/ holds extract.json, people.json and ranked.json from one
real run, saved before the event-type refactor. Rebuilding people and the ranking
from that extract.json must give back the same fields and amounts.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from agents.people import build_people
from agents.rank import rank_people

FIXTURES = Path(__file__).parent / "fixtures" / "sedemac_ipo"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _no_model(left, right, event_id):
    raise AssertionError("the snapshot needed no identity call")


def _rebuild() -> tuple[dict, dict]:
    before = _load("people.json")
    spec = SimpleNamespace(event_id=before["event_id"], event_type="ipo")
    people = build_people(_load("extract.json"), spec, ask=_no_model, as_of=date.fromisoformat(before["as_of"]))
    return before, people


def test_people_fields_and_amounts_are_unchanged():
    before, after = _rebuild()
    assert [p["person_id"] for p in after["people"]] == [p["person_id"] for p in before["people"]]
    # Keys added after the snapshot was taken; every key the snapshot has must be unchanged.
    added = {"amount_as_printed"}
    for old, new in zip(before["people"], after["people"]):
        assert set(new) - set(old) <= added, (old["person_id"], set(new) - set(old))
        assert {key: new[key] for key in old} == old, old["person_id"]
    for key in ("price_basis", "listing", "allotment", "identity_log", "family_groups", "counts"):
        assert after[key] == before[key], key


def test_ranking_is_unchanged():
    before, after = _rebuild()
    ranked = rank_people(after["people"], "ipo")
    saved = _load("ranked.json")
    # The snapshot was re-saved for the RM call tiers (cash now > fresh unlock > holding).
    # Keys added after it was taken go here. Every key the snapshot has must be unchanged.
    added: set[str] = set()
    for key in ("callable", "entities"):
        assert len(ranked[key]) == len(saved[key]), key
        for new, old in zip(ranked[key], saved[key]):
            assert set(new) - set(old) == added, (key, set(new) - set(old))
            assert {field: new[field] for field in old} == old, (key, old["person_id"])


def test_largest_promoter_with_a_fresh_unlock_leads_the_call_list():
    _before, after = _rebuild()
    ranked = rank_people(after["people"], "ipo")
    first = ranked["callable"][0]
    assert first["name_as_printed"] == _load("ranked.json")["callable"][0]["name_as_printed"]
    assert first["call_tier"] == "unlock" and Decimal(first["later_value_crore"]) == max(
        Decimal(entry["later_value_crore"]) for entry in ranked["callable"])
    tiers = [entry["call_tier"] for entry in ranked["callable"]]
    assert tiers == sorted(tiers, key=["cash_now", "unlock", "holding"].index)
