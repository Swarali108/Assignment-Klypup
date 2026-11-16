"""Understand a question: code rules first (exact lookups cost $0 and use no model), then the fast model.

Intents: today, search_people, search_events, calendar, person (reverse lookup), process_event, deep_dive,
call_script, draft_message, research (multi-step), help. v2: the model sees the conversation state (after the
stable prefix, api/chat/prompts.py) and says when a message is about the focus; who "him" is, is decided in code
(api/chat/memory.py). The model only classifies and copies entities out of the question; a number it
returns is kept only when that number is in the question, and a name only when it is in the question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from api import ask as ask_mod
from api.chat import llm, prompts, tools, verifier
from api.chat import windows as win
from api.chat.actions import URL
from api.chat.script import channel_of
from config.chat import fast_model

PROMPT_VERSION = "chat-route-v2"


@dataclass
class Route:
    """What the agent will do, and who decided (rules | model | choice | fallback)."""

    intent: str
    args: dict = field(default_factory=dict)
    by: str = "rules"
    cost: float = 0.0
    calls: int = 0
    model: str | None = None
    note: str | None = None


# ---------- rules ----------

_DEEP = re.compile(r"\b(?:deep[\s-]?dive|dig (?:into|deeper)|trace|follow (?:the )?(?:money|leads?)|investigate)\b"
                   r"(?:\s+(?:on|into|for|about|of|the money of))?\s*(?P<name>.*)$", re.I)
_PERSON = (
    re.compile(r"\bwhat (?:money|cash|wealth|shares) (?:does|did|has) (?P<name>.+?) (?:have|got|get|make|hold|own)\b", re.I),
    re.compile(r"\bhow much (?:money |cash )?(?:does|did|has) (?P<name>.+?) (?:have|got|get|make|made|hold)\b", re.I),
    re.compile(r"\b(?:who is|tell me about|look up|lookup|money of|anything on) (?P<name>.+)$", re.I),
)
# A "name" that only points at someone; the conversation's focus says who (api/chat/memory.py).
_PRONOUN_NAME = re.compile(r"(?:he|she|him|her|they|them|this person|that person|the client|this client)", re.I)
_PROCESS = re.compile(r"\b(?:process|run|re-?run|refresh|add)\b", re.I)
_RESEARCH = re.compile(r"\b(?:compare|versus|vs\.?|and then|step by step|across all|which of .+ and)\b", re.I)
_TODAY = re.compile(r"\b(?:came into money|come into money|who should i call|call list|top calls?|briefing|"
                    r"who to call|today'?s calls?|new money)\b", re.I)
_CALENDAR = re.compile(r"\b(?:calendar|lock-?ins?|unlocks?|upcoming|listing dates?|due (?:this|next)|"
                       r"(?:next|this) (?:week|month)'?s? (?:dates|payments))\b", re.I)
_EVENTS = re.compile(r"\b(?:events?|filings?|ipos|buybacks|offers? for sale)\b", re.I)
_PEOPLE_WORDS = re.compile(r"\b(?:who|people|persons?|promoters?|directors?|investors?|sellers?|holders?|founders?|cash)\b", re.I)
_HELP = re.compile(r"^\s*(?:hi|hello|hey|help|what can you do)\b", re.I)
_SCRIPT = re.compile(r"\b(?:script|talking points|call prep|prep(?:are)? (?:me )?for (?:the|my|a|this) call|"
                     r"ready me for|what (?:should|do) i say|how (?:should|do) i (?:open|pitch|start)|pitch)\b", re.I)
_DRAFT = re.compile(r"\b(?:draft|write|compose|prepare|send)\b.{0,40}?\b(?:whats\s?app|e-?mail|mail|message|text|"
                    r"note|sms)\b|^\s*(?:e-?mail|whats\s?app|message|text|sms)\b", re.I)
# Words around a name in a script request ("a script for the call with <name>"), dropped to find the name.
_FILLER = re.compile(r"\b(?:ready|make|me|a|an|the|call|calls|script|scripts|talking|points|prep|prepare|draft|write|"
                     r"compose|send|for|with|to|on|about|whats\s?app|e-?mail|mail|message|text|note|sms|please|my|"
                     r"this|that|him|her|them|client|person|only|its|it's|it|is|i|mean|meant|regarding|just|again|"
                     r"same|one|quick|short|of|what|should|do|say|how|open|pitch|start|up|can|you|need|want|new|"
                     r"shorter|longer|another|different|version|brief|briefer|formal|casual|warmer|simpler|"
                     r"again|redo|rewrite|make|less|more|it|when|keep|tomorrow|tomorrows|today|tonight|yesterday|meeting|meetings|"
                     r"points|point|ideas|idea|give|get|have|and|or|in|at|by|from|before|after|next|then|now|s|"
                     r"will|would|could|talk|talking|speak|ring|phone|calling|called|let|lets|go|going|ask|asking|"
                     r"questions|question|objections|objection|opening|opener|intro|agenda|notes|tips|help|"
                     r"something|anything|some|any|good|best|better|easy|simple|friendly|polite|tone|words|line|lines)\b", re.I)


def leftover_name(text: str) -> str:
    """What is left of a message once the request words are dropped: a name, or ''."""
    rest = _FILLER.sub(" ", re.sub(r"[?.!,'\"“”]", " ", text or ""))
    return clean_name(" ".join(rest.split()))


def clean_name(text: str) -> str:
    """A name typed in a question, without the question's own words."""
    text = re.sub(r"[?.!]+$", "", (text or "").strip())
    text = re.sub(r"^(?:mr|mrs|ms|dr|shri|smt)\.?\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(?:have|has|got|now|today|in total|please)$", "", text, flags=re.I)
    return text.strip(" '\"")


