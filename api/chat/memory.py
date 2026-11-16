"""Conversation memory: rolling summary + focus entities + the last K turns, stored with the conversation.

State (JSON in chat_conversations.state):
  summary, summary_entities, open_questions   older turns folded in by compress() (no unverified digit)
  compressed_through                          how many stored messages the summary covers
  focus      [entity]  who/what the conversation is about now (from tool results, clicks, confirmed actions)
  recent     [entity]  earlier focus, kept for name matching ("its about <first name>")
  candidates [entity]  the people in the last list shown (for "the second one" and for clarify options)
  pending    {intent, channel} | None   what a clarify was asked for, so the reply completes it
  last_intent                           the last person-scoped intent answered (call_script, person, ...)
  compressions [{...}]                  one record per compression
An entity is {kind: "person"|"event", event_id, person_id|None, label, company}.

Reference resolution is code: message words against entity names, ordinals against the last list, pronouns
against the focus. The model is never asked who "him" is.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from api import db
from api.chat import verifier
from config.chat import (CANDIDATES_MAX, FOCUS_MAX, HISTORY_COMPRESS_TOKENS, KEEP_TURNS, RECENT_MAX, SUMMARY_CHARS,
                         TURN_CHARS)

CHARS_PER_TOKEN = 4
PROMPT_VERSION = "chat-compress-v1"

_PRONOUN = re.compile(r"\b(?:him|her|his|hers|them|they|their|he|she|this person|that person|the person|"
                      r"same person|this one|that one|the client|this client|the call|this call|for the call|"
                      r"about (?:them|him|her)|the same)\b", re.I)
_ORDINALS = {"first": 0, "1st": 0, "top": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3,
             "fifth": 4, "5th": 4}
_ORDINAL = re.compile(r"\b(?:the )?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|top) (?:one|person|name|"
                      r"guy|lady|seller|promoter|holder)\b|\b(?:number|no\.?|#)\s?([1-5])\b", re.I)
# Words that never identify a person, even when a name happens to contain them.
_STOP = {"the", "and", "for", "about", "only", "its", "it's", "this", "that", "with", "from", "call", "script",
         "ready", "make", "write", "draft", "email", "mail", "whatsapp", "message", "what", "who", "how", "much",
         "money", "does", "have", "has", "please", "need", "want", "give", "show", "tell", "more", "his", "her",
         "him", "them", "their", "limited", "ltd", "india", "private", "pvt", "company", "shareholder", "promoter",
         "selling", "family", "trust", "kumar", "singh", "devi", "bhai", "ben", "shah", "one", "person", "same",
         "again", "also", "just", "can", "you", "me", "my", "our", "your", "a", "an", "to", "of", "in", "on", "is"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty() -> dict:
    """A new conversation's state."""
    return {"v": 2, "summary": "", "summary_entities": [], "open_questions": [], "compressed_through": 0,
            "focus": [], "recent": [], "candidates": [], "pending": None, "last_intent": None, "compressions": []}


# ---------- storage ----------

def load(conversation_id: str) -> dict:
    """The stored state (a fresh one when none is stored yet)."""
    with db.connect() as conn:
        rows = conn.query("SELECT state FROM chat_conversations WHERE id = %s", (conversation_id,))
    try:
        stored = json.loads((rows[0].get("state") if rows else None) or "{}")
    except (TypeError, ValueError):
        stored = {}
    return {**empty(), **(stored if isinstance(stored, dict) else {})}


def save(conversation_id: str, state: dict) -> None:
    """Store the state."""
    with db.connect() as conn:
        conn.execute("UPDATE chat_conversations SET state = %s WHERE id = %s",
                     (json.dumps(state, ensure_ascii=False, default=str), conversation_id))


# ---------- entities ----------

def person_entity(event_id: str, person_id: str, label: str, company: str | None = None) -> dict:
    return {"kind": "person", "event_id": event_id, "person_id": person_id, "label": label or "", "company": company}


