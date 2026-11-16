"""Tier-1 checks for the wave-2 chat fixes: no model, no network (see tests/test_chat.py for the fixture style)."""

from __future__ import annotations

import json

import pytest


def _events(reply) -> list[tuple[str, dict]]:
    out = []
    for block in reply.text.split("\n\n"):
        lines = [line for line in block.split("\n") if line]
        if len(lines) >= 2 and lines[0].startswith("event: ") and lines[1].startswith("data: "):
            out.append((lines[0][7:], json.loads(lines[1][6:])))
    return out


def _of(events, kind):
    return [data for name, data in events if name == kind]


@pytest.fixture()
def chat(as_role, tmp_path, monkeypatch):
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
    from api.chat import llm as chat_llm
    from tools import llm as tools_llm

    def no_model(*args, **kwargs):
        raise AssertionError("a model was called")

    monkeypatch.setattr(chat_llm, "call", no_model)
    monkeypatch.setattr(tools_llm, "llm_call", no_model)
    monkeypatch.setattr(tools_llm, "llm_stream", no_model)
    return as_role


def _top(client) -> dict:
    return client.get("/api/today?limit=1").json()["items"][0]


def test_viewer_estimate_says_why_not_once(chat):
    """The reason a role cannot run a paid action is on the card (blocked_reason); the prose does not repeat it."""
    client = chat("viewer")
    top = _top(client)
    events = _events(client.post("/api/chat", json={"choice": f"deep:{top['event']['id']}/{top['person']['id']}"}))
    estimate = _of(events, "estimate")[0]
    assert estimate["can_confirm"] is False and estimate["confirm_token"] == ""
    reason = estimate["blocked_reason"]
    assert reason
    prose = "".join(d.get("delta", "") for d in _of(events, "text"))
    assert reason not in prose and "Nothing runs until you confirm" not in prose


def test_deep_dive_own_event_is_not_another_event(chat):
    """The starting appearance is the person's home: not counted as "other events", not drawn as a second copy."""
    from api.chat import deep_dive, tools

    client = chat("rm")
    top = _top(client)
    home = (top["event"]["id"], top["person"]["id"])
    identity = tools.find_person(*home)
    tree = deep_dive.explore(identity)
    own = deep_dive.home_node(tree, home)
    assert own is not None
    total = sum(1 for n in tree.nodes if n["kind"] == "same_person")
    assert deep_dive.free_rows(tree, home)[0]["step"] == f"Same person in other events ({total - 1})"

    before = [dict(n) for n in tree.nodes]
    card = deep_dive.lineage_card(tree, "t", home)
    assert tree.nodes == before  # the tree the writer reads is not changed
    ids = {n["id"] for n in card["items"]}
    assert own["id"] not in ids and card["total"] == len(tree.nodes) - 1
    assert all(n["parent"] in ids for n in card["items"][1:])  # nothing is left pointing at the dropped node
    root = card["items"][0]
    assert root["event_id"] == home[0] and root["person_id"] == home[1] and own["label"] in root["detail"]


def test_request_words_after_a_focus_person_show_no_failed_lookup(chat):
    """"draft a detailed email to her" with someone in focus binds to the focus without a bogus name lookup step."""
    client = chat("viewer")  # a viewer's draft is written by code from a template: no model
    top = _top(client)
    first = _events(client.post("/api/chat", json={"choice": f"deep:{top['event']['id']}/{top['person']['id']}"}))
    cid = _of(first, "meta")[0]["conversation_id"]
    events = _events(client.post("/api/chat", json={"conversation_id": cid, "message": "draft a detailed email to her"}))
    labels = [s["label"] for s in _of(events, "step")]
    assert not [label for label in labels if label.startswith("Looking up")], labels
    assert [c for c in _of(events, "cards") if c["kind"] == "script"]


def test_script_drops_a_sentence_that_only_restates_the_timing_caveat():
    from api.chat.script import drop_restated

    lines = ["Listing was due 21 Oct 2026 (26 days ago); listing notice not yet seen.",
             "The listing notice has not yet been seen, so the payment timing is not confirmed.",
             "Confidence in these facts: high."]
    assert drop_restated(lines) == [lines[0], lines[2]]
    fresh = ["Selling shareholder: the card amount.", "First proceeds after the sale, so cash is new."]
    assert drop_restated(fresh) == fresh


def test_compare_flags_an_answer_served_from_the_saved_copy(chat, monkeypatch):
    """A compare result whose model answer came from the local cache says so (cached), instead of showing $0 as a run."""
    from api import db  # noqa: F401  (the app database the history uses)
    from api.chat import history, routes

    client = chat("admin")
    me = client.get("/api/me").json()

    def fake_respond(user, conversation_id, question, choice, confirmed, focus, model):
        row = history.ensure(None, user["email"], question)
        yield "meta", {"conversation_id": row["id"], "title": row["title"]}
        yield "text", {"delta": "an answer"}
        history.add_message(row["id"], "assistant", "an answer", extra={"meta": FAKE_META[model]})
        yield "done", {"total_cost_usd": 0.0, "models": [], "tokens": {"input": 0, "output": 0, "cached_input": 0}}

    FAKE_META = {"a": {"local_cache_hits": 1, "provider_calls": 0}, "b": {"local_cache_hits": 0, "provider_calls": 1}}
    monkeypatch.setattr(routes.agent, "respond", fake_respond)
    user = {"email": me["email"], "role": "admin"}
    assert routes._run_once(user, "q", "a")["cached"] is True
    assert routes._run_once(user, "q", "b")["cached"] is False
    assert history.list_for(me["email"]) == []  # the throwaway conversations are gone
