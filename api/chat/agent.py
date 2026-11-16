"""The chat agent: one message in, a stream of (event_type, data) out (api/CHAT_CONTRACT.md).

understand (rules, then the fast model) -> clarify when ambiguous -> estimate + stop, for anything that spends
-> tools (code) -> write (template / fast / strong model) -> verify every number -> stream. A confirmed action
(a valid confirm token, checked in api/chat/routes.py before the stream starts) runs exactly that action.

v2 (api/CHAT_CONTRACT.md): every turn loads the conversation's memory (api/chat/memory.py), compresses old turns
past a threshold, binds "him" / "the call" / a first name to the focus in code, asks back only among real
candidates, applies time windows to money dates, writes call scripts, streams model prose sentence by sentence
(each sentence verified first), and ends with a `context` event and per-message meta (tokens, cached tokens,
cost, focus).
"""

from __future__ import annotations

import os
import re
import traceback

from api import store
from api.chat import actions, clarify, deep_dive, enrich_branch, history, llm, memory, planner, router, script, stream, tokens, tools
from api.chat import estimate as est
from api.chat import verifier, writer
from api.chat import windows as win
from api.chat.turn import Turn
from config import enrichment as cfg_enrich
import config.chat as chat_config
from config.chat import KEEP_TURNS, MAX_ANSWER_WORDS, QUESTION_CAP_USD, fast_model, strong_model
from tools.llm import LLMError


def _processed_count() -> int:
    return sum(1 for e in store.load_events() if e["processed"])


def _events_label() -> str:
    count = _processed_count()
    return f"Checking {count} {'event' if count == 1 else 'events'}"


# ---------- entry ----------

def apply_focus(state: dict, focus: list[dict]) -> None:
    """The RM edited the "Talking about" chip: that list is now the focus (each person checked against the data)."""
    entities = []
    for item in focus[:3]:
        if item.get("kind") == "person" and item.get("event_id") and item.get("person_id"):
            who = tools.find_person(item["event_id"], item["person_id"])
            if who:
                entities.append(memory.person_entity(item["event_id"], item["person_id"], who["name"],
                                                     _company(who, item["event_id"])))
        elif item.get("kind") == "event" and item.get("event_id") and store.find_event(item["event_id"]):
            entities.append(memory.event_entity(item["event_id"], item.get("label") or ""))
    dropped = [e for e in state["focus"] if memory.key(e) not in {memory.key(x) for x in entities}]
    state["focus"] = entities
    state["recent"] = [e for e in dropped + state["recent"]][:12]
    state["pending"] = None


def respond(user: dict, conversation_id: str | None, message: str, choice: str | None, confirmed: dict | None,
            focus: list[dict] | None = None, model: str | None = None):
    """Generator of (event_type, data) for one request. Always ends with 'done'.

    model: a model from config.chat.ALLOWED_MODELS chosen for this conversation (stored in its memory, so later
    turns keep it); None keeps the conversation's stored choice, else the defaults. The choice is set around
    every step of the generator because the server resumes it on different threads.
    """
    chosen = model if model in chat_config.allowed_ids() else None
    if chosen is None and conversation_id:
        stored = memory.load(conversation_id).get("model")
        chosen = stored if stored in chat_config.allowed_ids() else None
    inner = _respond(user, conversation_id, message, choice, confirmed, focus, chosen, model is not None)
    while True:
        token = chat_config.choose(chosen)
        try:
            item = next(inner)
        except StopIteration:
            return
        finally:
            chat_config._CHOSEN.reset(token)
        yield item


def _respond(user: dict, conversation_id: str | None, message: str, choice: str | None, confirmed: dict | None,
             focus: list[dict] | None, chosen: str | None, set_choice: bool):
    message = (message or "").strip()[:2000]
    shown = message or _choice_words(choice) or ("Run the confirmed action" if confirmed else "")
    conversation = history.ensure(conversation_id, user["email"], shown)
    turn = Turn(user, conversation["id"], message)
    turn.prior = history.messages(conversation["id"])
    turn.state = memory.load(conversation["id"])
    if focus is not None:
        apply_focus(turn.state, focus)
    if set_choice:
        turn.state["model"] = chosen  # the switcher: kept for the conversation's later turns
    yield "meta", {"conversation_id": conversation["id"], "title": conversation["title"]}
    extra = {"choice": choice} if choice else {}
    if confirmed:
        extra["confirmed"] = True  # lets a reopened thread tell the estimate before this message was run
    history.add_message(conversation["id"], "user", shown, extra=extra or None)
    try:
        yield from prepare_context(turn)
        if confirmed:
            yield from run_confirmed(turn, confirmed)
        elif choice:
            yield from handle_choice(turn, choice)
        elif message:
            yield from handle_question(turn, message)
        else:
            yield "error", {"message": "Type a question, or pick one of the suggestions."}
    except Exception as exc:  # shown in RM words; the trace goes to the server log
        traceback.print_exc()
        reason = str(exc) if isinstance(exc, actions.TargetError) else "Something went wrong while answering."
        for step in turn.steps:
            if step["status"] == "running":
                yield from turn.end(step, "failed")
        yield "error", {"message": reason}
        turn.extra["error"] = reason
    yield from finish(turn)