def event_entity(event_id: str, label: str) -> dict:
    return {"kind": "event", "event_id": event_id, "person_id": None, "label": label or "", "company": label}


def from_item(item: dict) -> dict | None:
    """A person entity from a call item or call card (api/CONTRACT.md view model)."""
    person, event = item.get("person") or {}, item.get("event") or {}
    if not person.get("id") or not event.get("id"):
        return None
    return person_entity(event["id"], person["id"], person.get("name") or "", event.get("company"))


def key(entity: dict) -> tuple:
    return entity.get("kind"), entity.get("event_id"), entity.get("person_id")


def public(entities: list[dict]) -> list[dict]:
    """The focus as the contract shows it: [{kind, event_id, person_id, label}]."""
    return [{"kind": e["kind"], "event_id": e["event_id"], "person_id": e.get("person_id"), "label": e["label"]}
            for e in entities]


def set_focus(state: dict, entities: list[dict]) -> bool:
    """Make these the focus (older focus moves to recent). True when the focus changed."""
    entities = [e for e in entities if e][:FOCUS_MAX]
    if not entities or [key(e) for e in entities] == [key(e) for e in state["focus"]]:
        return False
    keep = {key(e) for e in entities}
    recent = [e for e in state["focus"] + state["recent"] if key(e) not in keep]
    seen, unique = set(), []
    for entity in recent:
        if key(entity) not in seen:
            seen.add(key(entity))
            unique.append(entity)
    state["focus"], state["recent"] = entities, unique[:RECENT_MAX]
    return True


def learn_from_cards(state: dict, cards: list[dict]) -> bool:
    """Update focus / candidates from the cards a turn showed. True when the focus changed.

    A person card or a script card focuses that person; a list of people becomes the candidates (the focus
    stays, so "the call" after a list still means the person we were talking about, if any).
    """
    focused: list[dict] = []
    for card in cards:
        items = card.get("items") or []
        if card.get("kind") == "person" and items:
            focused.append(from_item(items[0]))
        elif card.get("kind") == "script" and card.get("person"):
            who = card["person"]
            focused.append(person_entity(who["event_id"], who["person_id"], who.get("name") or ""))
        elif card.get("kind") == "people" and items:
            found = [from_item(item) for item in items[:CANDIDATES_MAX]]
            state["candidates"] = [e for e in found if e]
    focused = [e for e in focused if e]
    return set_focus(state, focused[:1]) if focused else False


# ---------- reference resolution ----------

def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) >= 3 and w not in _STOP}


def _pool(state: dict) -> list[dict]:
    """Focus first, then the last list, then earlier entities; each once."""
    seen, out = set(), []
    for entity in state["focus"] + state["candidates"] + state["recent"]:
        if key(entity) not in seen:
            seen.add(key(entity))
            out.append(entity)
    return out


def _name_tokens(label: str) -> list[str]:
    """A label's distinctive name words in order (given name first)."""
    out = []
    for word in re.findall(r"[a-z]+", (label or "").lower()):
        if len(word) >= 3 and word not in _STOP and word not in out:
            out.append(word)
    return out


def name_matches(message: str, state: dict) -> list[dict]:
    """Remembered entities the message names, best coverage first ("its about kusum").

    A name counts when the message holds the entity's given (first) name or two or more of its name words;
    one shared surname token alone is not a match. Only the entities that explain the most message words are
    returned, so "what about harish?" never binds to a wife who merely shares the surname.
    """
    words = _words(message)
    if not words:
        return []
    scored = []
    for entity in _pool(state):
        tokens = _name_tokens(entity.get("label") or "")
        covered = [t for t in tokens if t in words]
        if covered and (tokens[0] in words or len(covered) >= 2 or len(tokens) == 1):
            scored.append((len(covered) + (0.5 if tokens[0] in words else 0), entity))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [entity for score, entity in scored if score == best]


