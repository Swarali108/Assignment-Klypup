"""The chat agent's tools: plain code over api/views and api/store. None of them calls a model or spends money.

Each tool returns {"data": compact facts for the writer and the verifier, "cards": [card, ...]}. Cards carry the
same view models the screens use (api/CONTRACT.md), so every number on a card comes straight from stored data.
Spending tools (process an event, deep dive) live in api/chat/actions.py and api/chat/deep_dive.py.
"""

from __future__ import annotations

from datetime import date, timedelta

from agents.identity import different_first_names, identity_tokens
from api import ask as ask_mod
from api import jobs, rm_state, store, views
from api.chat import windows as win
from config.chat import MAX_CARD_ITEMS, NEAREST_ROWS

LIKELY = "likely the same person"
COMMON = "common name: the same name is printed in more than one filing, confirm before using"
PARTIAL = "the name only partly matches what you typed"


def context() -> tuple[list[dict], dict]:
    """(events, rm lookup) read fresh from disk."""
    return store.load_events(), rm_state.all_states()


def compact(item: dict) -> dict:
    """The facts of one call item the writer may use (all strings and numbers as stored)."""
    return {"name": item["person"]["name"], "role": item["person"]["role"], "company": item["event"]["company"],
            "event": item["event"]["type_label"], "tier": item["tier_label"], "amount": item["amount"]["display"],
            "amount_cr": item["amount"]["value_cr"], "estimate": bool(item["amount"].get("estimate")),
            "timing": (item.get("timing") or {}).get("label"), "confidence": item["confidence"]["level"],
            "why": item.get("why"), **_trade_facts(item)}


def _trade_facts(item: dict) -> dict:
    """On a row that folds one holder's repeat sales at a company: how many of those sales are in this answer and
    their known cash together. The row's own amount and timing are its newest sale's."""
    trades = item.get("trades") or []
    if len(trades) < 2:
        return {}
    facts = {"trades": len(trades), "trades_total": item.get("trades_total_display"),
             "trade_dates": [t["date_display"] for t in trades if t["date_display"]]}
    if item.get("trades_unpriced"):
        facts["trades_without_amount"] = item["trades_unpriced"]
    return facts


def _card(kind: str, title: str, items: list[dict], total: int | None = None) -> dict:
    """One card; total is how many matched before the card was cut to MAX_CARD_ITEMS."""
    return {"kind": kind, "title": title, "items": items[:MAX_CARD_ITEMS], "total": len(items) if total is None else total}


# ---------- lookups ----------

def today(limit: int = 8, window: win.Window | None = None) -> dict:
    """The cross-event call queue (households folded) and the Today headline numbers.

    With a window, only people whose money date falls inside it; when none do, the nearest dated people
    instead, in a card that says they are outside the window.
    """
    events, rm = context()
    queue = views.today_queue(events, rm)
    head = views.summary(events, rm)
    data = {"people_to_call": head["people_to_call"], "households": head["households"],
            "cash_now_people": head["cash_now_people"], "cash_now_cr": head["cash_now_cr"],
            "new_events_this_week": head["new_events_this_week"], "events_processed": head["events_processed"],
            "top": [compact(item) for item in queue[:limit]]}
    if window is None:
        return {"data": data, "cards": [_card("people", "Who to call first", queue[:limit], len(queue))]}
    # Each trade is placed in or out of the window by its own date, then a holder's trades inside it fold together.
    trades = views.today_queue(events, rm, fold_trades=False)
    return windowed(trades, window, limit, data, f"Came into money {window.words}")


def _with_days(row: dict, item: dict) -> dict:
    """A compact row plus how many days ago (or ahead) its money date is."""
    iso = win.date_of(item)
    return {**row, "money_date": views.nice_date(iso), "days_ago": win.days_from(iso) if iso else None}


def windowed(items: list[dict], window: win.Window, limit: int, data: dict, title: str) -> dict:
    """Facts and cards for people inside a window, or the nearest outside it when none are inside."""
    inside, outside = win.split(items, window)
    inside = views.fold_repeat_trades(inside)  # a holder's trades inside the window, together
    base = {k: v for k, v in data.items() if k not in ("top", "people")}
    if inside:
        rows = [_with_days(compact(i), i) for i in inside[:limit]]
        found = {**base, "window": window.as_data(), "in_window": len(inside), "count": len(inside), "top": rows,
                 "people": rows}
        return {"data": found, "cards": [_card("people", f"{title} ({window.span_text()})", inside[:limit], len(inside))]}
    near = _one_per_holder(win.nearest(outside, window, len(outside)))[:NEAREST_ROWS]
    rows = [_with_days(compact(i), i) for i in near]
    found = {**base, **win.fallback_facts(near, window), "count": 0, "nearest": rows, "top": [], "people": []}
    cards = [_card("people", f"Nearest money dates, outside {window.words}", near)] if near else []
    for card in cards:
        card["outside_window"] = window.as_data()
    return {"data": found, "cards": cards}


