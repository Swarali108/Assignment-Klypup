"""Write the answer: a code template for exact lookups ($0), the fast model for simple answers, the strong model
for multi-step ones. Prose only: at most MAX_ANSWER_WORDS words, RM language; cards carry the numbers.

Whatever writes it, the verifier (api/chat/verifier.py) checks every number against the tool results before a
word is streamed. v2: the model's prose is streamed from the provider and checked sentence by sentence
(api/chat/stream.py); its prompt starts with the stable prefix (api/chat/prompts.py) so the provider caches it.
"""

from __future__ import annotations

import json

from api.chat import llm, prompts
from api.chat import windows as win
from config.chat import WRITE_MAX_TOKENS

PROMPT_VERSION = "chat-write-v2"
DATA_CHARS = 9000


def facts_json(facts: object) -> str:
    """The facts as compact JSON, cut to DATA_CHARS."""
    text = json.dumps(facts, ensure_ascii=False, separators=(",", ":"), default=str)
    return text[:DATA_CHARS]


def messages_for(question: str, facts: object, context: str = "") -> list[dict]:
    """[stable prefix, write instructions, conversation context + question + facts]."""
    user = (f"{context}\n\n" if context else "") + f"Latest message: {question[:600]}\n\nFacts (JSON): {facts_json(facts)}"
    return prompts.system_messages(prompts.WRITE) + [{"role": "user", "content": user}]


def prompt_chars(question: str, facts: object, context: str = "") -> int:
    """Size of the writer prompt, for the estimate."""
    return sum(len(m["content"]) for m in messages_for(question, facts, context)) + 30


def stream(question: str, facts: object, model: str, turn_id: str, context: str = "") -> "llm.Stream":
    """A provider stream of the prose (iterate for deltas; .cost / .calls afterwards)."""
    return llm.Stream("write", model, messages_for(question, facts, context), PROMPT_VERSION, turn_id,
                      max_tokens=WRITE_MAX_TOKENS)


# ---------- code templates ($0) ----------

def _n(count: object, one: str, many: str) -> str:
    """'1 person' / '3 people'."""
    return f"{count} {one if count == 1 else many}"


def _who(row: dict) -> str:
    role = f", {row['role']}" if row.get("role") else ""
    return f"{row['name']}{role} ({row['company']})"


def template(intent: str, data: dict) -> str:
    """Prose built by code from the tool data for one intent."""
    window = data.get("window")
    if window and data.get("in_window") == 0 and intent in ("today", "search_people", "calendar", "keyword"):
        return window_fallback(intent, data)
    if intent == "today" and window:
        top = data.get("top") or []
        first = top[0]
        verb = {"past": "came into money", "future": "are due money"}.get(window.get("tense"), "have money dates")
        if window.get("tense") == "past" and data["in_window"] == 1:
            verb = "came into money"
        elif window.get("tense") == "future" and data["in_window"] == 1:
            verb = "is due money"
        text = (f"{_n(data['in_window'], 'person', 'people')} {verb} {window['words']} ({window['span']}). "
                f"Start with {_who(first)}: {first['tier'].lower()}, {first['amount']}.")
        if len(top) > 1:
            text += f" Then {_who(top[1])}, {top[1]['amount']}."
        return text + " The list below is in call order."
    if intent == "today":
        top = data.get("top") or []
        if not top:
            return "Nobody is waiting for a call right now. Process a new filing to fill the list."
        first = top[0]
        text = (f"{_n(data['people_to_call'], 'person is', 'people are')} waiting for a call across "
                f"{_n(data['events_processed'], 'processed event', 'processed events')}. Start with {_who(first)}: {first['tier'].lower()}, {first['amount']}.")
        if len(top) > 1:
            text += f" Then {_who(top[1])}, {top[1]['amount']}."
        return text + " The full queue is below, best call first."
    if intent == "search_people":
        rows, read_as = data.get("people") or [], ", ".join(data.get("read_as") or [])
        if not rows:
            return f"No one matches {read_as or 'that'} yet. Try a lower amount or another event type."
        first = rows[0]
        return (f"{_n(data['count'], 'person matches', 'people match')} ({read_as}). The strongest is {_who(first)} with {first['amount']}"
                f"{' (an estimate)' if first.get('estimate') else ''}. The list below is in call order.")
    if intent == "keyword":
        rows = data.get("people") or []
        if not rows:
            return ("I could not match that to a person, company or role. Try a full name, a company, or "
                    "\"cash in hand above\" an amount.")
        return f"{_n(data['count'], 'person matches', 'people match')} your words. Closest: {_who(rows[0])}, {rows[0]['amount']}."
    if intent == "search_events":
        rows = data.get("events") or []
        if not rows:
            return "No events of that kind are in the app yet."
        ready = [r for r in rows if r["status"] == "ready"]
        return (f"{_n(data['count'], 'event', 'events')} found, {data['ready_count']} with a call list ready. "
                + (f"The largest is {ready[0]['company']} ({ready[0]['type']}) with {_n(ready[0]['people'], 'person', 'people')} to call."
                   if ready else "None has a call list yet."))
    if intent == "calendar":
        rows = data.get("items") or []
        if not rows:
            return "No money dates fall in that window."
        first = rows[0]
        return (f"{_n(data['count'], 'money date', 'money dates')} in this window. Next up: {first['what'].lower()} "
                f"for {first['company']} on {first['date']}, {_n(first['people'], 'person', 'people')}.")
    if intent == "person":
        apps = data.get("appearances") or []
        if not apps:
            return "I could not find that name in any processed event."
        first = apps[0]
        text = (f"{data['name']} appears in {_n(data['count'], 'processed event', 'processed events')}. In {first['company']} ({first['event']}) they are "
                f"{first['role'] or 'a holder'}: {first['tier'].lower()}, {first['amount']}. "
                f"{first['timing'] or ''}".rstrip() + ".")
        if len(apps) > 1:
            text += " Also: " + "; ".join(f"{a['company']}, {a['amount']}" for a in apps[1:4]) + "."
        if data.get("unsure"):
            text += f" Unsure match: {data['unsure_reason']}."
        return text.replace("..", ".")
    if intent == "person_lock_in":
        return person_lock_in(data)
    if intent == "person_elsewhere":
        return person_elsewhere(data)
    if intent == "person_question":
        return (f"I can only show what is stored for {data['name']} here, not write an answer to that; the card "
                "below has the details. " + template("person", data))
    if intent == "process":
        top = data.get("top") or []
        text = f"{data.get('event')} ({data.get('type')}) is processed: {_n(data.get('people_to_call', 0), 'person', 'people')} to call."
        if top:
            text += f" Start with {_who(top[0])}, {top[0]['amount']}."
        return text
    if intent == "research":
        return "Here is what each lookup found; the cards below carry the details."
    if intent == "script":
        if data.get("reused"):
            return (f"Here is the {data['what']} for {_who(data)} again, only about them. It is the one written "
                    "earlier in this conversation, so nothing new was spent.")
        article = "an" if data["what"][:1].lower() in "aeiou" else "a"
        tail = ("the spoken lines do not read the amount out" if data["what"] == "call script"
                else "the message itself does not mention the amount")
        return (f"Here is {article} {data['what']} for {_who(data)}. Every number in it comes from the call card, filled "
                f"in by code; {tail}.")
    if intent == "help":
        return ("Ask me who came into money, what one person has, people above an amount, upcoming money dates, or "
                "paste a filing link to process it. Anything that costs money shows its cost first and waits for you.")
    return ""


