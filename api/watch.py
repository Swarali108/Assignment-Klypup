"""Watchlists and in-app alerts.

A user follows a person (by normalised name, so every event they appear in counts) or a company. Alerts are worked
out from the current data whenever the bell asks (GET /api/alerts), and kept in alert_log so "read" sticks:
  new      a followed name (or company) is in an event that was processed after the follow, other than the one it was
           followed from
  lockin   a lock-in ends within LOCKIN_DAYS (people: their shares; companies: any holder of that company's events)
  block    a block deal or an insider sale names them (event types block_deal / insider_sale; those types may arrive
           from another branch, so nothing here depends on them existing)
  amount   a followed amount changed since the last time it was looked at (after a re-run)
The ids are deterministic, so the same fact never alerts twice.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from api import db, store, views
from api.chat import tools

LOCKIN_DAYS = 30
BLOCK_TYPES = ("block_deal", "insider_sale", "insider_trade")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def company_key(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (company or "").lower()).replace(" limited", "").replace(" ltd", "").strip()


def name_key(name: str) -> str:
    return "|".join(tools._tokens(name))


def follows(email: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM follows WHERE user_email = %s ORDER BY created_at DESC", (email,))
    return [{"kind": r["kind"], "key": r["key"], "label": r["label"], "origin_event_id": r["origin_event_id"],
             "created_at": r["created_at"]} for r in rows]


def status(email: str, kind: str, event_id: str, person_id: str | None) -> dict:
    """{key, label, following} for one person or company page (the key is how the server names it)."""
    if kind == "person":
        who = tools.find_person(event_id, person_id or "")
        key, label = (name_key(who["name"]), who["name"]) if who else ("", "")
    else:
        event = store.find_event(event_id)
        key, label = (company_key(event["spec"].company), event["spec"].company) if event else ("", "")
    mine = {(f["kind"], f["key"]) for f in follows(email)}
    return {"key": key, "label": label, "following": bool(key) and (kind, key) in mine}


def follow(email: str, kind: str, event_id: str, person_id: str | None) -> dict:
    """Follow a person (event_id + person_id) or a company (event_id). ValueError when it is not found."""
    if kind == "person":
        who = tools.find_person(event_id, person_id or "")
        if not who:
            raise ValueError("That person is not in the call lists")
        key, label = name_key(who["name"]), who["name"]
    elif kind == "company":
        event = store.find_event(event_id)
        if not event:
            raise ValueError("No such event")
        key, label = company_key(event["spec"].company), event["spec"].company
    else:
        raise ValueError("kind must be person or company")
    snapshot = _snapshot(kind, key, _context())
    with db.connect() as conn:
        conn.execute("""INSERT INTO follows (user_email, kind, key, label, origin_event_id, created_at, snapshot)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (user_email, kind, key) DO NOTHING""",
                     (email, kind, key, label, event_id, _now(), json.dumps(snapshot)))
    return {"kind": kind, "key": key, "label": label}


def unfollow(email: str, kind: str, key: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM follows WHERE user_email = %s AND kind = %s AND key = %s", (email, kind, key))
        conn.execute("DELETE FROM alert_log WHERE user_email = %s AND follow_key = %s", (email, f"{kind}:{key}"))


# ---------- the data the alerts read ----------

def _context() -> dict:
    """Appearances of every holder, and the processed events with when their data was written."""
    events = [e for e in store.load_events() if e["processed"]]
    stamps = {}
    for e in events:
        try:
            stamps[e["spec"].event_id] = datetime.fromtimestamp(
                (store.OUTPUTS_DIR / e["spec"].event_id / "people.json").stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except OSError:
            stamps[e["spec"].event_id] = ""
    return {"events": events, "appearances": tools.appearances(), "stamps": stamps}


def _matches(kind: str, key: str, ctx: dict) -> list[dict]:
    if kind == "person":
        wanted = tuple(key.split("|"))
        return [a for a in ctx["appearances"] if a["tokens"] == wanted and a["list"] != "context"]
    return [a for a in ctx["appearances"] if company_key(a["event"]["spec"].company) == key and a["list"] != "context"]


def _amount_of(kind: str, found: list[dict]) -> dict[str, float | None]:
    """event_id -> the amount watched: a person's headline amount, or a company's known total (Rs Cr)."""
    out: dict[str, float | None] = {}
    for a in found:
        eid, value = a["event"]["spec"].event_id, a["item"]["amount"]["value_cr"]
        if kind == "person":
            out[eid] = value
        elif value is not None and a["list"] == "callable":
            out[eid] = round((out.get(eid) or 0) + value, 2)
    return out


def _snapshot(kind: str, key: str, ctx: dict) -> dict:
    return {k: v for k, v in _amount_of(kind, _matches(kind, key, ctx)).items() if v is not None}


def _candidates(f: dict, ctx: dict, today) -> tuple[list[dict], dict]:
    """(alert rows, new snapshot) for one follow."""
    kind, key, label = f["kind"], f["key"], f["label"]
    found = _matches(kind, key, ctx)
    fk, rows = f"{kind}:{key}", []

    def add(aid: str, akind: str, title: str, detail: str, event_id: str, person_id: str | None = None) -> None:
        link = f"/people/{event_id}/{person_id}" if person_id else f"/events/{event_id}"
        rows.append({"id": aid, "kind": akind, "title": title, "detail": detail, "link": link, "follow_key": fk})

    seen_events: set[str] = set()
    for a in found:
        event, item = a["event"], a["item"]
        eid, spec = event["spec"].event_id, event["spec"]
        pid = item["person"]["id"]
        if eid != f["origin_event_id"] and eid not in seen_events and ctx["stamps"].get(eid, "") > f["created_at"]:
            seen_events.add(eid)
            where = f"{spec.company} {views.spec_type_label(spec).lower()}"
            add(f"new|{fk}|{eid}", "new", f"{label} is in a new event" if kind == "person" else f"New event for {label}",
                where.strip(), eid, pid if kind == "person" else None)
        timing = item["timing"]
        when = _day(timing.get("date_iso"))
        if item["tier"] != "cash_now" and when and today <= when <= today + timedelta(days=LOCKIN_DAYS):
            who = f"{label}: " if kind == "person" else f"{label}, {item['person']['name']}: "
            add(f"lockin|{fk}|{eid}|{pid}|{when.isoformat()}", "lockin", f"{who}lock-in ends {views.nice_date(when.isoformat())}",
                f"{(when - today).days} days from now, {spec.company}", eid, pid)
        if spec.event_type in BLOCK_TYPES and ctx["stamps"].get(eid, "") > f["created_at"]:
            add(f"block|{fk}|{eid}|{pid}", "block", f"{label if kind == 'person' else item['person']['name']} in a "
                f"{views.spec_type_label(spec).lower()}", spec.company, eid, pid)
    snapshot = json.loads(f.get("snapshot") or "{}")
    now = _snapshot(kind, key, ctx)
    for eid, value in now.items():
        before = snapshot.get(eid)
        if before is not None and abs(before - value) > 0.005:
            company = next((a["event"]["spec"].company for a in found if a["event"]["spec"].event_id == eid), "")
            add(f"amount|{fk}|{eid}|{value}", "amount", f"{label}: amount changed",
                f"{views.cr_text(views.dec(before))} to {views.cr_text(views.dec(value))} after a re-run, {company}", eid)
    return rows, {**snapshot, **now}


def _day(iso: str | None):
    try:
        return datetime.strptime((iso or "")[:10], "%Y-%m-%d").date() if iso else None
    except ValueError:
        return None


def sync(email: str) -> None:
    """Work out the alerts from the current data and store the new ones."""
    mine = follows(email)
    if not mine:
        return
    ctx, today = _context(), views.as_of()
    with db.connect() as conn:
        raw = {(r["kind"], r["key"]): r["snapshot"] for r in conn.query(
            "SELECT kind, key, snapshot FROM follows WHERE user_email = %s", (email,))}
        for f in mine:
            f["snapshot"] = raw.get((f["kind"], f["key"]), "{}")
            rows, snapshot = _candidates(f, ctx, today)
            for r in rows:
                conn.execute("""INSERT INTO alert_log (id, user_email, kind, title, detail, link, follow_key, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (user_email, id) DO NOTHING""",
                             (r["id"], email, r["kind"], r["title"], r["detail"], r["link"], r["follow_key"], _now()))
            conn.execute("UPDATE follows SET snapshot = %s WHERE user_email = %s AND kind = %s AND key = %s",
                         (json.dumps(snapshot), email, f["kind"], f["key"]))


def alerts(email: str, limit: int = 60) -> dict:
    """{unread, items: [{id, kind, title, detail, link, created_at, read}]} newest first."""
    sync(email)
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM alert_log WHERE user_email = %s ORDER BY created_at DESC, id LIMIT %s",
                          (email, limit))
    items = [{"id": r["id"], "kind": r["kind"], "title": r["title"], "detail": r["detail"], "link": r["link"],
              "created_at": r["created_at"], "read": bool(r["read_at"])} for r in rows]
    return {"unread": sum(1 for i in items if not i["read"]), "items": items}


def mark_read(email: str, ids: list[str] | None) -> int:
    """Mark these alerts (or all, with None) read; returns how many changed."""
    with db.connect() as conn:
        if ids is None:
            before = conn.query("SELECT id FROM alert_log WHERE user_email = %s AND read_at IS NULL", (email,))
            conn.execute("UPDATE alert_log SET read_at = %s WHERE user_email = %s AND read_at IS NULL", (_now(), email))
            return len(before)
        for one in ids[:200]:
            conn.execute("UPDATE alert_log SET read_at = %s WHERE user_email = %s AND id = %s AND read_at IS NULL",
                         (_now(), email, one))
    return len(ids)
