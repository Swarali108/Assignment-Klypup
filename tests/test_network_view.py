"""Network view: a company dot opens the event that has calls, counts only individuals to call, and one
company spelled two ways is one dot. Plus the no-one-to-call copy names the right kind of event."""

from __future__ import annotations

from types import SimpleNamespace

from api import store, views


def test_company_spellings_merge_but_different_firms_do_not():
    """'Ltd.' vs 'Limited' and the exchange's truncated spelling are one company; two Tata firms are not."""
    same = views.same_company
    tok = views.company_tokens
    assert same(tok("Parag Milk Foods Ltd."), tok("Parag Milk Foods Limited"))
    assert same(tok("Sahajanand Medical Tech L"), tok("Sahajanand Medical Technologies Limited"))
    assert same(tok("Genus Power Infrastructures Ltd-$"), tok("Genus Power Infrastructure Limited"))
    assert not same(tok("Tata Motors Limited"), tok("Tata Steel Limited"))
    assert not same(tok("Tata Limited"), tok("Tata Motors Limited"))


def test_company_dot_opens_the_event_with_calls_and_counts_only_people():
    """On the real outputs: the dot's link is its first listed event, which has calls whenever any event
    behind the dot does; to_call never counts a fund; no company appears as two dots."""
    net = views.network(store.load_events(), {})
    companies = [n for n in net["nodes"] if n["type"] == "event"]
    assert companies
    seen = set()
    for node in companies:
        assert node["event"] == node["events"][0]["event"]
        if any(r["to_call"] for r in node["events"]):
            assert node["events"][0]["to_call"] == max(r["to_call"] for r in node["events"])
        assert node["to_call"] >= 0 and node["linked_people"] + node["linked_entities"] == node["people_count"]
        key = tuple(views.company_tokens(node["label"]))
        assert key not in seen, f"{node['label']} drawn twice"
        seen.add(key)


def _event(kind: str) -> dict:
    return {"processed": True, "spec": SimpleNamespace(event_type=kind)}


def _item(name: str) -> dict:
    return {"person": {"name": name}}


def test_no_one_to_call_copy_matches_the_event_kind():
    """A block deal whose seller is a company must not be described as a buyback nobody tendered in."""
    lists = {"callable": [], "context": [_item("PI OPPORTUNITIES AIF V LLP")], "entities": [_item("PRAZIM TRADING PVT LTD")]}
    text = views.empty_reason(_event("block_deal"), lists, [])
    assert "buyback" not in text and "tender" not in text
    assert "PRAZIM TRADING PVT LTD" in text and "1 other holder named gets no money" in text
    buyback = views.empty_reason(_event("buyback"), lists, [])
    assert "will not tender" in buyback