def _holder_with_role(filters: dict, question: str) -> str | None:
    """The holder a role word belongs to ("Trust" in "<X Family Trust>"), when the question names one; else None."""
    word = filters.get("role_contains")
    return tools.holder_named(question, word) if word else None


def rules(question: str) -> Route | None:
    """The intent from word rules alone, or None when the rules cannot tell."""
    q = (question or "").strip()
    if not q:
        return None
    if _HELP.match(q):
        return Route("help")
    link = URL.search(q)
    if link:
        return Route("process_event", {"target": link.group(0).rstrip(".,")})
    deep = _DEEP.search(q)
    if deep:
        return Route("deep_dive", {"name": clean_name(deep.group("name"))})
    if _DRAFT.search(q):
        return Route("draft_message", {"name": leftover_name(q), "channel": channel_of(q)})
    if _SCRIPT.search(q):
        return Route("call_script", {"name": leftover_name(q), "channel": "call"})
    if _PROCESS.search(q) and re.search(r"\b(?:ipo|buyback|event|filing|offer|link)\b", q, re.I):
        found = tools.events_by_word(q)
        return Route("process_event", {"target": found[0]["spec"].event_id} if len(found) == 1 else {})
    if _RESEARCH.search(q):
        return Route("research", {"question": q})
    for index, pattern in enumerate(_PERSON):
        match = pattern.search(q)
        if match:
            name = clean_name(match.group("name"))
            if _PRONOUN_NAME.fullmatch(name):
                return Route("person", {})  # "what money does she have?": whoever the conversation is about

            # "who is worth ringing" is not a name: the loose pattern counts only when someone matches it.
            if index < 2 or tools.reverse_lookup(name)["data"]["match"] != "none":
                return Route("person", {"name": name})
    if _CALENDAR.search(q):
        start, end = tools.date_window(q)
        return Route("calendar", {"start": start, "end": end, "window": win.parse(q)})
    if _TODAY.search(q):
        return Route("today")
    filters = ask_mod.safe_filters(ask_mod.rule_filters(q, tools.companies()), q)
    holder = _holder_with_role(filters, q)
    if holder:
        # A question about one holder, answered from their facts (by the model when the role may spend).
        return Route("person", {"name": holder, "ask": "question"})
    if filters and (_PEOPLE_WORDS.search(q) or "min_cr" in filters or "max_cr" in filters or "tier" in filters):
        return Route("search_people", {"filters": filters})
    if _EVENTS.search(q) and not _PEOPLE_WORDS.search(q):
        return Route("search_events", {"event_type": filters.get("event_type"), "company": filters.get("company")})
    if filters:
        return Route("search_people", {"filters": filters})
    # A bare name: when the whole question is a known person's name, look them up.
    if len(q.split()) <= 5 and tools.reverse_lookup(clean_name(q))["data"]["match"] == "exact":
        return Route("person", {"name": clean_name(q)})
    return None


