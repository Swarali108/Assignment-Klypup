"""Checks for chat fixes that touch stored data and exports: a confirm message is marked as such (so a reopened
thread can tell which estimate ran), the lineage export uses the card's words and keeps the tree, the process
question offers the kind of event that was named, and a name clarify points at the exact person."""

from __future__ import annotations

import json

from api.chat import clarify, exports


def test_confirm_message_is_stored_as_confirmed(as_role, tmp_path, monkeypatch):
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
    from api.chat import llm as chat_llm
    from tools.llm import LLMError

    def refuse(*args, **kwargs):
        raise LLMError("model unavailable in tests")

    monkeypatch.setattr(chat_llm, "call", refuse)
    client = as_role("rm")
    top = client.get("/api/today?limit=1").json()["items"][0]
    reply = client.post("/api/chat", json={"choice": f"deep:{top['event']['id']}/{top['person']['id']}"})
    events = [(b.split("\n")[0][7:], json.loads(b.split("\n")[1][6:])) for b in reply.text.split("\n\n") if b.startswith("event: ")]
    cid = next(d["conversation_id"] for n, d in events if n == "meta")
    token = next(d["confirm_token"] for n, d in events if n == "estimate")
    client.post("/api/chat", json={"conversation_id": cid, "message": "", "confirm_token": token})
    stored = client.get(f"/api/chat/conversations/{cid}").json()["messages"]
    users = [m for m in stored if m["role"] == "user"]
    assert not users[0].get("confirmed")  # the pick that asked for the estimate is not a confirm
    assert users[1].get("confirmed") is True  # the run that followed it is, so a reopened thread can tell


def test_lineage_export_uses_card_words_and_keeps_the_tree():
    card = {"kind": "lineage", "title": "Where the money goes", "items": [], "nodes": [
        {"id": "n1", "parent": None, "kind": "person", "label": "A Person", "status": "followed", "detail": None},
        {"id": "n2", "parent": "n1", "kind": "same_person", "label": "Acme Limited · IPO", "status": "followed", "detail": "x"},
        {"id": "n3", "parent": "n1", "kind": "filing", "label": "A filing", "status": "candidate", "detail": "y"},
        {"id": "n4", "parent": "n2", "kind": "family", "label": "A Relative", "status": "followed", "detail": "z"}]}
    text = exports.card_md(card)
    assert "same_person" not in text and "family" not in text and "candidate" not in text
    assert "Same person, another event" in next(line for line in text.splitlines() if "Acme" in line)
    relative = next(line for line in text.splitlines() if "A Relative" in line)
    assert "↳ ↳ A Relative" in relative and "Same household" in relative
    assert text.index("Acme Limited") < text.index("A Relative") < text.index("A filing")  # children follow their parent


def test_process_question_offers_only_the_type_asked_for(monkeypatch):
    from api import store

    def event(event_type, event_id):
        spec = type("Spec", (), {"event_type": event_type, "event_id": event_id, "company": event_id.upper()})()
        return {"spec": spec, "processed": False}

    monkeypatch.setattr(store, "load_events", lambda: [event("buyback", "b1"), event("ipo", "i1")])
    assert [o["value"] for o in clarify.need_event("Process a new IPO from a link")["options"]] == ["process:i1"]
    both = clarify.need_event("process something")["options"]
    assert {o["value"] for o in both} == {"process:b1", "process:i1"}
    monkeypatch.setattr(store, "load_events", lambda: [event("buyback", "b1")])
    none = clarify.need_event("Process a new IPO from a link")
    assert none["options"] == [] and "IPO" in none["question"]


def test_name_clarify_points_at_the_exact_person():
    identity = {"name": "A Person", "appearances": [{"role": "Holder", "company": "Acme", "amount": "₹1 Cr",
                                                      "event_id": "e1", "person_id": "p1"}]}
    options = clarify.which_person("Person", [identity, identity])["options"]
    assert {o["value"] for o in options} == {"person:e1/p1"}