def finish(turn: Turn):
    """Focus, context and done events; the assistant message with its meta; the memory saved."""
    state = turn.state
    changed = memory.learn_from_cards(state, turn.cards)
    if turn.focus_set:
        changed = memory.set_focus(state, turn.focus_set) or changed
    if changed:
        yield "focus", {"focus": memory.public(state["focus"])}
    usage = llm.usage_for(turn.id, pop=True)
    info = turn.context_info
    context = {"prompt_tokens": usage["input"], "cached_tokens": usage["cached_input"],
               "history_tokens_before": info.get("history_tokens_before", 0),
               "history_tokens_after": info.get("history_tokens_after", 0), "compressed": bool(info.get("compressed")),
               "turns_kept": info.get("turns_kept", 0), "focus": memory.public(state["focus"])}
    yield "context", context
    done = {**turn.done_event(), "tokens": {"input": usage["input"], "output": usage["output"],
                                            "cached_input": usage["cached_input"]},
            "saved_usd_by_cache": round(usage["saved_usd"], 6)}
    meta = {"models": done["models"], "tokens_in": usage["input"], "tokens_out": usage["output"],
            "cached_in": usage["cached_input"], "cache_write": usage["cache_write"], "cost_usd": done["total_cost_usd"],
            "saved_usd_by_cache": done["saved_usd_by_cache"], "context_tokens": info.get("history_tokens_after", 0),
            "compressed": context["compressed"], "focus": context["focus"], "seconds": done["seconds"],
            "provider_calls": usage["provider_calls"], "local_cache_hits": usage["local_hits"],
            "by_step": usage["by_step"], "context": context, "chat_model": chat_config.chosen_model()}
    history.add_message(turn.conversation_id, "assistant", turn.text.strip(), cards=turn.cards,
                        steps=turn.public_steps(), estimate=turn.estimate,
                        extra={k: v for k, v in (("clarify", turn.clarify), ("done", done), ("meta", meta)) if v})
    memory.save(turn.conversation_id, state)
    yield "done", done


def prepare_context(turn: Turn):
    """Compress old turns when the history passes the threshold, then build the context text for model calls."""
    state, prior = turn.state, turn.prior
    before = memory.tokens(memory.context_text(prior, state))  # the same measure as "after"
    compressed = False
    if memory.needs_compression(prior, state):
        allow = turn.user["role"] != "viewer"
        step = yield from turn.begin("Compressing earlier turns", model=fast_model() if allow else None)
        record = memory.compress(prior, state, turn.id, fast_model(), allow)
        how = "summarised by the cheap model, numbers checked" if record["by"] == "model" else "summarised by code"
        removed = f"; removed {len(record['removed'])} unverified numbers" if record["removed"] else ""
        yield from turn.end(step, detail=f"{record['messages']} older messages {how}: about {record['tokens_before']} "
                                         f"to {record['tokens_after']} tokens{removed}",
                            cost=record["cost_usd"], calls=record["calls"], model=record["model"])
        compressed = True
    turn.context = memory.context_text(prior, state)
    kept = sum(1 for m in prior[state.get("compressed_through", 0):] if m.get("role") == "user")
    turn.context_info = {"history_tokens_before": before, "history_tokens_after": memory.tokens(turn.context),
                         "compressed": compressed, "turns_kept": min(kept, max(kept, KEEP_TURNS))}


def _choice_words(choice: str | None) -> str:
    """What a clicked option means, for the conversation history."""
    if not choice:
        return ""
    kind, _, rest = choice.partition(":")
    if kind in ("person", "script", "deep"):
        ids, _, channel = rest.partition("|")
        event_id, _, person_id = ids.partition("/")
        who = tools.find_person(event_id, person_id)
        name = who["name"] if who else "this person"
        return {"person": f"What money does {name} have?", "deep": f"Deep dive on {name}",
                "script": f"{script.title_for(channel or 'call', name)}"}[kind]
    return {"lookup": f"Look up {rest}", "process": "Process this event", "ask": rest}.get(kind, choice)


# ---------- understanding ----------

def handle_question(turn: Turn, question: str):
    """Route a typed question (rules, then the conversation's memory, then the fast model), then act on it."""
    step = yield from turn.begin("Understanding your question")
    route = router.rules(question)
    pointed = pronoun_focus(turn, question, route)
    if pointed:
        route = pointed
        how = {"lock_in": "their lock-in", "elsewhere": "their money across events"}.get(pointed.args["ask"])
        yield from turn.end(step, detail=f"A question about {how or 'the person in focus'}, matched from this "
                                         "conversation (no model needed to read it)")
    elif route:
        yield from turn.end(step, detail="Read by rules, no model needed")
    else:
        route = followup(turn, question)
        if route:
            who = ", ".join(e["label"] for e in route.args.get("entities") or []) or route.args.get("name")
            yield from turn.end(step, detail=f"A follow-up about {who}, matched from this conversation (no model)")
    if route is None and turn.user["role"] == "viewer":
        route = router.Route("keyword", {"question": question}, by="fallback")
        yield from turn.end(step, detail="Matched your words in code (your role asks $0 questions only)")
    elif route is None:
        try:
            known = tuple(e["label"] for e in turn.state["focus"] + turn.state["candidates"])
            route = router.model_route(question, turn.id, turn.context, known)
            yield from turn.end(step, detail=f"Read as: {route.intent.replace('_', ' ')}", cost=route.cost,
                                calls=route.calls, model=route.model)
        except LLMError as exc:
            cost, calls = getattr(exc, "chat_cost", (0.0, 0))
            route = router.Route("keyword", {"question": question}, by="fallback")
            yield from turn.end(step, detail="The model did not answer; matched your words in code", cost=cost,
                                calls=calls, model=fast_model())
    if route.by in ("rules", "model") and route.intent not in PERSON_INTENTS:
        turn.state["pending"] = None  # a new question replaces an unanswered clarify
    yield from dispatch(turn, route, question)