def _one_per_holder(rows: list[dict]) -> list[dict]:
    """Rows nearest the window first, each holder's repeat sales at a company kept once: the trade nearest it."""
    seen, out = set(), []
    for row in rows:
        key = views.repeat_trade_key(row)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(row)
    return out


def search_people(filters: dict, window: win.Window | None = None) -> dict:
    """People across processed events matching api/ask filters (validated by ask.safe_filters already)."""
    events, rm = context()
    trades = ask_mod.apply(filters, views.all_items(events, rm))
    found = views.fold_repeat_trades(trades)  # one row per holder and company; a window splits the trades first
    chips = ask_mod.chips(filters)
    data = {"filters": filters, "read_as": chips, "count": len(found), "people": [compact(i) for i in found[:MAX_CARD_ITEMS]]}
    title = " · ".join(chips) or "People"
    if window is not None:
        return windowed(trades, window, MAX_CARD_ITEMS, data, title)
    return {"data": data, "cards": [_card("people", title, found)]}


def keyword_people(question: str) -> dict:
    """People whose name, company or role contains every word of the question (the $0 fallback)."""
    events, rm = context()
    found = views.fold_repeat_trades(ask_mod.keyword(question, views.all_items(events, rm)))
    return {"data": {"searched_for": question, "count": len(found), "people": [compact(i) for i in found[:MAX_CARD_ITEMS]]},
            "cards": [_card("people", "Matching people", found)] if found else []}


def search_events(event_type: str | None = None, company: str | None = None, processed_only: bool = False) -> dict:
    """Events with status, people count and cash total, optionally of one type or company."""
    events, rm = context()
    running, failures = jobs.running_events(), views.failure_reasons()
    rows = []
    for event in events:
        if event_type and event["spec"].event_type != event_type:
            continue
        if company and company.lower() not in event["spec"].company.lower():
            continue
        if processed_only and not event["processed"]:
            continue
        rows.append(views.event_summary(event, running, failures, rm))
    rows.sort(key=lambda r: (r["status"] != "ready", -(r["cash_cr"] or 0), -r["people_count"]))
    data = {"count": len(rows), "ready_count": sum(1 for r in rows if r["status"] == "ready"), "events": [{"company": r["company"], "type": r["type_label"], "status": r["status"],
                                            "people": r["people_count"], "cash_cr": r["cash_cr"],
                                            "money_date": r["money_date"]["display"]} for r in rows[:MAX_CARD_ITEMS]]}
    title = f"{views.type_label(event_type)} events" if event_type else "Events"
    return {"data": data, "cards": [_card("events", title, rows)]}


def calendar(start: str | None = None, end: str | None = None, window: win.Window | None = None) -> dict:
    """Dated money items between two ISO dates (default: a week back to two months ahead).

    A window sets the dates; when nothing falls in it, the nearest dated rows come back marked as outside it.
    """
    if window is not None:
        start, end = window.start_iso, window.end_iso
    today_iso = views.as_of()
    start = start or (today_iso - timedelta(days=7)).isoformat()
    end = end or (today_iso + timedelta(days=60)).isoformat()
    events, rm = context()
    rows = views.calendar(events, rm, start, end)
    data = {"from": start, "to": end, "count": len(rows),
            "items": [_cal_row(r) for r in rows[:MAX_CARD_ITEMS]]}
    if window is not None:
        data.update(window=window.as_data(), in_window=len(rows))
        if not rows:
            everything = views.calendar(events, rm, None, None)
            near = win.nearest(everything, window, NEAREST_ROWS, date_key=lambda r: r["date_iso"])
            data.update(win.fallback_facts(near, window, date_key=lambda r: r["date_iso"]),
                        nearest=[{**_cal_row(r), "days_ago": win.days_from(r["date_iso"])} for r in near])
            card = _card("calendar", f"Nearest money dates, outside {window.words}", near)
            card["outside_window"] = window.as_data()
            return {"data": data, "cards": [card] if near else []}
    return {"data": data, "cards": [_card("calendar", f"Money dates, {views.nice_date(start)} to {views.nice_date(end)}", rows)]}


