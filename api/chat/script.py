"""Call scripts and message drafts for one person (api/CHAT_CONTRACT.md v2, cards kind "script").

The strong model writes the words with {placeholders}; it is told never to type a digit, and any digit it types
anyway is removed before filling. Code then fills each placeholder from the person's call card (a whitelist;
the model's text is never passed to str.format). So every number in a script comes from stored data. When the
role may not spend, or the model fails, a code template with the same placeholders writes the script ($0).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from api import views
from api.chat import llm, prompts, tools, verifier

PROMPT_VERSION = "chat-script-v2"
CHANNELS = ("call", "whatsapp", "email")
_PLACEHOLDER = re.compile(r"\{\s*([a-z_]+)\s*\}")
_TITLES = re.compile(r"^(?:dr|mr|mrs|ms|prof|shri|smt)\.?$", re.I)


class Objection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objection: str
    answer: str


class ScriptDraft(BaseModel):
    """What the model writes (placeholders, no digits)."""

    model_config = ConfigDict(extra="forbid")
    opening: list[str]
    why_now: list[str]
    questions: list[str]
    objections: list[Objection]
    message: list[str]
    next_step: list[str]


# ---------- the facts a script may use ----------

def first_name(name: str) -> str:
    """The first given name as an RM would say it: 'Dr. Asha' stays, an ALL-CAPS name is title-cased."""
    parts = (name or "").split()
    if not parts:
        return ""
    pick = parts[:2] if _TITLES.match(parts[0]) and len(parts) > 1 else parts[:1]
    text = " ".join(pick)
    return text.title() if text.isupper() else text


def values(card: dict, rm_name: str = "") -> dict[str, str]:
    """Placeholder -> text, every value straight from the call card (api/views.person_card); rm_name is the
    signed-in user's name."""
    person, event, timing = card.get("person") or {}, card.get("event") or {}, card.get("timing") or {}
    date_iso = timing.get("date_iso")
    return {"name": person.get("name") or "", "first_name": first_name(person.get("name") or ""),
            "rm_name": rm_name or "your relationship manager",
            "role": person.get("role") or "holder", "company": event.get("company") or "",
            "event": event.get("type_label") or "", "tier": card.get("tier_label") or "",
            "amount": (card.get("amount") or {}).get("display") or "an amount not yet known",
            "money_date": views.nice_date(date_iso) if date_iso else "a date not yet confirmed",
            "timing": timing.get("label") or "", "why_now": card.get("why_now") or card.get("why") or "",
            "confidence": (card.get("confidence") or {}).get("level") or "unknown"}


def model_facts(card: dict) -> dict:
    """What the model sees about the person (it writes words, code writes numbers)."""
    return {**tools.compact(card), "brief": (card.get("brief") or {}).get("lines") or [],
            "why_now": card.get("why_now"), "unsure": bool((card.get("match") or {}).get("unsure"))}


def fill(line: str, vals: dict[str, str]) -> tuple[str, list[str]]:
    """(the line with digits the model typed removed and placeholders filled, digits removed)."""
    cleaned, removed = verifier.verify(line or "", {})  # no digit may come from the model

    def value(match: re.Match) -> str:
        text = vals.get(match.group(1), "")
        before = cleaned[:match.start()].rstrip()
        if match.group(1) == "tier" and before and before[-1] not in ".!?:":
            return text.lower()  # "the filing shows cash in hand", "Cash in hand: ..." at a start
        return text

    filled = _PLACEHOLDER.sub(value, cleaned)
    filled = re.sub(r"[{}]", "", filled)
    filled = re.sub(r"\s{2,}", " ", filled).replace(" .", ".").replace(" ,", ",").strip()
    return filled, removed


_FILLER = frozenset("a an the is are was were be been being has have had do does did so that this it its of to in on at for "
                    "and or but with as by from".split())
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_RESTATED = 0.6


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _FILLER}


def drop_restated(lines: list[str]) -> list[str]:
    """Lines with sentences removed that only restate an earlier sentence of the same section: at least 60% of
    their content words were already said (the card's timing label already carries "listing notice not yet seen",
    and the model repeats it in its own words). The first time a fact is said is always kept."""
    seen: set[str] = set()
    out = []
    for line in lines:
        kept = []
        for sentence in _SENTENCE.split(line):
            words = _content_words(sentence)
            if words and len(words & seen) / len(words) >= _RESTATED:
                continue
            seen |= words
            kept.append(sentence)
        if kept:
            out.append(" ".join(kept))
    return out


# ---------- templates ($0) ----------