PERSON_INTENTS = ("person", "deep_dive", "call_script", "draft_message")
# Intents a time word ("lock-in", "this week") can wrongly claim when the message is really about the person in focus.
LISTING_INTENTS = ("calendar", "today", "search_people", "search_events")
# "those shares" points at the person in focus too (kept here: memory's pronouns also drive clarify replies). A bare
# "these" is not: "which of these are promoters?" is about the list on screen.
_POINTING = re.compile(r"\b(?:those|these|the|her|his|their)\s+(?:locked[\s-]?in\s+)?(?:shares|holdings?|stakes?)\b",
                       re.I)
# What a follow-up about the person in focus asks; anything else is answered from their facts by the writer.
_LOCK_ASK = re.compile(r"\b(?:lock-?ins?|locked[\s-]?in|lock[\s-]?ups?|unlocks?|unlocked|unlocking|free to sell)\b", re.I)
_ELSEWHERE_ASK = re.compile(r"\b(?:other (?:money|events?|filings?|deals?|companies|holdings?)|across (?:all )?"
                            r"(?:the )?(?:events?|filings?|companies|deals)|elsewhere|anywhere else)\b", re.I)


def follow_up_ask(question: str) -> str:
    """lock_in | elsewhere | question: what a follow-up about one person asks."""
    if _LOCK_ASK.search(question):
        return "lock_in"
    if _ELSEWHERE_ASK.search(question):
        return "elsewhere"
    return "question"


def pronoun_focus(turn: Turn, question: str, route: router.Route | None) -> router.Route | None:
    """"When does he get the money and when is the lock-in over?" with one person in focus: the pronoun points at them,
    so the answer is that person's dates, not a calendar of everyone. Only when the rules chose a list or the calendar,
    the message has a pronoun (or "those shares"), and it names no company (a named company or person is a different
    question). args["ask"] says what was asked, so the answer is that, not the same summary every time."""
    if route is None or route.intent not in LISTING_INTENTS or not (memory.has_pronoun(question)
                                                                    or _POINTING.search(question)):
        return None
    focus = [e for e in turn.state.get("focus") or [] if e.get("kind") == "person"]
    if len(focus) != 1:
        return None
    lowered = question.lower()
    if any(name and name.lower() in lowered for name in tools.companies()):
        return None
    return router.Route("person", {"entities": focus, "channel": "call", "ask": follow_up_ask(question)}, by="memory")


def followup(turn: Turn, question: str) -> router.Route | None:
    """A short message that only points at someone ("its about kusum only", "the second one", "him"), or a reply to
    a clarify: complete the pending request, else repeat the last person-scoped request, else show the person."""
    state = turn.state
    pending = state.get("pending") or {}
    ref = memory.resolve(question, state)
    short = len(question.split()) <= 8
    intent = pending.get("intent") or (state.get("last_intent") if state.get("last_intent") in
                                       ("call_script", "draft_message") else None) or "person"
    channel = pending.get("channel") or state.get("last_channel") or "call"
    if ref["how"] in ("name", "ordinal") and short:
        return router.Route(intent, {"entities": ref["entities"], "channel": channel}, by="memory")
    if ref["how"] == "focus" and ref["pronoun"] and short and pending:
        return router.Route(intent, {"entities": ref["entities"], "channel": channel}, by="memory")
    name = router.leftover_name(question)
    if pending and name and short:
        return router.Route(intent, {"name": name, "channel": channel}, by="memory")
    return None


def handle_choice(turn: Turn, choice: str):
    """A clicked clarify option: its value says what to do."""
    kind, _, rest = choice.partition(":")
    if kind == "lookup":
        yield from dispatch(turn, router.Route("person", {"name": rest}, by="choice"), f"What money does {rest} have?")
    elif kind in ("deep", "person", "script"):
        ids, _, channel = rest.partition("|")
        event_id, _, person_id = ids.partition("/")
        identity = tools.find_person(event_id, person_id)
        if not identity:
            yield "error", {"message": "That person is no longer in the call lists."}
            return
        entity = memory.person_entity(event_id, person_id, identity["name"], _company(identity, event_id))
        turn.state["pending"] = None
        if kind == "deep":
            turn.focus_set = [entity]
            yield from estimate_deep_dive(turn, identity, event_id, person_id)
        elif kind == "person":
            yield from show_person(turn, entity, f"What money does {identity['name']} have?")
        else:
            yield from make_script(turn, entity, channel or "call", _choice_words(choice))
    elif kind == "process":
        yield from dispatch(turn, router.Route("process_event", {"target": rest}, by="choice"), f"Process {rest}")
    elif kind == "ask":
        yield from handle_question(turn, rest)
    else:
        yield from handle_question(turn, choice)


def ask_back(turn: Turn, payload: dict, pending: dict | None = None):
    """Emit a clarify event (the turn ends there). pending: what the answer should complete."""
    yield from turn.note("Asking a quick question")
    turn.clarify = payload
    if pending:
        turn.state["pending"] = pending
    yield "clarify", payload


def _company(identity: dict, event_id: str) -> str | None:
    return next((a["company"] for a in identity.get("appearances") or [] if a["event_id"] == event_id), None)


