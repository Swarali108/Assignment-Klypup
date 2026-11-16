"""Turn extract.json rows into people with amounts, timing and confidence.

Code only. The one model call is identity's strong-model check on a name pair
it cannot settle by rules. Amounts use Decimal and only verified values: a value
verify rejected is never used, and a missing input makes the figure "unknown".

This module is the same for every event type. config/event_types.py says which
fields a person carries and which rules module (agents/rules_<name>.py) sets
their seller status, amounts and timing.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable

from agents.event_rules import rules_for
from agents.extract import merge_group
from agents.figures import kept_evidence
from agents.identity import ask_strong_model, family_groups, resolve_identities
from agents.names import holder_type
from config.event_types import event_config


def build_people(extracted: dict, spec, ask: Callable | None = None, as_of: date | None = None) -> dict:
    """people.json for one event: people sorted by name, identity_log, family_groups, counts.

    as_of (default today) decides which dates are past: listing, payment, lock-in ends.
    spec.event_type picks the rules; a spec without one is read as "ipo".
    """
    as_of = as_of or date.today()
    event_type = getattr(spec, "event_type", "ipo")
    config = event_config(event_type)
    rules = rules_for(event_type)
    rows = [row for row in extracted.get("rows") or [] if str(row.get("name_as_printed") or "").strip()]
    holders = [_holder_view(row) for row in rows]
    calls = {"count": 0}
    resolved = resolve_identities(holders, spec.event_id, _counting(ask, calls))
    context = rules.context(extracted, as_of)
    people = [_person(rows, group, holders, resolved, context, config, rules) for group in resolved["groups"]]
    families = family_groups([{"name": p["name_as_printed"], "holder_type": p["holder_type"]} for p in people])
    _attach_families(people, families)
    people.sort(key=lambda person: (person["name_clean"], person["name_as_printed"]))
    return {
        "event_id": spec.event_id,
        "as_of": as_of.isoformat(),
        **rules.summary(context),
        "people": people,
        "identity_log": resolved["log"],
        "family_groups": families,
        "counts": _counts(people, resolved["log"], families, calls["count"], config),
    }


def confidence(person: dict, flags: list[str], llm_matched: bool, config: dict | None = None) -> dict:
    """high, medium or low with short reasons. Kept apart from the amount.

    low: holder type or identity unsure. high: name verified in the seller section
    and holdings agree across sections. medium: everything else.
    """
    config = config or event_config("ipo")
    holding = config["holding_field"]
    sections = sorted({item["section"] for item in kept_evidence(person) if item.get("section")})
    held = sorted({item["section"] for item in kept_evidence(person, holding) if item.get("section")}) if holding else []
    reasons: list[str] = []
    if person["holder_type"] == "unsure":
        reasons.append("holder type unsure")
    reasons.extend(flag for flag in flags if "unsure" in flag)
    if reasons:
        return {"level": "low", "reasons": reasons}
    in_seller = config["seller_section"] in sections
    agree = bool(holding) and len(held) >= 2 and holding not in (person.get("conflicts") or {})
    label = config["seller_label"]
    reasons.append(f"name verified in {label}" if in_seller else f"not in {label}")
    if holding:
        reasons.append(_holding_reason(person, held, holding))
    if len(sections) == 1:
        reasons.append(f"found in one section only ({sections[0]})")
    if llm_matched:
        reasons.append("identity matched by the strong model")
    level = "high" if in_seller and agree and not llm_matched else "medium"
    return {"level": level, "reasons": reasons}


def _holding_reason(person: dict, held: list[str], holding: str) -> str:
    """One reason about the holding that should agree across sections."""
    if holding in (person.get("conflicts") or {}):
        return "pre-offer holdings differ across sections"
    if len(held) >= 2:
        return f"holdings agree across {len(held)} sections ({', '.join(held)})"
    if len(held) == 1:
        return f"holdings found in one section only ({held[0]})"
    return "no verified pre-offer holding"


def _person(
    rows: list[dict],
    group: list[int],
    holders: list[dict],
    resolved: dict,
    context: dict,
    config: dict,
    rules,
) -> dict:
    """One person from the rows identity grouped together."""
    members = [rows[index] for index in group]
    merged = merge_group(members, config["merge_fields"], config["role_priority"])
    kind, kind_reason = _group_type(holders, group)
    flags = [flag for index in group for flag in resolved["flags"].get(index, [])] + list(merged.get("flags") or [])
    if kind == "unsure":
        flags.append(f"holder type unsure: {kind_reason}")
    person = {
        "person_id": "p_" + re.sub(r"[^a-z0-9]+", "_", merged["name_clean"]).strip("_"),
        "name_as_printed": merged["name_as_printed"],
        "names_as_printed": _distinct(row.get("name_as_printed") for row in members),
        "name_clean": merged["name_clean"],
        "holder_type": kind,
        "holder_type_reason": kind_reason,
        "role_as_printed": merged.get("role_as_printed") or printed_role(merged.get("role_by_section") or {}, config["role_priority"]),
        "role_by_section": merged.get("role_by_section") or {},
        **{field: merged.get(field) for field in config["person_fields"]},
        "conflicts": merged.get("conflicts") or {},
        "flags": flags,
        "family_group": None,
        "evidence": merged.get("evidence") or [],
    }
    rules.apply(person, members, context)
    llm_matched = any(index in resolved["llm_merged"] for index in group) and len(group) > 1
    person["confidence"] = confidence(person, flags, llm_matched, config)
    return person


def printed_role(role_by_section: dict, role_priority: tuple[str, ...] = ()) -> str | None:
    """The verified printed role to show when no priority section printed one.

    role_by_section holds only roles verify kept. A role printed in another section
    (for example the average-cost table: "Promoter Selling Shareholder") is still the
    holder's printed role, so it is used rather than leaving the role unknown.
    Priority sections come first, then the others in name order.
    """
    ordered = [section for section in role_priority if section in role_by_section]
    ordered += sorted(section for section in role_by_section if section not in ordered)
    for section in ordered:
        role = role_by_section.get(section)
        if role and str(role).strip():
            return str(role)
    return None


def _holder_view(row: dict) -> dict:
    """What identity needs from one row: the printed name, its type and its name quotes."""
    name = str(row.get("name_as_printed"))
    quotes = [item.get("quote") for item in row.get("evidence") or [] if item.get("field") == "name_as_printed"]
    return {"name": name, "holder_type": holder_type(name)[0], "quotes": [q for q in quotes if q]}


def _group_type(holders: list[dict], group: list[int]) -> tuple[str, str]:
    """One type for a merged group. Members that disagree make it unsure."""
    kinds = {holders[index]["holder_type"] for index in group}
    if len(kinds) > 1:
        return "unsure", "merged names have different types: " + ", ".join(sorted(kinds))
    return holder_type(holders[group[0]]["name"])


def _attach_families(people: list[dict], families: list[dict]) -> None:
    """Put {id, reason} on each family member. The reason lists only links that name them."""
    for family in families:
        for person in people:
            if person["name_as_printed"] not in family["members"]:
                continue
            mine = [text for text in family["reasons"] if f"'{person['name_as_printed']}'" in text]
            person["family_group"] = {"id": family["id"], "reason": "; ".join(mine or family["reasons"])}


def _distinct(values) -> list[str]:
    """Each printed value once, in first-seen order."""
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _counting(ask: Callable | None, calls: dict) -> Callable:
    """Wrap the identity model call so build_people can count how often it ran."""
    target = ask or ask_strong_model

    def counted(left: dict, right: dict, event_id: str) -> dict:
        calls["count"] += 1
        return target(left, right, event_id)

    return counted


def _counts(people: list[dict], log: list[dict], families: list[dict], llm_asks: int, config: dict) -> dict:
    """Totals for the report. A figure an event type does not have counts as not computed."""
    def tally(values) -> dict:
        found: dict[str, int] = {}
        for value in values:
            found[value] = found.get(value, 0) + 1
        return dict(sorted(found.items()))

    def computed(person: dict, key: str) -> bool:
        return (person["amounts"].get(key) or {}).get("status") == "computed"

    seller_section = config["seller_section"]
    return {
        "people": len(people),
        "by_holder_type": tally(p["holder_type"] for p in people),
        "by_confidence": tally(p["confidence"]["level"] for p in people),
        "sellers": sum(1 for p in people if any(i.get("section") == seller_section for i in kept_evidence(p))),
        "sellers_unverified": sum(1 for p in people if p.get("seller_status") == "unverified"),
        "proceeds_computed": sum(1 for p in people if computed(p, "proceeds")),
        "gain_computed": sum(1 for p in people if computed(p, "gain")),
        "retained_valued": sum(1 for p in people if computed(p, "retained")),
        "retained_timing": tally((p["timing"].get("retained") or {}).get("status", "not_applicable") for p in people),
        "identity_decisions": tally(entry["method"] for entry in log),
        "identity_merges": sum(1 for entry in log if entry["outcome"] == "merge"),
        "llm_asks": llm_asks,
        "family_groups": len(families),
        "flagged": sum(1 for p in people if p["flags"]),
    }