def template_draft(channel: str) -> ScriptDraft:
    """A plain script from code, with the same placeholders the model uses."""
    if channel == "whatsapp":
        return ScriptDraft(opening=["Hello {first_name},"], why_now=[], questions=[], objections=[], message=[
            "Congratulations on the {company} {event}; it is a big milestone.",
            "When the dust settles, I would value a short conversation about your plans from here.",
            "Would a quick call later this week suit you?"],
            next_step=["If there is no reply in two days, follow up with a call."])
    if channel == "email":
        return ScriptDraft(opening=["Congratulations on the {company} {event}"], why_now=[], questions=[], objections=[],
                           message=["Dear {first_name},", "Congratulations on the {company} {event}.",
                                    "Events like this often bring new decisions for the family and the business.",
                                    "I would welcome a short conversation, at your convenience, to understand your plans.",
                                    "Warm regards,"],
                           next_step=["Log the email and set a follow-up for later this week."])
    return ScriptDraft(
        opening=["Hello {first_name}, this is {rm_name}; thank you for taking my call.",
                 "I am calling to congratulate you on the {company} {event} and to understand your plans from here."],
        why_now=["{tier}: {amount}. {timing}.", "{why_now}", "Confidence in these facts: {confidence}."],
        questions=["How are you thinking about the proceeds from the {company} {event}?",
                   "Are there family or business plans this money should support over the next year?",
                   "How do you look after your investments today, and what would you change?"],
        objections=[Objection(objection="I already have an advisor.",
                              answer="That makes sense; I would only offer a second view on what has changed since the "
                                     "{event}, with no obligation."),
                    Objection(objection="It is too early to decide anything.",
                              answer="Agreed; today is only about understanding your plans, nothing to decide.")],
        message=[], next_step=["Offer a short meeting this week and send a one-page summary after the call."])


# ---------- building the card ----------

def sections(draft: ScriptDraft, channel: str, vals: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Contract sections [{heading, lines}] filled by code, and every digit removed from the model's text."""
    removed: list[str] = []

    def lines(raw: list[str]) -> list[str]:
        out = []
        for line in raw:
            text, gone = fill(line, vals)
            removed.extend(gone)
            if text:
                out.append(text)
        return out

    if channel == "call":
        objections = []
        for item in draft.objections[:3]:
            said, gone_a = fill(item.objection, vals)
            reply, gone_b = fill(item.answer, vals)
            removed.extend(gone_a + gone_b)
            if said and reply:
                said = said.strip('“”"')
                objections.append(f"“{said}” → {reply}")
        found = [{"heading": "Opening", "lines": lines(draft.opening)[:3]},
                 {"heading": "Why now (for you, not to read out)", "lines": drop_restated(lines(draft.why_now))[:4]},
                 {"heading": "Three questions", "lines": lines(draft.questions)[:3]},
                 {"heading": "Likely objections", "lines": objections},
                 {"heading": "Next step", "lines": lines(draft.next_step)[:2]}]
    else:
        head = "Subject" if channel == "email" else "Greeting"
        body = "Email" if channel == "email" else "WhatsApp message"
        found = [{"heading": head, "lines": lines(draft.opening)[:1]},
                 {"heading": body, "lines": lines(draft.message)[:6]},
                 {"heading": "After sending", "lines": lines(draft.next_step)[:1]}]
    return [s for s in found if s["lines"]], removed


def title_for(channel: str, name: str) -> str:
    return {"call": "Call script", "whatsapp": "WhatsApp draft", "email": "Email draft"}[channel] + f": {name}"


def card_for(card: dict, draft: ScriptDraft, channel: str, written_by: str, rm_name: str = "") -> tuple[dict, list[str]]:
    """The script card and the digits removed from the model's words."""
    vals = values(card, rm_name)
    found, removed = sections(draft, channel, vals)
    person, event = card.get("person") or {}, card.get("event") or {}
    return ({"kind": "script", "title": title_for(channel, vals["name"]), "channel": channel, "written_by": written_by,
             "person": {"event_id": event.get("id"), "person_id": person.get("id"), "name": vals["name"]},
             "sections": found, "items": [], "draft": draft.model_dump(),  # words + placeholders, no digits
             "facts": {"amount": vals["amount"], "timing": vals["timing"], "company": vals["company"],
                       "event": vals["event"], "confidence": vals["confidence"]}}, removed)


def write(card: dict, channel: str, request: str, context: str, model: str, turn_id: str) -> tuple[ScriptDraft, float, int]:
    """(draft, cost, calls) from the strong model."""
    import json

    user = (f"{context}\n\n" if context else "") + (
        f"Channel: {channel}\nRM's request: {request[:400]}\n\n"
        f"Call card facts (JSON): {json.dumps(model_facts(card), ensure_ascii=False, default=str)[:5000]}")
    messages = prompts.system_messages(prompts.SCRIPT) + [{"role": "user", "content": user}]
    parsed, cost, calls = llm.call("script", model, messages, ScriptDraft, PROMPT_VERSION, turn_id)
    return ScriptDraft.model_validate(parsed), cost, calls


def prompt_chars(card: dict, request: str, context: str) -> int:
    """Size of the script prompt, for the spend check."""
    import json

    return (len(prompts.STABLE_PREFIX) + len(prompts.SCRIPT) + len(context) + len(request[:400])
            + len(json.dumps(model_facts(card), ensure_ascii=False, default=str)[:5000]) + 80)


def channel_of(text: str) -> str:
    """'call' unless the request asks for a WhatsApp / text message or an email."""
    lowered = (text or "").lower()
    if re.search(r"\b(?:e-?mail|mail)\b", lowered):
        return "email"
    if re.search(r"\b(?:whats\s?app|wa message|text message|sms|message)\b", lowered):
        return "whatsapp"
    return "call"