def _filler_leftover(name: str, question: str) -> bool:
    """True when the unmatched leftover is not name-shaped: the message points at someone ("him", "the call"), or
    the leftover is a lowercase word the RM did not capitalise as a name (every capitalised word in the message
    that is not its first word counts as a typed name)."""
    if memory.has_pronoun(question):
        return True
    words = {w.lower() for w in name.replace("'", " ").split()}
    parts = question.split()
    typed = {w.strip(".,?!'\"").lower() for w in (parts if len(parts) <= 2 else parts[1:])
             if w[:1].isupper() and w.lower() != "i"}
    return not (words & typed) and len(words) <= 2


def pick_person(turn: Turn, route: router.Route, question: str, then: str):
    """Who a person-scoped request is about: the entities the route carries, a typed name, or the focus.

    Returns the entity, or None after asking back (options: the real candidates, never the home chips).
    """
    state, args = turn.state, route.args
    pending = {"intent": route.intent, "channel": args.get("channel") or "call"}
    entities = args.get("entities")
    if entities is None and args.get("name"):
        name = args["name"]
        focus = [e for e in state["focus"] if e.get("kind") == "person"]
        if focus and _filler_leftover(name, question) and not tools.reverse_lookup(name)["identities"]:
            found = []  # request words, not a name ("detailed", "thorough follow- plan"): no failed-looking lookup step
        else:
            found = yield from find(turn, name)
        if len(found) == 1:
            first = found[0]["appearances"][0]
            return memory.person_entity(first["event_id"], first["person_id"], found[0]["name"], first["company"])
        if len(found) > 1:
            yield from ask_back(turn, clarify.which_person(name, found, then=then), pending)
            return None
        entities = memory.name_matches(name, state)
        if not entities:
            # A leftover word is a name only when it finds someone (lookup or memory). Otherwise it is request
            # filler ("when", "keep", "tomorrow s") and the person is whoever the conversation is about.
            focus = [e for e in state["focus"] if e.get("kind") == "person"]
            if not focus or not _filler_leftover(name, question):
                yield from ask_back(turn, clarify.no_match(name, then), pending)
                return None
            entities = None
    if entities is None:
        entities = memory.resolve(question, state)["entities"]
    people = [e for e in entities if e.get("kind") == "person"]
    if len(people) == 1:
        return people[0]
    if len(people) > 1:
        yield from ask_back(turn, clarify.among(people, then), pending)
        return None
    listed = [e for e in state.get("candidates") or [] if e.get("kind") == "person"]
    if listed:
        verb = clarify.among(listed, then)["question"].split("?")[0]
        yield from ask_back(turn, clarify.among(listed, then, f"{verb}? Pick from the list we just looked at, or type "
                                                             "a name."), pending)
    else:
        yield from ask_back(turn, clarify.need_person(then), pending)
    return None


# ---------- acting ----------

def dispatch(turn: Turn, route: router.Route, question: str):
    """Do what the route says."""
    intent, args = route.intent, route.args
    window = win.parse(question)
    if intent in ("call_script", "draft_message"):
        channel = args.get("channel") or ("whatsapp" if intent == "draft_message" else "call")
        entity = yield from pick_person(turn, route, question, f"script:{channel}")
        if entity:
            yield from make_script(turn, entity, channel, question, reuse=route.by == "memory")
        return
    if intent in ("person", "deep_dive") and not args.get("name") and (args.get("entities") is not None or
                                                                       args.get("about_focus") or route.by == "memory"
                                                                       or memory.has_pronoun(question)):
        entity = yield from pick_person(turn, route, question, "deep" if intent == "deep_dive" else "person")
        if not entity:
            return
        if intent == "person":
            yield from show_person(turn, entity, question, route if route.by == "model" or args.get("ask") else None)
        else:
            identity = tools.find_person(entity["event_id"], entity["person_id"])
            if identity:
                turn.focus_set = [entity]
                yield from estimate_deep_dive(turn, identity, entity["event_id"], entity["person_id"])
        return
    if intent == "help":
        yield from answer(turn, question, "help", {}, route)
    elif intent == "today":
        yield from lookup(turn, question, "today", lambda: tools.today(window=window), route)
    elif intent == "search_people":
        if not args.get("filters"):
            yield from lookup(turn, question, "keyword", lambda: tools.keyword_people(question), route)
        else:
            yield from lookup(turn, question, "search_people",
                              lambda: tools.search_people(args["filters"], window=window), route)
    elif intent == "search_events":
        yield from lookup(turn, question, "search_events",
                          lambda: tools.search_events(args.get("event_type"), args.get("company")), route)
    elif intent == "calendar":
        yield from lookup(turn, question, "calendar",
                          lambda: tools.calendar(args.get("start"), args.get("end"), window=args.get("window") or window),
                          route)
    elif intent == "keyword":
        yield from lookup(turn, question, "keyword", lambda: tools.keyword_people(args.get("question") or question), route)
    elif intent == "person":
        yield from person(turn, question, args.get("name") or "", route)
    elif intent == "deep_dive":
        name = args.get("name") or ""
        entity = yield from pick_person(turn, route, question, "deep")
        if entity:
            identity = tools.find_person(entity["event_id"], entity["person_id"])
            if identity:
                turn.focus_set = [entity]
                turn.state["last_intent"] = "deep_dive"
                yield from estimate_deep_dive(turn, identity, entity["event_id"], entity["person_id"])
    elif intent == "process_event":
        if not args.get("target"):
            yield from ask_back(turn, clarify.need_event(question))
            return
        try:
            target = actions.resolve(args["target"])
        except actions.TargetError as exc:
            yield from turn.note("Checking the link", "failed", str(exc))
            yield from turn.say(str(exc))
            return
        yield from estimate_process(turn, target)
    elif intent == "research":
        yield from estimate_research(turn, args.get("question") or question)
    else:
        yield from ask_back(turn, clarify.unclear(route.note, turn.state))


