"""Chat routing: a holder whose name holds a role word ("... Family Trust") is that holder, not a role filter; and a
follow-up about the one person in focus answers what was asked (lock-in, other events, anything else), not the
calendar and not the same one-line summary every time. No network, no API key: every model entry point is replaced
(tests/test_chat_v2.py). No names are written here: holders come from the stored data."""

from __future__ import annotations

import pytest

from tests.test_chat_v2 import Talk, _of, _text, chat  # noqa: F401  (chat is a fixture)


def _holder_with_role_word() -> str:
    """A callable holder, found by exact name, whose printed name contains a role word (a trust, say)."""
    from api import ask
    from api.chat import tools

    named = [e for e in tools.appearances() if e["list"] == "callable" and len(e["tokens"]) >= 2
             and any(w in e["name"].lower().split() for w in ask.ROLE_WORDS)]
    for entry in sorted(named, key=lambda e: ("trust" not in e["name"].lower(), len(e["tokens"]), e["name"])):  # a trust first
        if tools.reverse_lookup(entry["name"])["data"]["match"] == "exact":
            return entry["name"]
    pytest.skip("no holder name with a role word in the stored data")


def _locked_holder(client) -> tuple[dict, dict]:
    """A person on today's list (one identity) whose call card says when their kept shares are free."""
    from api.chat import tools

    for item in client.get("/api/today?limit=30").json()["items"]:
        found = tools.reverse_lookup(item["person"]["name"])
        if found["data"]["match"] != "exact" or len(found["identities"]) != 1:
            continue
        card = tools.identity_result(found["identities"][0])["cards"][0]["items"][0]
        retained = next((t for t in card.get("timing_detail") or [] if t["key"] == "retained"
                         and t["status"] != "unknown"), None)
        if retained:
            return item, retained
    pytest.skip("no person with a lock-in on today's list")


# ---------- (a) a role word inside a holder's name ----------

def test_a_holder_named_with_a_role_word_is_that_holder_not_a_role_filter(chat):
    from api.chat import router

    chat("admin")
    name = _holder_with_role_word()
    for question in (f"Why is {name} worth a call first?",
                     f"Walk me through today's brief. Why is {name.upper()} worth a call first?"):
        route = router.rules(question)
        assert route is not None and route.intent == "person", (question, route)
        assert route.args["name"].lower() == name.lower()
        assert "role_contains" not in (route.args.get("filters") or {})
    # A role word on its own is still a role filter.
    for question in ("Show me trusts", "Which trusts got cash?", "promoters above 50 cr"):
        route = router.rules(question)
        assert route.intent == "search_people" and route.args["filters"].get("role_contains"), question


def test_a_holder_question_shows_that_holder_for_a_zero_cost_role(chat):
    client = chat("viewer")
    name = _holder_with_role_word()
    events = Talk(client).send(message=f"Why is {name} worth a call first?")
    people = [c for c in _of(events, "cards") if c["kind"] == "person"]
    assert people and people[0]["items"][0]["person"]["name"].lower() == name.lower()
    assert "Role:" not in _text(events) and "No one matches" not in _text(events)


def test_the_model_cannot_bring_the_role_filter_back(chat, monkeypatch):
    from api import ask
    from api.chat import llm as chat_llm
    from api.chat import router

    chat("admin")
    name = _holder_with_role_word()
    question = f"Why is {name} worth a call first?"
    word = next(w for w in ask.ROLE_WORDS if w in name.lower().split())
    entities = {"person_name": None, "company": None, "event_type": None, "tier": None, "role_contains": word,
                "min_cr": None, "max_cr": None, "link": None}
    monkeypatch.setattr(chat_llm, "call", lambda *a, **k: ({"intent": "search_people", "multi_step": False,
                                                            "about_focus": False, "channel": None,
                                                            "entities": entities, "clarify_question": None}, 0.0, 1))
    route = router.model_route(question, "t", "")
    assert "role_contains" not in (route.args.get("filters") or {})


# ---------- (b) follow-ups about the person in focus ----------

