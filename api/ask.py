"""Plain-English questions -> a fixed filter -> people chosen by code.

The cheap model (tools.llm.llm_call) only maps the question to the AskFilters JSON below;
code applies the filter to stored call items, so the model never writes a number the RM
sees. A numeric bound is kept only when that number is in the question. When the model
fails (no key, network, bad JSON), a small rule parser reads the same filter from the
words; when that finds nothing, a keyword search over names, companies and roles runs.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Callable, Literal

from pydantic import BaseModel

from api.views import TIER_LABELS, TYPE_LABELS, cr_text

PROMPT_VERSION = "ask-v2"
# The timing statuses the call items really carry. A model answer outside this set is dropped, not applied.
TIMING_STATUSES = {"due_past", "scheduled", "unlocked", "partly_unlocked", "locked_in", "after_date"}
SCHEMA_NAME = "AskFilters"


class AskFilters(BaseModel):
    """The only things a question can ask for."""

    event_type: Literal["ipo", "buyback", "ofs_stock_exchange"] | None = None
    role_contains: str | None = None
    tier: Literal["cash_now", "unlock", "holding"] | None = None
    min_cr: float | None = None
    max_cr: float | None = None
    timing_status: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    company: str | None = None


SYSTEM = (
    "You turn a wealth manager's question into a JSON filter. Reply with JSON only, keys: "
    "event_type (ipo|buyback|ofs_stock_exchange|null), role_contains (a word from a printed role such as "
    "'promoter', 'director', 'investor', or null), tier (cash_now = cash in hand or due soon; unlock = shares "
    "recently unlocked; holding = holds shares; or null), min_cr and max_cr (amounts in rupees crore, numbers "
    "only, or null), timing_status (due_past = money already payable; scheduled; unlocked; partly_unlocked; locked_in; after_date; or null. 'cash in hand' is tier cash_now, never a timing_status), confidence (high|medium|low|null), "
    "company (part of a company name, or null). Use null for anything the question does not ask."
)


def model_filters(question: str) -> dict:
    """Ask the cheap model for the filter (cached by tools.llm)."""
    from tools.llm import llm_call, register_schema

    register_schema(SCHEMA_NAME, AskFilters)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    return llm_call("ask", messages, SCHEMA_NAME, PROMPT_VERSION, event_id="ask")


_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)")
ROLE_WORDS = ("promoter", "director", "investor", "founder", "employee", "trust", "selling shareholder")


def numbers_in(question: str) -> set[Decimal]:
    """Every number written in the question (commas ignored)."""
    return {Decimal(m.replace(",", "")) for m in _NUMBER.findall(question)}


def rule_filters(question: str, companies: list[str]) -> dict:
    """The same filter read by simple word rules (used when the model is unavailable)."""
    q = question.lower()
    found: dict = {}
    if "buyback" in q or "buy-back" in q:
        found["event_type"] = "buyback"
    elif "ipo" in q or "listing" in q:
        found["event_type"] = "ipo"
    elif "offer for sale" in q or "ofs" in q:
        found["event_type"] = "ofs_stock_exchange"
    for word in ROLE_WORDS:
        if word in q or word + "s" in q:
            found["role_contains"] = word
            break
    if any(w in q for w in ("cash", "in hand", "sold", "proceeds", "liquid")):
        found["tier"] = "cash_now"
    elif "unlock" in q:
        found["tier"] = "unlock"
    elif "holding" in q or "holds" in q:
        found["tier"] = "holding"
    for match in re.finditer(r"(above|over|more than|at least|>=?|below|under|less than|<=?)\s*(?:rs\.?|₹|inr)?\s*"
                             r"(\d[\d,]*(?:\.\d+)?)\s*(cr|crore|crores)?", q):
        value = float(match.group(2).replace(",", ""))
        key = "min_cr" if match.group(1) in ("above", "over", "more than", "at least", ">", ">=") else "max_cr"
        found[key] = value
    for level in ("high", "medium", "low"):
        if f"{level} confidence" in q:
            found["confidence"] = level
    for company in companies:
        first = company.lower().split()[0]
        if len(first) > 3 and re.search(rf"\b{re.escape(first)}\b", q):
            found["company"] = company.split()[0]
            break
    return found


def safe_filters(raw: dict, question: str) -> dict:
    """Validated filter; numeric bounds dropped unless the number is in the question."""
    try:
        parsed = AskFilters.model_validate(raw or {}).model_dump()
    except ValueError:
        return {}
    allowed = numbers_in(question)
    for key in ("min_cr", "max_cr"):
        if parsed[key] is not None and Decimal(str(parsed[key])).normalize() not in {n.normalize() for n in allowed}:
            parsed[key] = None
    if parsed["timing_status"] not in TIMING_STATUSES:
        parsed["timing_status"] = None
    for key in ("role_contains", "company", "timing_status"):
        if isinstance(parsed[key], str) and not parsed[key].strip():
            parsed[key] = None
    return {k: v for k, v in parsed.items() if v is not None}


def apply(filters: dict, items: list[dict]) -> list[dict]:
    """Items matching every filter, in call order."""
    out = []
    for item in items:
        value = item["amount"]["value_cr"]
        if filters.get("event_type") and item["event"]["type"] != filters["event_type"]:
            continue
        if filters.get("role_contains") and filters["role_contains"].lower() not in (item["person"]["role"] or "").lower():
            continue
        if filters.get("tier") and item["tier"] != filters["tier"]:
            continue
        if filters.get("min_cr") is not None and (value is None or value < filters["min_cr"]):
            continue
        if filters.get("max_cr") is not None and (value is None or value > filters["max_cr"]):
            continue
        if filters.get("timing_status") and item["timing"]["status"] != filters["timing_status"]:
            continue
        if filters.get("confidence") and item["confidence"]["level"] != filters["confidence"]:
            continue
        if filters.get("company") and filters["company"].lower() not in item["event"]["company"].lower():
            continue
        out.append(item)
    return out


def chips(filters: dict) -> list[str]:
    """'Promoters', 'Cash in hand', '≥ ₹50.00 Cr' ... for showing how the question was read."""
    words = []
    if filters.get("event_type"):
        words.append(TYPE_LABELS.get(filters["event_type"], filters["event_type"]))
    if filters.get("role_contains"):
        words.append(f"Role: {filters['role_contains'].title()}")
    if filters.get("tier"):
        words.append(TIER_LABELS[filters["tier"]])
    if filters.get("min_cr") is not None:
        words.append(f"≥ {cr_text(Decimal(str(filters['min_cr'])))}")
    if filters.get("max_cr") is not None:
        words.append(f"≤ {cr_text(Decimal(str(filters['max_cr'])))}")
    if filters.get("timing_status"):
        words.append(f"Timing: {filters['timing_status'].replace('_', ' ')}")
    if filters.get("confidence"):
        words.append(f"{filters['confidence'].title()} confidence")
    if filters.get("company"):
        words.append(f"Company: {filters['company']}")
    return words


def keyword(question: str, items: list[dict]) -> list[dict]:
    """Items whose name, company or role contains every word (stop words ignored)."""
    stop = {"the", "a", "an", "of", "in", "with", "who", "show", "me", "all", "and", "for", "to", "find", "people"}
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in stop]
    if not words:
        return []
    found = []
    for item in items:
        hay = " ".join([item["person"]["name"] or "", item["event"]["company"], item["person"]["role"] or ""]).lower()
        if all(w in hay for w in words):
            found.append(item)
    return found


def ask(question: str, items: list[dict], companies: list[str], model: Callable[[str], dict] | None = model_filters) -> dict:
    """{filters, chips, people, explanation, interpreted_by, count}."""
    question = (question or "").strip()[:300]
    if not question:
        return {"question": "", "filters": {}, "chips": [], "people": [], "count": 0, "interpreted_by": "none",
                "explanation": "Type a question, for example: promoters with cash in hand above 50 crore."}
    filters, how = {}, "assistant"
    try:
        filters = safe_filters(model(question) if model else {}, question)
    except Exception:  # model unavailable: fall back to rules
        filters = {}
    if not filters:
        filters, how = safe_filters(rule_filters(question, companies), question), "rules"
    if filters:
        people = apply(filters, items)
        explanation = f"Interpreted as: {' · '.join(chips(filters))}. {len(people)} match."
    else:
        people, how = keyword(question, items), "keyword"
        explanation = f"Searched names, companies and roles for “{question}”. {len(people)} match."
    return {"question": question, "filters": filters, "chips": chips(filters), "people": people, "count": len(people),
            "interpreted_by": how, "explanation": explanation}


def debug_dump(result: dict) -> str:
    """Compact JSON for logs."""
    return json.dumps({k: v for k, v in result.items() if k != "people"}, ensure_ascii=False)