def lookup(turn: Turn, question: str, intent: str, run, route: router.Route):
    """A $0 tool call, its cards, then the answer."""
    step = yield from turn.begin(_events_label())
    result = run()
    count = result["data"].get("count")
    yield from turn.end(step, detail=f"{count} found" if count is not None else None)
    for card in result["cards"]:
        yield from turn.card(card)
    yield from answer(turn, question, intent, result["data"], route)


def find(turn: Turn, name: str):
    """Reverse lookup as a step; returns the identities."""
    step = yield from turn.begin(f"Looking up “{name}” in {_processed_count()} events")
    found = tools.reverse_lookup(name)
    identities = found["identities"]
    words = {"exact": "exact name match", "partial": "partial name match", "none": "no match"}[found["data"]["match"]]
    yield from turn.end(step, detail=f"{len(identities)} {'person' if len(identities) == 1 else 'people'}, {words}")
    return identities


def person(turn: Turn, question: str, name: str, route: router.Route):
    """What money does this person have: reverse lookup, clarify when several match."""
    if not name:
        entity = yield from pick_person(turn, route, question, "person")
        if entity:
            yield from show_person(turn, entity, question)
        return
    identities = yield from find(turn, name)
    if not identities:
        named = memory.name_matches(name, turn.state)
        if len(named) == 1:
            yield from show_person(turn, named[0], question, route if route.args.get("ask") else None)
            return
        yield from ask_back(turn, clarify.no_match(name), {"intent": "person"})
        return
    if len(identities) > 1:
        yield from ask_back(turn, clarify.which_person(name, identities), {"intent": "person"})
        return
    turn.state["last_intent"], turn.state["pending"] = "person", None
    result = tools.identity_result(identities[0])
    for card in result["cards"]:
        yield from turn.card(card)
    yield from answer_about(turn, question, identities[0], result["data"], route)


def answer_about(turn: Turn, question: str, identity: dict, data: dict, route: router.Route | None):
    """The answer for one person. route.args["ask"] (a question about them, not a plain lookup): lock_in and
    elsewhere are written by code from their stored facts ($0); any other question is written by the model from
    those facts, or, when the model may not run, says it can only show what is stored."""
    ask = (route.args.get("ask") if route else None) or None
    if not ask:
        yield from answer(turn, question, "person", data, route or router.Route("person", by="choice"))
        return
    facts = {**data, "lock_in": tools.lock_in(identity)}
    if ask in ("lock_in", "elsewhere"):
        yield from answer(turn, question, f"person_{ask}", facts, router.Route("person", by="memory"))
    else:
        yield from answer(turn, question, "person_question", facts, router.Route("person", by="model"))


def show_person(turn: Turn, entity: dict, question: str, route: router.Route | None = None):
    """One remembered person's money: their identity across events, the call card, then the answer.

    A free-form question the model routed ("anything to be careful about with her?") is answered by the model
    from this person's facts; a click or a plain lookup gets the $0 template; a follow-up the rules read about
    them (route.args["ask"]) answers what was asked (answer_about).
    """
    identity = tools.find_person(entity["event_id"], entity["person_id"])
    if not identity:
        yield "error", {"message": "That person is no longer in the call lists."}
        return
    turn.state["last_intent"], turn.state["pending"] = "person", None
    turn.focus_set = [entity]
    result = tools.identity_result(identity)
    for card in result["cards"]:
        yield from turn.card(card)
    yield from answer_about(turn, question, identity, result["data"], route)


def _earlier_script(turn: Turn, entity: dict, channel: str) -> dict | None:
    """The last script card for this person and channel already shown in this conversation."""
    for message in reversed(turn.prior):
        for card in message.get("cards") or []:
            who = card.get("person") or {}
            if card.get("kind") == "script" and card.get("channel", "call") == channel and \
                    (who.get("event_id"), who.get("person_id")) == (entity["event_id"], entity["person_id"]):
                return card
    return None


