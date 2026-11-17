"""Tier-1 checks for the control tower chat: nothing spends without a valid confirm, numbers are verified,
exact lookups use no model. No network, no API key: every model entry point raises if it is reached."""

from __future__ import annotations

import json
import time

import pytest


def _events(reply) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event, data) pairs."""
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
    """Clients per role with an isolated cost log and model cache; any model call fails the test."""
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
    """The first person in today's queue (read from the stored data, so no name is written here)."""
    return client.get("/api/today?limit=1").json()["items"][0]


def test_spend_action_without_token_returns_estimate_only(chat):
    client = chat("rm")
    top = _top(client)
    events = _events(client.post("/api/chat", json={"choice": f"deep:{top['event']['id']}/{top['person']['id']}"}))
    estimate = _of(events, "estimate")
    assert len(estimate) == 1 and estimate[0]["action"]["kind"] == "deep_dive"
    assert estimate[0]["confirm_token"] and estimate[0]["can_confirm"] is True
    assert estimate[0]["cost_usd_high"] >= estimate[0]["cost_usd_low"] >= 0
    assert all(row["step"] and "cost_usd" in row for row in estimate[0]["breakdown"])
    assert not [c for c in _of(events, "cards") if c["kind"] == "lineage"]  # nothing ran
    assert _of(events, "done")[0]["total_cost_usd"] == 0


def test_bad_or_expired_token_is_403(chat):
    from api.chat import tokens

    client = chat("rm")
    assert client.post("/api/chat", json={"message": "", "confirm_token": "forged.token"}).status_code == 403
    good, _ = tokens.sign("rm@finsight.demo", "deep_dive", "x/y|", 0.01)
    tampered = good[:-2] + ("AA" if not good.endswith("AA") else "BB")
    assert client.post("/api/chat", json={"confirm_token": tampered}).status_code == 403
    expired, _ = tokens.sign("rm@finsight.demo", "deep_dive", "x/y|", 0.01, now=time.time() - 3600)
    assert client.post("/api/chat", json={"confirm_token": expired}).status_code == 403
    someone_else, _ = tokens.sign("admin@finsight.demo", "deep_dive", "x/y|", 0.01)
    assert client.post("/api/chat", json={"confirm_token": someone_else}).status_code == 403


def test_viewer_cannot_confirm_and_rm_is_capped(chat):
    from api.chat import tokens

    viewer = chat("viewer")
    top = _top(viewer)
    events = _events(viewer.post("/api/chat", json={"choice": f"deep:{top['event']['id']}/{top['person']['id']}"}))
    estimate = _of(events, "estimate")[0]
    assert estimate["can_confirm"] is False and estimate["confirm_token"] == ""
    minted, _ = tokens.sign("viewer@finsight.demo", "deep_dive", "x/y|", 0.001)
    assert viewer.post("/api/chat", json={"confirm_token": minted}).status_code == 403
    rm = chat("rm")
    too_big, _ = tokens.sign("rm@finsight.demo", "research", "q", 0.75)
    assert rm.post("/api/chat", json={"confirm_token": too_big}).status_code == 403


def test_verifier_strips_an_invented_number():
    from api.chat.verifier import verify

    data = {"amount": "₹6.08 Cr", "shares": "45,000", "count": 450}
    text, removed = verify("They have ₹6.08 Cr from 45000 shares and another ₹12.40 Cr; 45 more.", data)
    assert "₹6.08 Cr" in text and "45000" in text
    assert "12.40" not in text and "₹ Cr" not in text and " 45 " not in text  # a substring of 450 does not pass
    assert removed == ["₹12.40 Cr", "45"]
    glued, removed = verify("Also ₹500Cr, Rs.700, 50k, 3x and the 2nd tranche; ₹6.08Cr stays.", data)
    assert not any(ch.isdigit() for ch in glued.replace("6.08", "")), glued
    assert "₹6.08Cr" in glued and len(removed) == 5


def test_exact_lookup_uses_no_model(chat):
    client = chat("rm")
    top = _top(client)
    name = top["person"]["name"]
    events = _events(client.post("/api/chat", json={"message": f"What money does {name} have?"}))
    assert not _of(events, "error"), _of(events, "error")
    cards = _of(events, "cards")
    assert cards and cards[0]["kind"] == "person" and cards[0]["items"][0]["person"]["name"] == name
    done = _of(events, "done")[0]
    assert done["total_cost_usd"] == 0 and done["models"] == []
    assert all(step["model"] is None for step in _of(events, "step"))
    text = "".join(d["delta"] for d in _of(events, "text"))
    assert name in text