def person_lock_in(data: dict) -> str:
    """When one person's kept shares are free, from the stored lock-in text of each event (tools.lock_in)."""
    name, rows = data["name"], data.get("lock_in") or []
    if not rows:
        return f"{name}'s call card has no lock-in on record. The card below has their money and timing."
    parts = []
    for row in rows[:2]:
        where = f"{row['company']} ({row['event']})"
        if row["status"] == "unknown":
            parts.append(f"For {where}, when {name}'s kept shares are free is not confirmed: {row['display']}.")
            continue
        kept = f"{name} keeps {row['shares']} in {where}" if row.get("shares") else f"{name}'s kept shares in {where}"
        value = f", {row['value']}" if row.get("shares") and row.get("value") else ""
        parts.append(f"{kept}{value}. When they are free: {row['display']}."
                     + (f" {row['note']}" if row.get("note") else ""))
    return " ".join(parts).replace("..", ".")


def person_elsewhere(data: dict) -> str:
    """Every processed event one person appears in, with the money in each."""
    name, apps = data["name"], data.get("appearances") or []
    if not apps:
        return "I could not find that name in any processed event."
    rows = [f"{a['company']} ({a['event']}), {a['tier'].lower()}, {a['amount']}" for a in apps[:5]]
    if len(apps) == 1:
        text = f"{name} appears in only 1 processed event: {rows[0]}. No other processed event has this name."
    else:
        more = "; and more on the cards" if len(apps) > 5 else ""
        text = f"{name} appears in {_n(data['count'], 'processed event', 'processed events')}: " + "; ".join(rows) + more + "."
    if data.get("unsure"):
        text += f" Unsure match: {data['unsure_reason']}."
    return text


def window_fallback(intent: str, data: dict) -> str:
    """'No one came into money this week (9 Nov to 15 Nov 2026). The nearest were 12 to 25 days ago ...'."""
    window = data["window"]
    nobody = {"past": "No one came into money", "future": "No one is due money"}.get(window.get("tense"),
                                                                                  "No one has a money date")
    what = {"calendar": "No money dates fall", "today": nobody}.get(intent, "No one matches")
    lead = f"{what} {window['words']} ({window['span']})." if intent != "search_people" else \
        f"No one matches that {window['words']} ({window['span']})."
    phrase = win.days_phrase(data)
    if not data.get("nearest_count"):
        return lead + " Nothing has a known date close to it either."
    rows = data.get("nearest") or []
    first = rows[0] if rows else None
    text = lead + f" The nearest {'is' if data['nearest_count'] == 1 else 'are'} {phrase}, outside this window"
    if first and first.get("name"):
        text += f"; the most recent is {_who(first)}, {first['amount']}, money date {first['money_date']}"
    elif first and first.get("what"):
        text += f"; the first is {first['what'].lower()} for {first['company']} on {first['date']}"
    return text + ". They are below, each with its own date."