def make_script(turn: Turn, entity: dict, channel: str, request: str, reuse: bool = False):
    """A call script or message draft for one person: model words with placeholders, every number filled by code.

    reuse: a follow-up that only points at the person ("its about kusum only") reuses the words of the script
    already written for them in this conversation, refilled from today's call card ($0). Any new request
    ("make it shorter", "a new one") writes a new script.
    """
    state = turn.state
    state["pending"], state["last_intent"], state["last_channel"] = None, (
        "call_script" if channel == "call" else "draft_message"), channel
    turn.focus_set = [entity]
    step = yield from turn.begin(f"Reading {entity['label']}'s call card")
    found = tools.person_card(entity["event_id"], entity["person_id"])
    if not found["cards"]:
        yield from turn.end(step, "failed", "This person is no longer in the call lists")
        yield from turn.say("I could not find that person's call card any more. Try looking them up by name.")
        return
    card = {**found["cards"][0]["items"][0]}
    yield from turn.end(step, detail="Amount, timing, why now and the brief, as stored from the filing")
    what = {"call": "call script", "whatsapp": "WhatsApp draft", "email": "email draft"}[channel]
    earlier = _earlier_script(turn, entity, channel) if reuse else None
    if earlier and earlier.get("draft"):
        yield from turn.note("Reusing the script from earlier in this conversation",
                             detail="Same words, numbers refilled from the current call card; no model, $0")
        script_card, removed = script.card_for(card, script.ScriptDraft.model_validate(earlier["draft"]), channel,
                                               "reused", turn.user.get("name") or "")
        written = "reused"
    else:
        model, draft, written = strong_model(), None, "template"
        if turn.user["role"] != "viewer":
            guess = est.chat_step("script", "Writing the call script", model,
                                  script.prompt_chars(card, request, turn.context))
            if turn.spent + guess["cost_usd_high"] <= QUESTION_CAP_USD:
                write = yield from turn.begin(f"Writing the {what}", model=model)
                try:
                    draft, cost, calls = script.write(card, channel, request, turn.context, model, turn.id)
                    written = "model"
                    yield from turn.end(write, cost=cost, calls=calls, detail="Words only; placeholders for every number")
                except Exception as exc:  # any model failure: the code template writes it instead
                    cost, calls = getattr(exc, "chat_cost", (0.0, 0))
                    yield from turn.end(write, "failed", "The model did not answer; written by code from a template",
                                        cost=cost, calls=calls)
        if draft is None:
            draft = script.template_draft(channel)
            if not any(st["label"] == f"Writing the {what}" for st in turn.steps):
                yield from turn.note(f"Writing the {what}", detail="Written by code from a template, no model")
        check = yield from turn.begin("Filling every number from the call card")
        script_card, removed = script.card_for(card, draft, channel, written, turn.user.get("name") or "")
        filled = sum(len(verifier.numbers_in(line)) for sec in script_card["sections"] for line in sec["lines"])
        gone = f"; removed {len(removed)} digits the model typed" if removed else ""
        said = {0: "No numbers needed", 1: "The one number was filled by code from the call card"}.get(
            filled, f"All {filled} numbers filled by code from the call card")
        yield from turn.end(check, detail=said + gone)
    yield from turn.card(script_card)
    words = writer.template("script", {"what": what, "name": entity["label"], "role": card["person"].get("role"),
                                       "company": card["event"]["company"], "reused": written == "reused"})
    yield from check_and_say(turn, words, {"card": tools.compact(card), "what": what})


def answer(turn: Turn, question: str, intent: str, data: dict, route: router.Route | None, strong: bool = False,
           cap: float = QUESTION_CAP_USD):
    """Write (template or model), verify every number, then stream the prose.

    A model writes through a provider stream; each sentence is verified before it is sent (api/chat/stream.py).
    """
    by_code = not strong and (route is None or route.by in ("rules", "choice", "fallback", "memory")
                              or turn.user["role"] == "viewer")
    model = strong_model() if strong else fast_model()
    if not by_code:
        guess = est.chat_step("write", "Writing the answer", model, writer.prompt_chars(question, data, turn.context))
        if turn.spent + guess["cost_usd_high"] > cap:
            by_code = True
    if by_code:
        step = yield from turn.begin("Writing the answer")
        prose = writer.template(intent, data)
        yield from turn.end(step, detail="Written from the data by code, no model")
        yield from check_and_say(turn, prose, data)
        return
    write = yield from turn.begin("Writing the answer", model=model)
    check = yield from turn.begin("Checking every number")
    checker, sentences, sent = stream.Checked(data, MAX_ANSWER_WORDS), stream.Sentences(), 0
    source = writer.stream(question, data, model, turn.id, turn.context)
    try:
        for delta in source:
            for sentence in sentences.feed(delta):
                clean = checker.take(sentence)
                if clean:
                    sent += 1
                    yield from turn.sentence(clean)
        for sentence in sentences.flush():
            clean = checker.take(sentence)
            if clean:
                sent += 1
                yield from turn.sentence(clean)
        yield from turn.end(write, cost=source.cost, calls=source.calls, detail=f"Streamed {sent} sentences")
    except LLMError as exc:
        cost, calls = getattr(exc, "chat_cost", (0.0, 0))
        yield from turn.end(write, detail="The model stopped; the rest is written from the data by code", cost=cost,
                            calls=calls)
        if not sent:
            for sentence in stream.split(writer.template(intent, data) or "Here is what the data shows."):
                clean = checker.take(sentence)
                if clean:
                    yield from turn.sentence(clean)
    yield from end_check(turn, check, checker.total, checker.removed)
    yield from turn.final()


def end_check(turn: Turn, step: dict, total: int, removed: list[str]):
    """Finish the 'Checking every number' step with what it found."""
    if removed:
        detail = f"Removed {len(removed)} number{'s' if len(removed) != 1 else ''} not in the data: {', '.join(removed[:5])}"
    else:
        detail = ("The one number matches the data" if total == 1 else f"All {total} numbers match the data") if total \
            else "No numbers in the prose; the cards carry them"
    turn.extra["verifier"] = {"checked": total, "removed": removed}
    yield from turn.end(step, detail=detail)


def check_and_say(turn: Turn, prose: str, data: object):
    """The verifier step, then the verified prose (sentence by sentence)."""
    step = yield from turn.begin("Checking every number")
    checker = stream.Checked(data, MAX_ANSWER_WORDS, words_checked=False)  # code templates write digits
    clean = [c for c in (checker.take(s) for s in stream.split(prose)) if c]
    yield from end_check(turn, step, checker.total, checker.removed)
    yield from turn.say(" ".join(clean))


