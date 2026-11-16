"""Cross-event data for the dashboard, read from events/ and outputs/. No Streamlit here.

It selects and counts what the pipeline stored; it never computes an amount or a date.
Every count has a rule in config/ranking.py (NEW_SIGNAL_DAYS, HIGH_PRIORITY_*), and
anything not stored (a document's publication date, history to compare against) is
reported as unknown rather than filled in.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from agents.spec import load_event_spec
from config.ranking import HIGH_PRIORITY_CONFIDENCE, HIGH_PRIORITY_TIMING, NEW_SIGNAL_DAYS

OUTPUT_FILES = ("extract", "people", "ranked", "briefs", "cost", "timeline")
EVENT_TYPE_LABELS = {"ipo": "IPO", "buyback": "Buyback", "ofs_stock_exchange": "OFS (stock exchange)"}
# What each failed holder-table check means for the call list.
COMPLETENESS_WORDS = {
    "rows missing": "The verified rows add up to less than the printed total, so people may be missing.",
    "sum exceeds printed total": "The verified rows add up to more than the printed total; a row may be read twice.",
    "values unverified": "Some share counts could not be verified on the page, so the total cannot be checked.",
}
BAD_COMPLETENESS = tuple(COMPLETENESS_WORDS)


def read_json(path: Path) -> dict | None:
    """One output file, or None when it is not there."""
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_outputs(outputs_dir: Path, event_id: str) -> dict:
    """Every output file of one event; None for a file not written yet."""
    return {name: read_json(outputs_dir / event_id / f"{name}.json") for name in OUTPUT_FILES}


def load_events(events_dir: Path, outputs_dir: Path) -> list[dict]:
    """Hand-made events/*.json, then discovered events/auto/*.json, as {"spec", "out", "processed", "auto"}.

    processed: people.json and ranked.json exist. A discovered file whose id a hand-made
    event already uses is skipped (discovery never writes one, but a stale file could exist).
    """
    events, ids = [], set()
    for path in sorted(events_dir.glob("*.json")) + sorted((events_dir / "auto").glob("*.json")):
        spec = load_event_spec(path)
        if spec.event_id in ids:
            continue
        ids.add(spec.event_id)
        out = load_outputs(outputs_dir, spec.event_id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        events.append({"spec": spec, "path": path, "out": out, "auto": path.parent.name == "auto",
                       "discovery": raw.get("discovery"),
                       "processed": out["people"] is not None and out["ranked"] is not None})
    return events


def processed(events: list[dict]) -> list[dict]:
    """Only the events with outputs."""
    return [event for event in events if event["processed"]]


def type_label(event_type: str) -> str:
    """"IPO", "Buyback", or the type id."""
    return EVENT_TYPE_LABELS.get(event_type, event_type)


# ---------- dates ----------

def event_date(people_doc: dict | None) -> dict:
    """The event's money date as stored: listing, buyback payment, or sale. Else unknown."""
    people_doc = people_doc or {}
    listing = people_doc.get("listing") or {}
    if listing.get("status") in ("verified", "scheduled") and listing.get("listed_on"):
        scheduled = listing["status"] == "scheduled"
        return {"date": listing["listed_on"], "as_printed": listing.get("date_as_printed"),
                "kind": "scheduled listing" if scheduled else "listing",
                "status": "scheduled, not confirmed by a listing notice" if scheduled else "verified"}
    dates = people_doc.get("buyback_dates") or {}
    for key in sorted(dates, key=lambda name: name != "payment"):
        value = dates[key]
        if isinstance(value, dict) and value.get("status") == "verified" and value.get("date"):
            printed = ((value.get("inputs") or [{}])[0]).get("value") or value["date"]
            return {"date": value["date"], "as_printed": printed, "kind": f"buyback {key.replace('_', ' ')}",
                    "status": "verified"}
    sale = people_doc.get("sale") or {}
    if sale.get("sale_date_parsed"):
        return {"date": sale["sale_date_parsed"], "as_printed": sale.get("sale_date"), "kind": "sale",
                "status": "verified"}
    return {"date": None, "as_printed": None, "kind": "event date", "status": "unknown",
            "reason": "no verified event date in people.json"}


def first_processed(runs_csv: Path) -> dict[str, str]:
    """event_id -> the date (YYYY-MM-DD) of its first successful run in runs.csv."""
    if not runs_csv.is_file():
        return {}
    found: dict[str, str] = {}
    with runs_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") == "ok" and row.get("event_id") and row.get("started_at"):
                found.setdefault(row["event_id"], row["started_at"][:10])
    return found


# ---------- KPIs ----------

def event_sources(event: dict) -> list[str]:
    """Where an event came from: its discovery sources, or "hand" for an event file made by hand."""
    return list((event.get("discovery") or {}).get("sources") or []) or ["hand"]


def provenance(event: dict) -> dict:
    """"Discovered from <source> on <date>" with the items' links, or "Added by hand"."""
    from config.sources import SOURCES

    found = event.get("discovery")
    if not found:
        return {"kind": "hand", "text": "Added by hand", "links": []}
    names = {source["id"]: source["name"] for source in SOURCES}
    sources = ", ".join(names.get(source, source) for source in found.get("sources") or []) or "a public source"
    first = str(found.get("first_seen") or "")[:10] or "an unknown date"
    links = [{"title": item.get("title") or "item", "link": item.get("link")} for item in found.get("items") or []]
    return {"kind": "discovered", "text": f"Discovered from {sources} on {first}", "links": links}


def is_new_signal(entry: dict) -> bool:
    """The money event behind this rank happened 0 to NEW_SIGNAL_DAYS days ago."""
    days = (entry.get("trigger") or {}).get("days_since")
    return days is not None and 0 <= days <= NEW_SIGNAL_DAYS


def is_high_priority(entry: dict) -> bool:
    """High confidence, and money in hand, at listing, or due on a printed timetable date."""
    return entry.get("confidence") in HIGH_PRIORITY_CONFIDENCE and entry.get("timing_display_status") in HIGH_PRIORITY_TIMING


FILTERS = {"all": lambda entry: True, "new": is_new_signal, "high": is_high_priority}
FILTER_LABELS = {"all": "Everyone", "new": "New signals", "high": "High priority"}


def callable_entries(events: list[dict]) -> list[tuple[dict, dict]]:
    """(event, ranked entry) for every callable person in every processed event."""
    return [(event, entry) for event in processed(events) for entry in event["out"]["ranked"].get("callable") or []]


def kpis(events: list[dict]) -> dict:
    """Counts for the three KPI cards and the summary line."""
    entries = [entry for _event, entry in callable_entries(events)]
    return {
        "events": len(processed(events)),
        "sources": len({source for event in processed(events) for source in event_sources(event)}),
        "potential": len(entries),
        "new": sum(1 for entry in entries if is_new_signal(entry)),
        "high": sum(1 for entry in entries if is_high_priority(entry)),
        "new_days": NEW_SIGNAL_DAYS,
    }


# ---------- charts ----------

def timeline_rows(events: list[dict], basis: str, detected: dict[str, str]) -> list[dict]:
    """One row per processed event with a known date: the money date, or the first-processed date."""
    rows = []
    for event in processed(events):
        spec = event["spec"]
        when = event_date(event["out"]["people"])["date"] if basis == "event" else detected.get(spec.event_id)
        if when:
            rows.append({"event_id": spec.event_id, "company": spec.company, "type": type_label(spec.event_type),
                         "date": when})
    return rows


def month_start(value: date) -> date:
    """The first day of value's month."""
    return value.replace(day=1)


def monthly_counts(rows: list[dict], start: date | None, end: date) -> list[dict]:
    """Events per month from start (or the earliest event) to end's month, with empty months as 0."""
    dated = [(date.fromisoformat(row["date"]), row) for row in rows]
    dated = [(when, row) for when, row in dated if (start is None or when >= start) and when <= end]
    if not dated and start is None:
        return []
    first = month_start(start or min(when for when, _row in dated))
    months, cursor = [], first
    while cursor <= month_start(end):
        inside = [row for when, row in dated if month_start(when) == cursor]
        months.append({"month": cursor.isoformat(), "month_key": cursor.strftime("%Y-%m"),
                       "label": cursor.strftime("%b %Y"), "events": len(inside),
                       "names": "; ".join(f"{row['company']} ({row['type']})" for row in inside) or "none"})
        cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
    return months


def event_mix(events: list[dict]) -> list[dict]:
    """Processed events by type, with each type's whole-number share of all events."""
    counts = Counter(type_label(event["spec"].event_type) for event in processed(events))
    total = sum(counts.values())
    return [{"type": name, "events": count, "share": round(100 * count / total)}
            for name, count in counts.most_common()] if total else []


# ---------- feed, notifications, search ----------

def feed_items(events: list[dict], detected: dict[str, str]) -> list[dict]:
    """One item per processed event, newest money date first; undated events last."""
    items = []
    for event in processed(events):
        spec, out = event["spec"], event["out"]
        when = event_date(out["people"])
        ranked = out["ranked"]
        callable_people = ranked.get("callable") or []
        briefs = (out["briefs"] or {}).get("briefs") or []
        items.append({
            "event_id": spec.event_id,
            "company": spec.company,
            "type": type_label(spec.event_type),
            "date": when,
            "month_key": when["date"][:7] if when["date"] else None,
            "detected": detected.get(spec.event_id),
            "detected_month_key": (detected.get(spec.event_id) or "")[:7] or None,
            "callable": len(callable_people),
            "top": callable_people[0] if callable_people else None,
            "documents": [document.model_dump() for document in spec.documents],
            "verification": verification_lines(out),
        })
    return sorted(items, key=lambda item: item["date"]["date"] or "", reverse=True)


def verification_lines(out: dict) -> list[str]:
    """Short checks a reader can trust or question: completeness, unattributed rows, brief sources."""
    extracted = out["extract"] or {}
    lines = [f"{key}: {result.get('status')}" for key, result in (extracted.get("completeness") or {}).items()]
    unattributed = len(extracted.get("unattributed") or [])
    lines.append(f"{unattributed} row{'s' if unattributed != 1 else ''} failed name verification" if unattributed
                 else "every extracted name verified on its page")
    sources = Counter(brief.get("brief_source") for brief in (out["briefs"] or {}).get("briefs") or [])
    if sources:
        lines.append(f"briefs: {sources.get('llm', 0)} by the model, {sources.get('template', 0)} from the template")
    return lines


def notifications(events: list[dict], today: date) -> list[dict]:
    """Warnings the pipeline stored, one per problem: {"id", "level", "title", "detail", "event_id"}."""
    found = []
    waiting = [event for event in events if event.get("auto") and not event["processed"]]
    if waiting:
        found.append({"id": f"discovered:{len(waiting)}", "level": "info", "event_id": None,
                      "title": f"{len(waiting)} discovered event{'s' if len(waiting) != 1 else ''} not processed yet",
                      "detail": "Found in official sources by discovery. Open the Live feed to see them and why."})
    for event in events:
        spec, out = event["spec"], event["out"]
        if event.get("auto") and not event["processed"]:
            continue
        if not event["processed"]:
            found.append(_note(spec, "none", "info", f"{spec.company}: no outputs yet",
                               "The event file exists but the pipeline has not been run for it."))
            continue
        for key, result in ((out["extract"] or {}).get("completeness") or {}).items():
            if result.get("status") in BAD_COMPLETENESS:
                found.append(_note(spec, f"complete-{key}", "warning", f"{spec.company}: {key} {result['status']}",
                                   COMPLETENESS_WORDS[result["status"]]))
        listing = (out["people"] or {}).get("listing") or {}
        if listing.get("status") == "scheduled" and listing.get("listed_on") and listing["listed_on"] < today.isoformat():
            found.append(_note(spec, "listing-passed", "warning",
                               f"{spec.company}: scheduled listing date has passed",
                               f"The timetable said {listing.get('date_as_printed')}; no listing notice is in the "
                               "event file, so trading is not confirmed. Add the listing announcement."))
        briefs = (out["briefs"] or {}).get("briefs") or []
        templates = [brief for brief in briefs if brief.get("brief_source") == "template"]
        if templates:
            found.append(_note(spec, "template", "info", f"{spec.company}: {len(templates)} template brief(s)",
                               "The model's brief failed a check twice, so a fixed brief built from the fields is shown."))
        failing = [brief for brief in templates if brief.get("template_problem")]
        if failing:
            found.append(_note(spec, "template-problem", "warning", f"{spec.company}: a template brief fails a check",
                               failing[0]["template_problem"]))
    return found


def _note(spec, suffix: str, level: str, title: str, detail: str) -> dict:
    """One notification with a stable id, so read/unread survives reruns."""
    return {"id": f"{spec.event_id}:{suffix}", "level": level, "title": title, "detail": detail,
            "event_id": spec.event_id}


def search_index(events: list[dict]) -> list[dict]:
    """Companies, events and people for the Ctrl+K search. Shown in the browser as text only.

    Discovered events that are not processed yet are listed as events that open the Live feed.
    """
    index = [{"kind": "action", "label": "Add event from a link", "sub": "paste PDF links; the app proposes the event",
              "target": {"page": "feed", "event": None, "person": None, "action": "add"}}]
    index += [{"kind": "event", "label": f"{type_label(event['spec'].event_type)} · {event['spec'].company}",
              "sub": "discovered; not processed yet", "target": {"page": "feed", "event": event["spec"].event_id,
                                                                   "person": None}}
             for event in events if event.get("auto") and not event["processed"]]
    for event in processed(events):
        spec, ranked = event["spec"], event["out"]["ranked"]
        target = {"page": "prospects", "event": spec.event_id, "person": None}
        callable_people = ranked.get("callable") or []
        index.append({"kind": "company", "label": spec.company,
                      "sub": f"{type_label(spec.event_type)} · {len(callable_people)} to call", "target": target})
        when = event_date(event["out"]["people"])
        index.append({"kind": "event", "label": f"{type_label(spec.event_type)} · {spec.company}",
                      "sub": f"{when['kind']}: {when['as_printed'] or 'unknown'}", "target": target})
        for group, entries in (("callable", callable_people), ("entities", ranked.get("entities") or [])):
            for entry in entries:
                index.append({"kind": "person" if group == "callable" else "entity",
                              "label": entry["name_as_printed"],
                              "sub": f"{entry.get('role_as_printed') or 'role unknown'} · {spec.company}",
                              "target": {**target, "person": entry["person_id"], "group": group}})
    return index


# ---------- money becoming available (Home chart) ----------

CASH = "cash"
ESTIMATE = "shares unlocking (estimate, shares not cash)"
# Point status words for the legend: what kind of date each point sits on.
VERIFIED_DATE = "cash, date verified"
SCHEDULED_DATE = "cash, date scheduled"


def person_lookup(event: dict) -> dict[str, dict]:
    """person_id -> person, from people.json."""
    return {person["person_id"]: person for person in (event["out"]["people"] or {}).get("people") or []}


def brief_lookup(event: dict) -> dict[str, dict]:
    """person_id -> brief, from briefs.json."""
    return {brief["person_id"]: brief for brief in (event["out"]["briefs"] or {}).get("briefs") or []}


def money_points(events: list[dict]) -> dict:
    """Stored (date, ₹ crore high end) points for every callable person, and who could not be plotted.

    Cash: computed proceeds on the event's stored money date (listing, buyback payment or
    sale). Estimate: computed retained value on its lock-in ends_on, only when one period
    holds all retained shares. Returns {"points": [...], "date_unknown": [...],
    "amount_unknown": [...], "split_unknown": [...]}; the lists hold "name (company)".
    """
    found = {"points": [], "date_unknown": [], "amount_unknown": [], "split_unknown": []}
    for event in processed(events):
        spec, people = event["spec"], person_lookup(event)
        when = event_date(event["out"]["people"])
        for entry in event["out"]["ranked"].get("callable") or []:
            person = people.get(entry["person_id"])
            if person:
                _cash_point(spec, entry, person, when, found)
                _estimate_point(spec, entry, person, found)
    return found


def _point(spec, entry: dict, figure: dict, date_iso: str, series: str, status: str, kind: str) -> dict:
    """One plotted person: stored date, stored crore_high, stored display text."""
    return {"date": date_iso, "series": series, "status": status, "crore_high": figure["crore_high"],
            "display": figure["display"], "kind": kind, "name": entry["name_as_printed"], "company": spec.company,
            "event_id": spec.event_id, "person_id": entry["person_id"]}


def _who(spec, entry: dict) -> str:
    """"name (company)" for a footnote."""
    return f"{entry['name_as_printed']} ({spec.company})"


def _cash_point(spec, entry: dict, person: dict, when: dict, found: dict) -> None:
    """Proceeds on the event's money date; unknown amounts and dates go to the footnote lists."""
    figure = (person.get("amounts") or {}).get("proceeds") or {}
    if figure.get("status") == "computed" and figure.get("crore_high"):
        if not when["date"]:
            found["date_unknown"].append(_who(spec, entry))
            return
        status = SCHEDULED_DATE if when["kind"].startswith("scheduled") else VERIFIED_DATE
        found["points"].append(_point(spec, entry, figure, when["date"], CASH, status, when["kind"]))
    elif figure.get("status") == "unknown":
        found["amount_unknown"].append(_who(spec, entry))


def _estimate_point(spec, entry: dict, person: dict, found: dict) -> None:
    """Retained value on its lock-in end, only when one stored period covers all retained shares."""
    figure = (person.get("amounts") or {}).get("retained") or {}
    if figure.get("status") != "computed" or not figure.get("crore_high"):
        return
    periods = ((person.get("timing") or {}).get("retained") or {}).get("periods") or []
    if len(periods) == 1 and periods[0].get("share_of_retained") == "all" and periods[0].get("ends_on"):
        found["points"].append(_point(spec, entry, figure, periods[0]["ends_on"], ESTIMATE, ESTIMATE,
                                      f"lock-in ends: {periods[0].get('label')}"))
    elif not periods or any(not period.get("ends_on") for period in periods):
        found["date_unknown"].append(_who(spec, entry))
    else:
        found["split_unknown"].append(_who(spec, entry))


def money_by_date(points: list[dict], start: date | None, end: date | None) -> list[dict]:
    """Sum stored crore_high per (date, series, status) inside [start, end]; keep who and their display text."""
    groups: dict[tuple, list[dict]] = {}
    for point in points:
        when = date.fromisoformat(point["date"])
        if (start is None or when >= start) and (end is None or when <= end):
            groups.setdefault((point["date"], point["series"], point["status"]), []).append(point)
    rows = []
    for (when, series, status), members in sorted(groups.items()):
        total = sum((Decimal(member["crore_high"]) for member in members), Decimal(0))
        rows.append({"date": when, "series": series, "status": status, "crore": float(total),
                     "crore_text": f"₹{total} crore (sum of stored high ends)", "people": len(members),
                     "who": "; ".join(f"{m['name']}, {m['company']}: {m['display']}" for m in members),
                     "kind": members[0]["kind"], "key": f"{when}|{series}|{status}",
                     "person_ids": [(m["event_id"], m["person_id"]) for m in members]})
    return rows


def unique_count(names: list[str]) -> int:
    """How many different people a footnote list names."""
    return len(set(names))


# ---------- today's calls, mix, timing groups ----------

def top_calls(events: list[dict], limit: int | None = 8, only: set | None = None,
              event_type: str | None = None) -> list[dict]:
    """The highest stored scores across events: {event, entry, person, brief, source}, best first.

    only: (event_id, person_id) pairs to keep (a chart click); event_type: a type label.
    """
    calls = []
    for event in processed(events):
        if event_type and type_label(event["spec"].event_type) != event_type:
            continue
        calls.extend(event_calls(event, only))
    calls.sort(key=lambda call: Decimal(str(call["entry"].get("score") or 0)), reverse=True)
    return calls if limit is None else calls[:limit]


def event_calls(event: dict, only: set | None = None, group: str = "callable") -> list[dict]:
    """One event's ranked entries (callable or entities) with their person, brief and first source."""
    people, briefs = person_lookup(event), brief_lookup(event)
    calls = []
    for entry in event["out"]["ranked"].get(group) or []:
        if only is not None and (event["spec"].event_id, entry["person_id"]) not in only:
            continue
        person = people.get(entry["person_id"]) or {}
        calls.append({"event": event, "entry": entry, "person": person, "brief": briefs.get(entry["person_id"]),
                      "source": first_source(person)})
    return calls


def mix_with_people(events: list[dict]) -> list[dict]:
    """Per event type: events, callable people, and the events' whole-number share."""
    people = Counter()
    for event in processed(events):
        people[type_label(event["spec"].event_type)] += len(event["out"]["ranked"].get("callable") or [])
    return [{**row, "people": people[row["type"]]} for row in event_mix(events)]


# Timing status -> filter group. "Unlocked" and "Not applicable" are kept apart from
# "Locked" and "Unknown": unlocked shares are free to sell, and not applicable is not unknown.
TIMING_GROUPS = {
    "In hand": ("in_hand",),
    "Scheduled": ("at_listing", "scheduled", "after_date", "settles"),
    "Locked": ("locked_in", "partly_unlocked"),
    "Unlocked": ("unlocked",),
    "Not applicable": ("not_applicable",),
    "Unknown": ("unknown",),
}
# Chart colour role per group: cash, scheduled, estimate (shares) or unknown.
GROUP_ROLE = {"In hand": "cash", "Scheduled": "scheduled", "Locked": "estimate", "Unlocked": "estimate",
              "Not applicable": "unknown", "Unknown": "unknown"}


def timing_group(status: str | None) -> str:
    """The filter group a stored timing status belongs to; anything else is Unknown."""
    for group, statuses in TIMING_GROUPS.items():
        if status in statuses:
            return group
    return "Unknown"


def first_source(person: dict) -> dict | None:
    """The first page behind the headline amount (proceeds, else retained), else behind the name."""
    from ui.components import evidence_refs

    amounts = person.get("amounts") or {}
    for key in ("proceeds", "retained"):
        figure = amounts.get(key) or {}
        if figure.get("status") == "computed":
            refs = evidence_refs(figure)
            if refs:
                return refs[0]
    refs = evidence_refs(person.get("evidence") or [])
    return refs[0] if refs else None


def money_dates(points: list[dict]) -> dict[tuple, str]:
    """(event_id, person_id) -> the latest stored money date plotted for them, for sorting by date."""
    found: dict[tuple, str] = {}
    for point in points:
        key = (point["event_id"], point["person_id"])
        found[key] = max(found.get(key, ""), point["date"])
    return found


# ---------- call sheet CSV ----------

CALL_SHEET_COLUMNS = ("rank", "name", "role", "company", "why money", "amount", "timing", "confidence", "brief",
                      "first evidence link")
# A cell starting with one of these is read as a formula by spreadsheet programs.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    """Text for a CSV cell; a leading formula character gets a quote prefix so it stays text."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def call_sheet_rows(calls: list[dict]) -> list[dict]:
    """One row per call, from stored fields only, in CALL_SHEET_COLUMNS order."""
    rows = []
    for call in calls:
        entry, brief, source = call["entry"], call.get("brief") or {}, call.get("source") or {}
        rows.append({
            "rank": entry["rank"], "name": entry["name_as_printed"], "role": entry.get("role_as_printed") or "unknown",
            "company": call["event"]["spec"].company, "why money": entry.get("why_money"),
            "amount": entry.get("amount_display"), "timing": entry.get("timing_display"),
            "confidence": entry.get("confidence"), "brief": " ".join(brief.get("lines") or []) or "no brief",
            "first evidence link": source.get("link") or "no page link",
        })
    return rows


def call_sheet_csv(rows: list[dict]) -> str:
    """The call sheet as CSV text; every cell passed through safe_cell."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CALL_SHEET_COLUMNS)
    for row in rows:
        writer.writerow([safe_cell(row.get(column)) for column in CALL_SHEET_COLUMNS])
    return buffer.getvalue()


# ---------- verification funnel, cost, time ----------

def funnel_rows(extracted: dict | None) -> list[dict]:
    """Per section: fields proposed, kept, rejected, unattributed (stored counts), and rejection reasons."""
    extracted = extracted or {}
    reasons: dict[str, Counter] = {}
    for item in extracted.get("rejections") or []:
        reasons.setdefault(item.get("section"), Counter())[item.get("reason")] += 1
    rows = []
    for section, counts in (extracted.get("counts") or {}).items():
        if not isinstance(counts, dict) or "proposed" not in counts:
            continue
        why = "; ".join(f"{reason} ×{count}" for reason, count in reasons.get(section, Counter()).most_common())
        rows.append({"section": section, "proposed": counts.get("proposed", 0), "kept": counts.get("kept", 0),
                     "rejected": counts.get("rejected", 0), "unattributed": counts.get("unattributed", 0),
                     "reasons": why or "none"})
    return rows


def cost_rows(events: list[dict]) -> list[dict]:
    """Per processed event: cost.json totals as stored (this run, no cache, per callable person)."""
    rows = []
    for event in processed(events):
        cost = event["out"]["cost"] or {}
        totals = cost.get("totals") or {}
        if totals:
            rows.append({"company": event["spec"].company, "event_id": event["spec"].event_id,
                         "run_id": cost.get("run_id"), "this run": totals.get("cost_usd"),
                         "no cache": totals.get("fresh_usd"),
                         "per callable (this run)": totals.get("cost_per_callable_usd"),
                         "per callable (no cache)": totals.get("fresh_per_callable_usd")})
    return rows


def time_rows(events: list[dict]) -> list[dict]:
    """Per processed event and step: seconds, calls and cost from timeline.json as stored."""
    return [{"company": event["spec"].company, "step": step["step"], "seconds": step["seconds"],
             "calls": step.get("calls"), "cached": step.get("cached"), "cost_usd": step.get("cost_usd")}
            for event in processed(events) for step in (event["out"]["timeline"] or {}).get("steps") or []]


# ---------- live feed (discovery) ----------

# What the feed can and cannot see, stated on the page.
COVERAGE = ("Main-board offers filed with SEBI. SME offers are filed with NSE/BSE, whose terms we do not read "
            "automatically: add them with a link.")
FEED_STATUS = {
    "ready": "Call list ready",
    "empty": "Processed; no one to call",
    "failed": "Processing failed",
    "waiting": "Supported, not processed yet",
    "unsupported": "Detected; not supported yet",
}


def read_discovery(outputs_dir: Path) -> dict | None:
    """outputs/discovery.json, or None before the first refresh."""
    return read_json(outputs_dir / "discovery.json")


def read_discovery_log(outputs_dir: Path) -> list[dict]:
    """outputs/discovery_log.json entries, oldest first."""
    return (read_json(outputs_dir / "discovery_log.json") or {}).get("entries") or []


def feed_rows(discovery: dict | None, events: list[dict], log: list[dict], today: date, days: int = 30) -> dict:
    """Discovered items as Today / Upcoming / Last N days, each with what was done with it.

    Upcoming: items whose processed event has a stored money date after today.
    """
    groups = {"today": [], "upcoming": [], "recent": []}
    if not discovery:
        return groups
    by_id = {event["spec"].event_id: event for event in events}
    summaries = {summary["event_id"]: summary for summary in discovery.get("events") or []}
    last = {}
    for entry in log:
        last[entry.get("event_id")] = entry
    start = (today - timedelta(days=days)).isoformat()
    for item in discovery.get("items") or []:
        if not item.get("published_iso") or item["published_iso"] < start or not item.get("class"):
            continue
        row = _feed_row(item, by_id, summaries, last)
        when = (row["event_date"] or {}).get("date")
        if when and when > today.isoformat():
            groups["upcoming"].append(row)
        elif item["published_iso"] == today.isoformat():
            groups["today"].append(row)
        else:
            groups["recent"].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: row["item"]["published_iso"], reverse=True)
    return groups


def _feed_row(item: dict, by_id: dict, summaries: dict, last: dict) -> dict:
    """One feed row: the item, its event (a hand-made event when one covers it) and its status."""
    summary = summaries.get(item.get("event_id")) or {}
    event_id = summary.get("covered_by") or item.get("event_id")
    event = by_id.get(event_id)
    entry = last.get(event_id) or {}
    row = {"item": item, "event_id": event_id, "event": event, "summary": summary, "reason": "",
           "event_date": event_date(event["out"]["people"]) if event and event["processed"] else None}
    ranked = (event or {}).get("out", {}).get("ranked") or {}
    if not item.get("supported") or not event_id:
        status = "unsupported"
        row["reason"] = item.get("label") or "other"
    elif event and event["processed"] and not (ranked.get("callable") or ranked.get("entities")):
        status = "failed"
        row["reason"] = entry.get("reason") or "processed, but no holder was found in the documents"
    elif event and event["processed"] and not ranked.get("callable"):
        status = "empty"
        row["reason"] = f"{len(ranked.get('entities') or [])} holders found, all entities; open the event to see them"
    elif event and event["processed"]:
        status = "ready"
        row["reason"] = f"{len(ranked['callable'])} to call"
    elif entry.get("status") == "failed":
        status = "failed"
        row["reason"] = entry.get("reason") or "no reason recorded"
    else:
        status = "waiting"
        row["reason"] = summary.get("missing") or ("" if summary.get("file") else summary.get("status", ""))
    row["status"], row["status_label"] = status, FEED_STATUS[status]
    row["processable"] = bool(summary.get("processable")) and bool(event) and status in ("waiting", "failed")
    return row


def feed_header(discovery: dict | None, events: list[dict]) -> dict:
    """Sources by status, last refresh time, and how many items, events and call lists there are."""
    if not discovery:
        return {"refreshed_at": None, "ok": [], "problems": [], "disabled": [], "items": 0, "events": 0,
                "call_lists": 0}
    sources = discovery.get("sources") or []
    found_ids = {summary["event_id"] for summary in discovery.get("events") or [] if summary.get("file")}
    return {
        "refreshed_at": discovery.get("refreshed_at"),
        "ok": [source for source in sources if source["status"] == "ok"],
        "problems": [source for source in sources if source["status"] in ("failed", "blocked")],
        "disabled": [source for source in sources if source["status"] == "disabled"],
        "items": len(discovery.get("items") or []),
        "events": len(discovery.get("events") or []),
        "call_lists": sum(1 for event in events if event.get("auto") and event["processed"]
                          and event["spec"].event_id in found_ids),
    }


def check_lines(report: dict | None) -> list[tuple[str, str]]:
    """`run.py --step check` as (level, words) lines: pass, warning or fail. No model call was made."""
    if not report:
        return [("fail", "the check did not run")]
    lines: list[tuple[str, str]] = []
    for document in report.get("documents") or []:
        name = f"{document.get('doc_type')}: {str(document.get('url', '')).rsplit('/', 1)[-1][:60]}"
        if document.get("fetched") != "yes":
            lines.append(("fail", f"{name} could not be fetched ({document.get('fetched')})"))
            continue
        pages, low = document.get("pages") or 0, document.get("low_text_pages") or []
        lines.append(("pass", f"{name}: {pages} pages read"))
        if pages and len(low) > pages / 5:
            lines.append(("warning", f"{name}: {len(low)} pages have almost no text (scanned?); values there are missed"))
        if document.get("read_whole"):
            lines.append(("pass", f"{name}: read whole ({document['read_whole']})"))
        for section, where in (document.get("sections_found") or {}).items():
            lines.append(("pass", f"{name}: {section.replace('_', ' ')} found ({where})"))
        for section in document.get("sections_missing") or []:
            lines.append(("warning", f"{name}: {section.replace('_', ' ')} not found; its values will be unknown"))
    return lines or [("fail", "no documents were checked")]