def _cal_row(r: dict) -> dict:
    return {"date": r["display"], "what": r["label"], "company": r["event"]["company"], "people": r["people_count"],
            "total_cr": r["total_cr"]}


def person_card(event_id: str, person_id: str) -> dict:
    """The full call card for one person in one event ({} data when not found)."""
    event = store.find_event(event_id)
    if not event or not event["processed"]:
        return {"data": {}, "cards": []}
    rm = rm_state.all_states()
    card = views.person_card(event, person_id, rm.get((event_id, person_id)), rm)
    if card is None:
        return {"data": {}, "cards": []}
    data = {**compact(card), "brief": card["brief"]["lines"], "why_now": card["why_now"]}
    return {"data": data, "cards": [_card("person", card["person"]["name"] or "Person", [card])]}


# ---------- reverse lookup ----------

def _tokens(name: str | None) -> tuple[str, ...]:
    return tuple(sorted(identity_tokens(name or "")))


def appearances() -> list[dict]:
    """Every holder in every processed event: {tokens, name, holder_type, event, item, list}."""
    events, rm = context()
    found = []
    for event in events:
        if not event["processed"]:
            continue
        people = views.people_by_id(event)
        for group, items in views.event_lists(event, rm).items():
            for item in items:
                person = people.get(item["person"]["id"]) or {}
                name = person.get("name_as_printed") or item["person"]["name"]
                found.append({"tokens": _tokens(name), "name": name, "holder_type": person.get("holder_type") or "unsure",
                              "event": event, "item": item, "list": group, "family_group": person.get("family_group")})
    return found


def reverse_lookup(name: str) -> dict:
    """Who this name is across all processed events, grouped into distinct people.

    Normalised names (agents.identity spelling rules). An exact token match beats a partial one, so typing a full
    name never pulls in a relative whose longer name contains it. Each identity carries an "unsure" flag:
    a two-word person name printed in more than one filing, or a partial match.
    """
    wanted = _tokens(name)
    if not wanted:
        return {"data": {"query": name, "identities": []}, "identities": []}
    exact, partial = {}, {}
    for entry in appearances():
        if entry["tokens"] == wanted:
            exact.setdefault(entry["tokens"], []).append(entry)
        elif set(wanted) <= set(entry["tokens"]):
            partial.setdefault(entry["tokens"], []).append(entry)
    groups = exact or partial
    identities = []
    for tokens, entries in groups.items():
        # Two entries with the same tokens but different first names (agents.identity) stay apart.
        clusters: list[list[dict]] = []
        for entry in entries:
            home = next((c for c in clusters if not different_first_names(
                {"name": c[0]["name"], "holder_type": c[0]["holder_type"]},
                {"name": entry["name"], "holder_type": entry["holder_type"]})), None)
            (home.append(entry) if home else clusters.append([entry]))
        for cluster in clusters:
            identities.append(_identity(cluster, matched="exact" if exact else "partial"))
    identities.sort(key=lambda i: (-(i["best_cr"] or 0), i["name"]))
    data = {"query": name, "match": "exact" if exact else ("partial" if partial else "none"),
            "identities": [{k: v for k, v in i.items() if k != "entries"} for i in identities]}
    return {"data": data, "identities": identities}


def _identity(entries: list[dict], matched: str) -> dict:
    """One person across events, with the unsure flag and the reason."""
    entries = sorted(entries, key=lambda e: (views.TIER_ORDER.get(e["item"]["tier"], 9), -(e["item"]["amount"]["value_cr"] or 0)))
    first = entries[0]
    person_like = first["holder_type"] in ("person", "unsure")
    events = {e["event"]["spec"].event_id for e in entries}
    reasons = []
    if matched == "partial":
        reasons.append(PARTIAL)
    if person_like and len(first["tokens"]) <= 2 and len(events) > 1:
        reasons.append(COMMON)
    known = [e["item"]["amount"]["value_cr"] for e in entries if e["item"]["amount"]["value_cr"] is not None]
    return {"name": first["name"], "holder_type": first["holder_type"], "unsure": bool(reasons),
            "unsure_reason": "; ".join(reasons) or (LIKELY if len(events) > 1 else None),
            "best_cr": max(known) if known else None, "entries": entries,
            "appearances": [{"company": e["event"]["spec"].company, "event": views.type_label(e["event"]["spec"].event_type),
                             "event_id": e["event"]["spec"].event_id, "person_id": e["item"]["person"]["id"],
                             "role": e["item"]["person"]["role"], "tier": e["item"]["tier_label"],
                             "amount": e["item"]["amount"]["display"], "amount_cr": e["item"]["amount"]["value_cr"],
                             "timing": (e["item"].get("timing") or {}).get("label"),
                             "confidence": e["item"]["confidence"]["level"], "list": e["list"]} for e in entries]}