# ---------- estimates ----------

def _inr(usd: float) -> float | None:
    """USD -> INR only when USD_INR is configured (no rate is guessed)."""
    rate = (os.environ.get("USD_INR") or "").strip()
    try:
        return round(usd * float(rate), 2) if rate else None
    except ValueError:
        return None


def usd_range(low: float, high: float) -> str:
    """'$0 to $0.0125' / '$0.0010 to $0.0034' (4 places: chat costs are fractions of a cent)."""
    def one(value: float) -> str:
        return "$0" if value == 0 else f"${value:.4f}"
    return one(low) if round(low, 4) == round(high, 4) else f"{one(low)} to {one(high)}"


def emit_estimate(turn: Turn, kind: str, title: str, target: str, breakdown: list[dict], seconds: tuple[int, int],
                  basis: str, summary: str):
    """The estimate card (the turn ends here); the token only when this role may confirm it.

    summary may use {cost} and {seconds}; they are filled from the estimate itself, so every number checks.
    """
    step = yield from turn.begin("Estimating the cost")
    low, high = est.total(breakdown)
    allowed, reason = tokens.can_confirm(turn.user["role"], high)
    token, expires = tokens.sign(turn.user["email"], kind, target, high, cost_low_usd=low) if allowed else ("", 0)
    payload = {"action": {"kind": kind, "title": title, "target": target}, "cost_usd_low": low, "cost_usd_high": high,
               "cost_inr_low": _inr(low), "cost_inr_high": _inr(high), "seconds_low": seconds[0],
               "seconds_high": seconds[1], "breakdown": breakdown, "basis": basis, "confirm_token": token,
               "expires_at": expires or None, "can_confirm": allowed, "blocked_reason": reason,
               "display": {"cost": usd_range(low, high), "seconds": f"{seconds[0]} to {seconds[1]} seconds"}}
    yield from turn.end(step, detail=f"{len(breakdown)} steps priced from measured history")
    turn.estimate = payload
    yield "estimate", payload
    words = summary.format(**payload["display"]) + (" Nothing runs until you confirm." if allowed else "")  # the card says why not, once
    clean, _removed = verifier.verify(words, payload)
    yield from turn.say(clean)


def estimate_process(turn: Turn, target: dict):
    """Estimate processing an event or a new link."""
    found = actions.estimate(target)
    summary = (f"Processing {target['title']} reads the filing with the cheap model: about {{cost}}, "
               "{seconds}.")
    yield from emit_estimate(turn, "process_event", target["title"], actions.target_key(target), found["breakdown"],
                             (found["seconds_low"], found["seconds_high"]), found["basis"], summary)


def estimate_deep_dive(turn: Turn, identity: dict, event_id: str, person_id: str):
    """Estimate a deep dive: the free branches run now (no spend) so the writer's prompt is sized on the real tree."""
    turn.focus_set = [memory.person_entity(event_id, person_id, identity["name"], _company(identity, event_id))]
    turn.state["last_intent"] = "deep_dive"
    tree = deep_dive.explore(identity)
    paid = deep_dive.estimate_rows(tree)
    write_row = est.chat_step("write", "Writing the lineage summary", strong_model(),
                              writer.prompt_chars("deep dive", deep_dive.compact_tree(tree)))
    # Public lookups (Bright Data): listed with their worst-case request count; they run only when confirmed.
    enrich_plan = tree.enrich_plan
    blocked = enrich_branch.over_cap(enrich_plan) if enrich_plan else None
    chosen = [] if blocked else enrich_plan
    breakdown = deep_dive.free_rows(tree, (event_id, person_id)) + paid + enrich_branch.estimate_rows(chosen) + [write_row]
    approved = ",".join(r["event_id"] for r in paid)
    enrich_flags = ",".join(c["kind"] for c in chosen)
    seconds = deep_dive.total_estimate_seconds(tree, [r["event_id"] for r in paid])
    if chosen:
        seconds = (seconds[0] + 5, seconds[1] + (cfg_enrich.MAX_POLLS * cfg_enrich.POLL_SECONDS if any(c["kind"] == "linkedin" and not c["cached"] for c in chosen) else 15))
    basis = (f"Code follows {len(tree.nodes) - 1 - len(tree.enrich_candidates) - (1 if deep_dive.home_node(tree, (event_id, person_id)) else 0)} leads for $0 (same person, family, filings), most promising first, "
             f"with a ${tree.budget:.2f} budget and caps per kind. The summary is written by {strong_model()}; "
             f"its cost is {write_row['how']}.")
    if chosen:
        basis += " " + enrich_branch.basis(chosen)
    elif blocked:
        basis += f" Public lookups are left out: {blocked}"
    leads = f" and process {len(paid)} related filing{'s' if len(paid) != 1 else ''}" if paid else ""
    public = ", and look up their public profile and web mentions" if chosen else ""
    summary = f"A deep dive on {identity['name']} follows every lead{leads}{public}: about {{cost}}, {{seconds}}."
    yield from emit_estimate(turn, "deep_dive", f"Deep dive: {identity['name']}",
                             f"{event_id}/{person_id}|{approved}|{enrich_flags}", breakdown, seconds, basis, summary)