_TOP_OF_LIST = re.compile(r"\b(?:whoever|who|the one|the person|the name)\s+(?:is\s+)?(?:tops?|heads?|leads?|"
                          r"(?:is\s+)?(?:at the top|first) (?:of|on|in))\s+(?:that|the|this)\s+list\b|"
                          r"\b(?:top|first) (?:of|on) (?:that|the|this) list\b|\bnumber one\b", re.I)


def ordinal(message: str, state: dict) -> dict | None:
    """'the second one' / 'number 2' / 'whoever tops that list' -> that row of the last list shown."""
    if state["candidates"] and _TOP_OF_LIST.search(message or ""):
        return state["candidates"][0]
    match = _ORDINAL.search(message or "")
    if not match or not state["candidates"]:
        return None
    index = _ORDINALS[match.group(1).lower()] if match.group(1) else int(match.group(2)) - 1
    return state["candidates"][index] if index < len(state["candidates"]) else None


def has_pronoun(message: str) -> bool:
    """True when the message points at someone without naming them."""
    return bool(_PRONOUN.search(message or ""))


def resolve(message: str, state: dict) -> dict:
    """{entities: [...], how: "name"|"ordinal"|"focus"|"none", pronoun: bool} for one message."""
    picked = ordinal(message, state)
    if picked:
        return {"entities": [picked], "how": "ordinal", "pronoun": True}
    named = name_matches(message, state)
    if named:
        # Equal coverage: keep the ones in the focus when any are (the focus is what we are talking about).
        in_focus = [e for e in named if key(e) in {key(f) for f in state["focus"]}]
        return {"entities": in_focus or named, "how": "name", "pronoun": has_pronoun(message)}
    people = [e for e in state["focus"] if e["kind"] == "person"]
    return {"entities": people, "how": "focus" if people else "none", "pronoun": has_pronoun(message)}


# ---------- rendering the history ----------

def _card_line(card: dict) -> str:
    """One card as a few words: kind, title, first names (never the whole card)."""
    items = card.get("items") or []
    kind = card.get("kind")
    if kind == "script":
        return f"[call script card for {(card.get('person') or {}).get('name') or 'a person'}]"
    names = []
    for item in items[:4]:
        person, event = item.get("person") or {}, item.get("event") or {}
        if person.get("name"):
            names.append(f"{person['name']} ({event.get('company') or ''})".replace(" ()", ""))
        elif item.get("company"):
            names.append(str(item["company"]))
    more = f" and {card.get('total', len(items)) - len(names)} more" if card.get("total", len(items)) > len(names) else ""
    return f"[{kind} card '{card.get('title') or ''}': " + ", ".join(names) + more + "]" if names else \
        f"[{kind} card '{card.get('title') or ''}']"


def render(message: dict) -> str:
    """One stored message as context text (cut to TURN_CHARS)."""
    who = "RM" if message.get("role") == "user" else "Assistant"
    text = " ".join((message.get("text") or "").split())
    extra = " ".join(_card_line(card) for card in message.get("cards") or [])
    if message.get("clarify"):
        extra += f" [asked: {message['clarify'].get('question')}]"
    if message.get("estimate"):
        extra += f" [cost estimate shown: {(message['estimate'].get('action') or {}).get('title')}]"
    line = f"{who}: {text} {extra}".strip()
    return line[:TURN_CHARS]


def tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def state_block(state: dict) -> str:
    """Summary + focus as text (no digits beyond what the summary already passed)."""
    lines = []
    if state.get("summary"):
        lines.append("Summary of earlier turns: " + state["summary"])
    if state.get("open_questions"):
        lines.append("Still open: " + "; ".join(state["open_questions"][:3]))
    if state["focus"]:
        lines.append("Focus: " + "; ".join(f"{e['label']} ({e.get('company') or e['kind']})" for e in state["focus"]))
    if state["candidates"]:
        lines.append("Last list shown: " + "; ".join(e["label"] for e in state["candidates"]))
    return "\n".join(lines)


