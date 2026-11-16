"""No event, company, document, holder or offer number is written into the code.

For every events/*.json: its event_id, company, each document URL, and every holder
name in outputs/<event_id>/people.json must not appear (case-insensitive) in agents/,
config/, tools/, run.py or app.py. A 4+ digit number from any event's offer_facts
must not appear either. Dates are left out of the number check: a year such as 2026
is not an offer number, and code comments carry their own dates.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from agents.verify import DATE_FIELDS, number_tokens

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ("agents", "config", "tools")
CODE_FILES = ("run.py", "app.py")


def _code_files() -> list[Path]:
    files = [ROOT / name for name in CODE_FILES]
    for folder in CODE_DIRS:
        files.extend(sorted((ROOT / folder).rglob("*.py")))
    return files


def _code_text() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8").lower() for path in _code_files()}


def _events() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted((ROOT / "events").glob("*.json"))]


def _outputs(event_id: str, name: str) -> dict:
    path = ROOT / "outputs" / event_id / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _strings(event: dict) -> list[str]:
    """Everything event-specific that must stay out of the code."""
    found = [event["event_id"], event["company"]] + [document["url"] for document in event["documents"]]
    people = _outputs(event["event_id"], "people.json").get("people") or []
    for person in people:
        found.extend(person.get("names_as_printed") or [person["name_as_printed"]])
    return [text for text in found if text and len(text.strip()) >= 4]


def _offer_numbers(event: dict) -> set[Decimal]:
    """4+ digit numbers in this event's offer facts, dates left out."""
    offer = _outputs(event["event_id"], "extract.json").get("offer_facts") or {}
    numbers: set[Decimal] = set()
    for field, value in offer.items():
        if field in DATE_FIELDS or not isinstance(value, str):
            continue
        numbers.update(number for number in number_tokens(value) if abs(number) >= 1000)
    return numbers


def test_no_event_text_in_code():
    code = _code_text()
    hits = [
        f"{text!r} ({event['event_id']}) in {path.relative_to(ROOT)}"
        for event in _events()
        for text in _strings(event)
        for path, body in code.items()
        if text.lower() in body
    ]
    assert hits == []


def test_no_offer_number_in_code():
    code = {path: set(number_tokens(body)) for path, body in _code_text().items()}
    hits = [
        f"{number} ({event['event_id']}) in {path.relative_to(ROOT)}"
        for event in _events()
        for number in sorted(_offer_numbers(event))
        for path, numbers in code.items()
        if number in numbers
    ]
    assert hits == []


def test_the_check_reads_names_from_outputs():
    """Guard against a check that passes because it found nothing to look for."""
    processed = [event for event in _events() if _outputs(event["event_id"], "people.json")]
    assert processed, "no event has people.json; run an event first"
    assert all(len(_strings(event)) > 3 for event in processed)