def estimate_research(turn: Turn, question: str):
    """Estimate a multi-step question: plan + $0 lookups + a strong-model answer."""
    companies = tools.companies()
    plan_row = est.chat_step("plan", "Planning the lookups", strong_model(), planner.plan_prompt_chars(companies, question))
    tool_row = {"step": "Running the lookups (code)", "model": None, "calls": 0, "cost_usd": 0.0}
    write_row = est.chat_step("write", "Writing the answer", strong_model(),
                              writer.prompt_chars(question, "x" * writer.DATA_CHARS))
    summary = "This question needs a plan and several lookups: about {cost}, {seconds}."
    basis = f"Planner and writer: {strong_model()}; planner cost {plan_row['how']}, writer {write_row['how']}."
    yield from emit_estimate(turn, "research", question[:80], question[:600], [plan_row, tool_row, write_row], (4, 30),
                             basis, summary)


# ---------- confirmed actions ----------

def run_confirmed(turn: Turn, payload: dict):
    """Run exactly the action the token names."""
    tokens.spend(payload)
    turn.extra["estimate"] = {"cost_usd_low": payload.get("lo"), "cost_usd_high": payload["hi"]}
    yield from turn.note("Confirmed", detail=f"Approved up to ${payload['hi']:.4f}")
    kind, target = payload["k"], payload["t"]
    if kind == "process_event":
        resolved = actions.resolve(target)
        result = yield from actions.run(turn, resolved)
        for card in result["cards"]:
            yield from turn.card(card)
        yield from answer(turn, f"Processed {resolved['title']}", "process", result["data"],
                          router.Route("process_event", by="choice"))
    elif kind == "deep_dive":
        yield from run_deep_dive(turn, target, payload["hi"])
    elif kind == "research":
        yield from run_research(turn, target, payload["hi"])


def run_deep_dive(turn: Turn, target: str, approved_usd: float):
    """Follow the leads, show each branch kind as a step, then the person and lineage cards and a summary."""
    ids, _, rest = target.partition("|")
    approved, _, enrich_flags = rest.partition("|")
    event_id, _, person_id = ids.partition("/")
    identity = tools.find_person(event_id, person_id)
    if not identity:
        raise actions.TargetError("That person is no longer in the call lists.")
    step = yield from turn.begin(f"Finding {identity['name']} in {_processed_count()} events")
    tree = deep_dive.explore(identity)
    same = sum(1 for n in tree.nodes if n["kind"] == "same_person") - (1 if deep_dive.home_node(tree, (event_id, person_id)) else 0)
    unsure = " (unsure match flagged)" if identity["unsure"] else ""
    yield from turn.end(step, detail=f"{same} other {'event' if same == 1 else 'events'} with this name{unsure}")
    family = [n for n in tree.nodes if n["kind"] == "family"]
    yield from turn.note("Checking family and household", detail=f"{len(family)} household members"
                         + (": " + ", ".join(n["label"] for n in family[:3]) if family else ""))
    filings = [n for n in tree.nodes if n["kind"] == "filing"]
    yield from turn.note("Reading related filings in the discovery index", detail=f"{len(filings)} related filings")
    yield from deep_dive.run_processing(turn, tree, [x for x in approved.split(",") if x])
    yield from enrich_branch.run(turn, tree, [x for x in enrich_flags.split(",") if x])
    for reason in tree.stops:
        if not any(s["label"] == reason for s in turn.steps):
            yield from turn.note(reason, "skipped" if "budget" in reason or "cap" in reason else "done")
    person_result = tools.identity_result(identity)
    for card in person_result["cards"][:1]:
        yield from turn.card(card)
    yield from turn.card(deep_dive.lineage_card(tree, f"Where {identity['name']}'s money leads", (event_id, person_id)))
    facts = {"person": person_result["data"], "tree": deep_dive.compact_tree(tree)}
    yield from answer(turn, f"Deep dive on {identity['name']}: what money do they and their household have, and what "
                            "should the RM follow up?", "person", facts, router.Route("deep_dive", by="model"),
                      strong=True, cap=approved_usd + QUESTION_CAP_USD)


def run_research(turn: Turn, question: str, approved_usd: float):
    """Plan with the strong model, run each lookup in code, answer with the strong model."""
    step = yield from turn.begin("Planning", model=strong_model())
    try:
        steps, cost, calls, model = planner.plan(question, turn.id, tools.companies())
    except LLMError as exc:
        cost, calls = getattr(exc, "chat_cost", (0.0, 0))
        yield from turn.end(step, "failed", "The planner did not answer", cost=cost, calls=calls)
        raise actions.TargetError("The planner did not answer. Try a simpler question.")
    yield from turn.end(step, detail=f"{len(steps)} lookups: " + "; ".join(s["why"] for s in steps)[:240], cost=cost,
                        calls=calls)
    results = []
    for planned in steps:
        label = {"today": "Checking today's call list", "search_people": "Searching people",
                 "search_events": "Listing events", "calendar": "Reading the money calendar",
                 "person": f"Looking up {planned['person_name'] or 'a person'}"}[planned["tool"]]
        inner = yield from turn.begin(label)
        result = planner.run_step(planned)
        yield from turn.end(inner, detail=planned["why"][:160])
        results.append(result["data"])
        for card in result["cards"][:1]:
            yield from turn.card(card)
    yield from answer(turn, question, "research", {"lookups": results}, router.Route("research", by="model"),
                      strong=True, cap=approved_usd + QUESTION_CAP_USD)
