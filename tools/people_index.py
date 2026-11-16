"""A cross-event index of people, and follow-on matches one level deep. Code only.

After the people step, outputs/index.json gets one entry per person of this event
(re-running an event replaces its entries). Each person is then looked up against
the entries of every other event, with the identity rules:
  - same identity tokens after spelling rules (agents.identity.identity_tokens);
  - never two persons with one surname and different first names.
Match strength:
  - persons with 3 or more name tokens, entities and family vehicles: "likely same holder";
  - persons with 2 tokens, and unsure types: "possible: common name, confirm before using".

Stop rules (also printed in report.md):
  - only events already processed into the index are searched;
  - no web search and no new document fetch;
  - at most MAX_MATCHES matches per person;
  - one level deep: a match's own matches are not followed.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from agents.event_rules import rules_for
from agents.identity import different_first_names, identity_tokens

MAX_MATCHES = 10
LIKELY = "likely same holder"
POSSIBLE = "possible: common name, confirm before using"
STOP_RULES = (
    "only events already processed into outputs/index.json are searched",
    "no web search and no new document fetch",
    f"at most {MAX_MATCHES} matches per person",
    "one level deep: a match's own matches are not followed",
)


def link_event(people_doc: dict, spec, index_path: Path) -> dict:
    """Add follow_on to every person, count the lookups, and write this event's index entries."""
    index = load_index(index_path)
    others = [entry for entry in index if entry["event_id"] != spec.event_id]
    as_of = date.fromisoformat(people_doc["as_of"])
    rules = rules_for(spec.event_type)
    mine = [index_entry(person, spec, rules, as_of) for person in people_doc["people"]]
    total = 0
    for person, entry in zip(people_doc["people"], mine):
        person["follow_on"] = follow_on(entry, others)
        total += len(person["follow_on"])
    people_doc["counts"]["index_lookups"] = len(mine)
    people_doc["counts"]["follow_on_matches"] = total
    save_index(index_path, others + mine)
    return people_doc


def index_entry(person: dict, spec, rules, as_of: date) -> dict:
    """What the index keeps for one person."""
    return {
        "event_id": spec.event_id,
        "event_type": spec.event_type,
        "company": spec.company,
        "person_id": person["person_id"],
        "name_as_printed": person["name_as_printed"],
        "identity_tokens": sorted(identity_tokens(person["name_as_printed"])),
        "holder_type": person["holder_type"],
        "role": person.get("role_as_printed"),
        "amount": rules.amount_display(person),
        "trigger_date": trigger_date(person, as_of),
    }


def follow_on(entry: dict, others: list[dict]) -> list[dict]:
    """Matches for one person among other events' entries, strongest first, at most MAX_MATCHES."""
    found: list[dict] = []
    for other in others:
        strength = match_strength(entry, other)
        if strength is None:
            continue
        found.append({
            "event_id": other["event_id"],
            "company": other["company"],
            "name_as_printed": other["name_as_printed"],
            "role": other["role"],
            "amount": other["amount"],
            "trigger_date": other["trigger_date"],
            "match_strength": strength,
            "reason": f"same name tokens after spelling rules: '{entry['name_as_printed']}' / '{other['name_as_printed']}'",
        })
    found.sort(key=lambda match: (match["match_strength"] != LIKELY, match["event_id"], match["name_as_printed"]))
    return found[:MAX_MATCHES]


def match_strength(entry: dict, other: dict) -> str | None:
    """LIKELY, POSSIBLE, or None when the two are not the same holder by the identity rules."""
    if not entry["identity_tokens"] or entry["identity_tokens"] != other["identity_tokens"]:
        return None
    left = {"name": entry["name_as_printed"], "holder_type": entry["holder_type"]}
    right = {"name": other["name_as_printed"], "holder_type": other["holder_type"]}
    if different_first_names(left, right):
        return None
    if entry["holder_type"] == "person" and other["holder_type"] == "person":
        return LIKELY if len(entry["identity_tokens"]) >= 3 else POSSIBLE
    if "unsure" in (entry["holder_type"], other["holder_type"]):
        return POSSIBLE
    return LIKELY


def trigger_date(person: dict, as_of: date) -> str | None:
    """The latest dated trigger on the person: money in hand, a payment or sale, or a lock-in end."""
    dates: list[str] = []
    for timing in (person.get("timing") or {}).values():
        if timing.get("since"):
            dates.append(timing["since"])
        elif timing.get("days_since") is not None:
            dates.append((as_of - timedelta(days=timing["days_since"])).isoformat())
        for period in timing.get("periods") or []:
            if period.get("status") == "unlocked_since":
                dates.append(period["ends_on"])
    return max(dates) if dates else None


def load_index(path: Path) -> list[dict]:
    """The index entries, or an empty list when there is no index yet."""
    if not Path(path).is_file():
        return []
    return json.loads(Path(path).read_text(encoding="utf-8")).get("entries") or []


def save_index(path: Path, entries: list[dict]) -> None:
    """Write the index sorted by event and person, so reruns give the same file."""
    ordered = sorted(entries, key=lambda entry: (entry["event_id"], entry["person_id"]))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = {"stop_rules": list(STOP_RULES), "entries": ordered}
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