# ---------- model ----------

class RouteEntities(BaseModel):
    """Entities copied from the question (null when absent)."""

    model_config = ConfigDict(extra="forbid")
    person_name: str | None
    company: str | None
    event_type: Literal["ipo", "buyback", "ofs_stock_exchange"] | None
    tier: Literal["cash_now", "unlock", "holding"] | None
    role_contains: str | None
    min_cr: float | None
    max_cr: float | None
    link: str | None


class RouteAnswer(BaseModel):
    """The fast model's reading of one question."""

    model_config = ConfigDict(extra="forbid")
    intent: Literal["today", "search_people", "search_events", "calendar", "person", "process_event", "deep_dive",
                    "call_script", "draft_message", "research", "help", "unclear"]
    multi_step: bool
    about_focus: bool
    channel: Literal["whatsapp", "email"] | None
    entities: RouteEntities
    clarify_question: str | None


SYSTEM = prompts.ROUTE  # after prompts.STABLE_PREFIX


def model_route(question: str, turn_id: str, context: str = "", known_names: tuple[str, ...] = ()) -> Route:
    """The fast model's route, with numbers and names it did not copy from the question removed.

    context is the conversation state and last turns (it follows the stable prefix). A name is kept when it is
    in the question or is one of known_names (the focus); anything else the model names is dropped.
    """
    model = fast_model()
    user = (f"{context}\n\n" if context else "") + f"Latest message: {question[:600]}"
    messages = prompts.system_messages(SYSTEM) + [{"role": "user", "content": user}]
    parsed, cost, calls = llm.call("route", model, messages, RouteAnswer, PROMPT_VERSION, turn_id)
    answer = RouteAnswer.model_validate(parsed)
    ent = answer.entities
    route = Route(answer.intent, by="model", cost=cost, calls=calls, model=model)
    known = {n.lower() for n in known_names if n}
    name = ent.person_name if ent.person_name and (ent.person_name.lower() in question.lower()
                                                   or ent.person_name.lower() in known) else None
    route.args["about_focus"] = bool(answer.about_focus)
    raw_filters = {"event_type": ent.event_type, "tier": ent.tier, "role_contains": ent.role_contains,
                   "min_cr": ent.min_cr, "max_cr": ent.max_cr,
                   "company": ent.company if ent.company and ent.company.lower() in question.lower() else None}
    filters = ask_mod.safe_filters(raw_filters, question)
    if _holder_with_role(filters, question):
        filters.pop("role_contains")  # the role word is part of a holder's name, not a filter
    if answer.multi_step or answer.intent == "research":
        route.intent, route.args = "research", {"question": question}
    elif answer.intent in ("person", "deep_dive"):
        route.args = {"name": clean_name(name or ""), "about_focus": bool(answer.about_focus)}
    elif answer.intent in ("call_script", "draft_message"):
        channel = (answer.channel or channel_of(question)) if answer.intent == "draft_message" else "call"
        route.args = {"name": clean_name(name or ""), "about_focus": bool(answer.about_focus),
                      "channel": "whatsapp" if channel == "call" and answer.intent == "draft_message" else channel}
    elif answer.intent == "process_event":
        link = URL.search(question)
        found = tools.events_by_word(question)
        route.args = {"target": link.group(0)} if link else ({"target": found[0]["spec"].event_id} if len(found) == 1 else {})
    elif answer.intent == "search_people":
        route.args = {"filters": filters}
    elif answer.intent == "search_events":
        route.args = {"event_type": filters.get("event_type"), "company": filters.get("company")}
    elif answer.intent == "calendar":
        start, end = tools.date_window(question)
        route.args = {"start": start, "end": end, "window": win.parse(question)}
    elif answer.intent == "unclear":
        # Shown on screen: any digit not in the question is removed (the model has not seen the data).
        route.note = verifier.verify(answer.clarify_question, question)[0] if answer.clarify_question else None
    return route