def test_conversations_are_per_user_and_new_rm_needs_setup(chat):
    rm = chat("rm")
    events = _events(rm.post("/api/chat", json={"message": "Who came into money this week?"}))
    cid = _of(events, "meta")[0]["conversation_id"]
    assert [c["id"] for c in rm.get("/api/chat/conversations").json()] == [cid]
    stored = rm.get(f"/api/chat/conversations/{cid}").json()
    assert [m["role"] for m in stored["messages"]] == ["user", "assistant"] and stored["messages"][1]["cards"]
    admin = chat("admin")
    assert admin.get(f"/api/chat/conversations/{cid}").status_code == 404
    assert rm.delete(f"/api/chat/conversations/{cid}", headers={"Content-Type": "application/json"}).status_code == 200
    assert rm.get("/api/chat/conversations").json() == []
    assert rm.get("/api/me").json()["onboarded"] is True
    assert chat("new.rm").get("/api/me").json() == {**chat("new.rm").get("/api/me").json(), "onboarded": False, "role": "rm"}


def test_deep_dive_reports_cap_and_budget_stops(chat, monkeypatch):
    """Caps per branch kind and the budget each stop the tree, and say so in plain words."""
    from api.chat import deep_dive, tools
    from api.chat.turn import Turn

    client = chat("rm")
    top = _top(client)
    identity = tools.find_person(top["event"]["id"], top["person"]["id"])
    monkeypatch.setattr(deep_dive, "DEEP_DIVE_CAPS", {"same_person": 1, "filing": 0, "family": 0, "process": 0})
    monkeypatch.setattr(deep_dive.enrich_branch, "plan", lambda _identity: [])  # no Bright Data rows, whatever the .env holds
    tree = deep_dive.explore(identity)
    assert [n["kind"] for n in tree.nodes] == ["person", "same_person"]
    assert any(stop.startswith("Stopped: cap of 0") for stop in tree.stops), tree.stops
    tree.budget = 0.0
    node = tree.add(tree.nodes[0]["id"], "process", "Process a related filing", status="candidate")
    tree.process_candidates.append({"node": node, "event_id": "related", "company": "a related company",
                                    "estimate": {"low": 0.001, "high": 0.002}})
    turn = Turn({"email": "rm@finsight.demo", "role": "rm"}, "c", "")
    steps = [data for _kind, data in deep_dive.run_processing(turn, tree, ["related"])]
    assert node["status"] == "stopped" and steps[0]["label"].startswith("Stopped: budget reached")
    assert turn.spent == 0


def test_estimate_expiry_is_unix_seconds_and_viewer_has_none(chat):
    top_client = chat("rm")
    top = _top(top_client)
    choice = {"choice": f"deep:{top['event']['id']}/{top['person']['id']}"}
    rm_estimate = _of(_events(top_client.post("/api/chat", json=choice)), "estimate")[0]
    assert isinstance(rm_estimate["expires_at"], int)
    assert 0 < rm_estimate["expires_at"] - time.time() <= 11 * 60  # seconds, about ten minutes ahead
    viewer_estimate = _of(_events(chat("viewer").post("/api/chat", json=choice)), "estimate")[0]
    assert viewer_estimate["expires_at"] is None


def test_model_text_shown_on_screen_cannot_carry_invented_numbers(monkeypatch):
    from api.chat import planner, router

    monkeypatch.setattr(router.llm, "call", lambda *a, **k: (
        {"intent": "unclear", "multi_step": False, "about_focus": False, "channel": None, "entities": {k: None for k in (
            "person_name", "company", "event_type", "tier", "role_contains", "min_cr", "max_cr", "link")},
         "clarify_question": "I found 3 people named Sharma. Which?"},
        0.0, 1))
    note = router.model_route("who is Sharma", "t").note
    assert "3" not in note and "Sharma" in note

    monkeypatch.setattr(planner.llm, "call", lambda *a, **k: (
        {"steps": [{"tool": "today", "person_name": None, "company": None, "event_type": None, "tier": None,
                    "role_contains": None, "min_cr": None, "max_cr": None, "why": "Top 5 of 40 calls above 12 crore"}]},
        0.0, 1))
    steps, *_ = planner.plan("what is on the list today", "t", [])
    assert not any(ch.isdigit() for ch in steps[0]["why"])
    assert "why" not in planner.run_step(steps[0])["data"]  # the planner's words never reach the answer's data


def test_cash_paid_earlier_counts_as_cash_in_hand_on_the_event(chat):
    event = chat("rm").get("/api/events/wipro_buyback").json()
    assert event["tier_counts"]["cash_now"] == event["people_count"] > 0
    assert event["tier_counts"]["holding"] == 0 and event["cash_cr"]