def history_lines(messages: list[dict], state: dict) -> list[str]:
    """Rendered messages the summary does not cover yet."""
    return [render(m) for m in messages[state.get("compressed_through", 0):]]


def context_text(messages: list[dict], state: dict) -> str:
    """The conversation context that follows the stable prefix: state block, then the uncompressed turns."""
    parts = []
    block = state_block(state)
    if block:
        parts.append("Conversation state:\n" + block)
    lines = history_lines(messages, state)
    if lines:
        parts.append("Last turns:\n" + "\n".join(lines))
    return "\n\n".join(parts)


# ---------- compression ----------

class CompressAnswer(BaseModel):
    """The cheap model's state block."""

    model_config = ConfigDict(extra="forbid")
    summary: str
    entities: list[str]
    open_questions: list[str]


def needs_compression(messages: list[dict], state: dict, threshold: int | None = None) -> bool:
    """True when the uncompressed history is past the threshold and there are turns older than the last K."""
    threshold = HISTORY_COMPRESS_TOKENS if threshold is None else threshold
    older = len(messages) - state.get("compressed_through", 0) - 2 * KEEP_TURNS
    return older > 0 and tokens("\n".join(history_lines(messages, state))) > threshold


def code_summary(lines: list[str], previous: str) -> str:
    """A $0 summary: what the RM asked, in order (used for the $0 role and when the model fails)."""
    asked = [line[4:].split(" [")[0][:120] for line in lines if line.startswith("RM: ")]
    text = (previous + " " if previous else "") + ("Earlier the RM asked: " + "; ".join(asked) + "." if asked else "")
    return text.strip()[-SUMMARY_CHARS:]


def compress(messages: list[dict], state: dict, turn_id: str, model: str | None, allow_model: bool) -> dict:
    """Fold every uncompressed message except the last K turns into the summary. Returns the record.

    The model writes the summary; any digit in it that is not in the text it summarised is removed (the
    verifier), so a summary can never carry a new number. Without a model, code writes it.
    """
    start = state.get("compressed_through", 0)
    cut = len(messages) - 2 * KEEP_TURNS
    older = [render(m) for m in messages[start:cut]]
    before = tokens("\n".join(history_lines(messages, state)) + state.get("summary", ""))
    source = (state.get("summary") or "") + "\n" + "\n".join(older)
    record = {"at": _now(), "messages": len(older), "model": None, "cost_usd": 0.0, "calls": 0, "removed": [],
              "by": "code"}
    summary, entities, open_q = None, list(state.get("summary_entities") or []), list(state.get("open_questions") or [])
    if allow_model and model:
        from api.chat import llm, prompts

        user = (f"Earlier summary: {state.get('summary') or '(none)'}\n\nTurns to fold in:\n" + "\n".join(older))[:9000]
        messages_out = prompts.system_messages(prompts.COMPRESS) + [{"role": "user", "content": user}]
        try:
            parsed, cost, calls = llm.call("compress", model, messages_out, CompressAnswer, PROMPT_VERSION, turn_id)
            answer = CompressAnswer.model_validate(parsed)
            summary, removed = verifier.verify(answer.summary, source)
            entities = [verifier.verify(e, source)[0] for e in answer.entities][:10]
            open_q = [verifier.verify(q, source)[0] for q in answer.open_questions][:3]
            record.update(model=model, cost_usd=cost, calls=calls, removed=removed, by="model")
        except Exception as exc:  # the model failed: code writes the summary instead
            record.update(model=model, cost_usd=getattr(exc, "chat_cost", (0.0, 0))[0], error="model did not answer")
    if summary is None:
        summary = code_summary(older, state.get("summary") or "")
    state["summary"] = summary[:SUMMARY_CHARS]
    state["summary_entities"], state["open_questions"] = entities, open_q
    state["compressed_through"] = cut
    after = tokens("\n".join(history_lines(messages, state)) + state["summary"])
    record.update(tokens_before=before, tokens_after=after, tokens_saved=max(before - after, 0))
    state.setdefault("compressions", []).append(record)
    return record