def test_lock_in_follow_ups_answer_for_the_person_in_focus(chat):
    client = chat("admin")
    item, retained = _locked_holder(client)
    talk = Talk(client)
    first = talk.send(message=f"What money does {item['person']['name']} have?")
    summary = _text(first)
    answers = []
    for question in ("and the lock-in, when do those shares unlock?", "when do her locked-in shares unlock?"):
        events = talk.send(message=question)
        kinds = [c["kind"] for c in _of(events, "cards")]
        assert "calendar" not in kinds, question
        people = [c for c in _of(events, "cards") if c["kind"] == "person"]
        assert people and people[0]["items"][0]["person"]["id"] == item["person"]["id"], question
        text = _text(events)
        assert retained["display"] in text, (question, text)
        assert text != summary
        assert _of(events, "done")[0]["total_cost_usd"] == 0
        answers.append(text)
    # A plain "what money does she have?" is a lookup of the same person, not a search for a holder called "she".
    events = talk.send(message="what money does she have?")
    assert not _of(events, "clarify")
    people = [c for c in _of(events, "cards") if c["kind"] == "person"]
    assert people and people[0]["items"][0]["person"]["id"] == item["person"]["id"]


def test_other_money_follow_up_lists_their_events_not_the_events_list(chat):
    from api.chat import tools

    client = chat("admin")
    item, _retained = _locked_holder(client)
    identity = tools.reverse_lookup(item["person"]["name"])["identities"][0]
    talk = Talk(client)
    summary = _text(talk.send(message=f"What money does {item['person']['name']} have?"))
    events = talk.send(message="what other money does she have across events?")
    assert "events" not in [c["kind"] for c in _of(events, "cards")]
    text = _text(events)
    assert text != summary
    for app in identity["appearances"][:3]:
        assert app["company"] in text and app["amount"] in text
    if len(identity["appearances"]) == 1:
        assert "only" in text.lower()
    lock = _text(talk.send(message="when do her locked-in shares unlock?"))
    assert lock not in (text, summary)


def test_any_other_follow_up_is_answered_by_the_writer_from_their_facts(chat, monkeypatch):
    from tools import llm as tools_llm

    client = chat("admin")
    item, retained = _locked_holder(client)
    talk = Talk(client)
    talk.send(message=f"What money does {item['person']['name']} have?")
    prompts: list = []

    def fake_stream(step, messages, *args, **kwargs):
        prompts.append(messages[-1]["content"])
        yield "Here is the written answer. "

    monkeypatch.setattr(tools_llm, "llm_stream", fake_stream)
    events = talk.send(message="Write a detailed one-page briefing on her for my manager")
    assert len(prompts) == 1 and item["person"]["name"] in prompts[0] and retained["display"] in prompts[0]
    assert "Here is the written answer." in _text(events)
    assert [c for c in _of(events, "cards") if c["kind"] == "person"]


def test_a_zero_cost_role_is_told_the_card_is_not_a_written_answer(chat):
    client = chat("viewer")
    item, _retained = _locked_holder(client)
    talk = Talk(client)
    summary = _text(talk.send(message=f"What money does {item['person']['name']} have?"))
    text = _text(talk.send(message="Write a detailed one-page briefing on her for my manager"))
    assert text != summary and text.startswith("I can only")


def test_listing_questions_with_someone_in_focus_stay_listings(chat):
    client = chat("admin")
    item, _retained = _locked_holder(client)
    talk = Talk(client)
    talk.send(message=f"What money does {item['person']['name']} have?")
    events = talk.send(message="Upcoming money dates")
    assert "calendar" in [c["kind"] for c in _of(events, "cards")]


def test_a_bare_these_about_the_list_on_screen_is_not_the_person_in_focus():
    from types import SimpleNamespace as NS

    from api.chat import agent, router

    focus = [{"kind": "person", "event_id": "e", "person_id": "p", "label": "A Holder"}]
    turn = NS(state={"focus": focus})
    question = "which of these are promoters?"
    route = router.Route("search_people", {"filters": {"role_contains": "promoter"}})
    assert agent.pronoun_focus(turn, question, route) is None
    pointed = agent.pronoun_focus(turn, "and the lock-in, when do those shares unlock?", router.Route("calendar"))
    assert pointed.intent == "person" and pointed.args == {"entities": focus, "channel": "call", "ask": "lock_in"}