def identity_result(identity: dict) -> dict:
    """Tool result for one resolved person: the call card of their top appearance plus every appearance."""
    top = identity["entries"][0]
    card = views.person_card(top["event"], top["item"]["person"]["id"], None, rm_state.all_states())
    match = {"unsure": identity["unsure"], "reason": identity["unsure_reason"]}
    items = []
    for entry in identity["entries"]:
        items.append({**entry["item"], "match": match, "list": entry["list"]})
    cards = []
    if card:
        cards.append(_card("person", identity["name"], [{**card, "match": match}]))
    if len(items) > 1:
        cards.append(_card("people", f"{identity['name']} in {len(items)} filings", items))
    data = {"name": identity["name"], "unsure": identity["unsure"], "unsure_reason": identity["unsure_reason"],
            "count": len(identity["appearances"]), "appearances": identity["appearances"], "brief": (card or {}).get("brief", {}).get("lines", [])}
    return {"data": data, "cards": cards}


def lock_in(identity: dict) -> list[dict]:
    """When each appearance's kept shares are free, as the call card stores it (no evidence arrays).

    One row per company and lock-in text: {company, event, status, display, note, shares, value}.
    """
    rm = rm_state.all_states()
    rows, seen = [], set()
    for entry in identity["entries"]:
        card = views.person_card(entry["event"], entry["item"]["person"]["id"], None, rm) or {}
        timing = next((t for t in card.get("timing_detail") or [] if t["key"] == "retained"), None)
        if not timing:
            continue
        kept = next((a for a in card.get("amounts") or [] if a["key"] == "retained"), {})
        company = entry["event"]["spec"].company
        if (company, timing["display"]) in seen:
            continue
        seen.add((company, timing["display"]))
        rows.append({"company": company, "event": views.type_label(entry["event"]["spec"].event_type),
                     "status": timing["status"], "display": timing["display"], "note": timing.get("note"),
                     "shares": kept.get("shares_display"), "value": kept.get("display")})
    return rows


def holder_named(text: str, word: str) -> str | None:
    """The holder whose full printed name (two or more name words, one of them `word`) is in the text, or None.

    "Why is <X Family Trust> worth a call?" names a trust; it is not a question about every trust.
    """
    typed = set(identity_tokens(text or ""))
    found = [e["name"] for e in appearances()
             if len(e["tokens"]) >= 2 and word.lower() in e["name"].lower() and set(e["tokens"]) <= typed]
    return max(found, key=lambda n: len(_tokens(n))) if found else None


def find_person(event_id: str, person_id: str) -> dict | None:
    """The identity (as reverse_lookup builds it) of one person in one event, or None."""
    event = store.find_event(event_id)
    if not event or not event["processed"]:
        return None
    person = views.people_by_id(event).get(person_id)
    if not person:
        return None
    found = reverse_lookup(person.get("name_as_printed") or "")["identities"]
    for identity in found:
        if any(e["event"]["spec"].event_id == event_id and e["item"]["person"]["id"] == person_id for e in identity["entries"]):
            return identity
    return found[0] if found else None


# ---------- small helpers for the router ----------

def companies() -> list[str]:
    """Company names of every event in the app."""
    return [event["spec"].company for event in store.load_events()]


def events_by_word(text: str) -> list[dict]:
    """Events whose company's first distinctive word (or id) appears in the text."""
    lowered = text.lower()
    found = []
    for event in store.load_events():
        spec = event["spec"]
        words = [w for w in identity_tokens(spec.company.lower()) if len(w) > 3 and w not in ("limited", "india")]
        if spec.event_id in lowered or (words and words[0] in lowered.split()):
            found.append(event)
    return found


def date_window(question: str) -> tuple[str | None, str | None]:
    """(from, to) ISO dates of the window a question names (api/chat/windows.py); else (None, None)."""
    found = win.parse(question)
    return (found.start_iso, found.end_iso) if found else (None, None)


def as_of() -> date:
    """The app's 'today'."""
    return views.as_of()
