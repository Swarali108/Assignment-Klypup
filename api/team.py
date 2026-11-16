"""Head of RMs: who is assigned to which RM, and the outcomes per RM and per event type (from rm_state).

Counts (one person-row in one event is one lead):
  calls      status is anything but "to_call" (the RM logged a call outcome)
  meetings   status "meeting_booked" or "won"
  won        status "won"; won_cr is the amount the RM entered (Rs Cr), never computed
  followups  status "follow_up" with a follow-up date on or before today (due or overdue)
  days_to_first_call  days from the event's money date to the day the first call was logged (median)
A lead belongs to the RM it is assigned to, else to whoever logged its outcome.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timezone

from api import db, views


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rms() -> list[dict]:
    """Users who can take leads: [{email, name, role}] (RMs first, then heads)."""
    with db.connect() as conn:
        rows = conn.query("SELECT email, name, role FROM users WHERE role IN ('rm', 'head', 'admin') ORDER BY name")
    order = {"rm": 0, "head": 1, "admin": 2}
    return sorted(rows, key=lambda r: (order.get(r["role"], 9), r["name"]))


def assignments() -> dict[str, dict]:
    """'event_id/person_id' -> {rm_email, rm_name, assigned_by, assigned_at}."""
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM assignments")
        names = {u["email"]: u["name"] for u in conn.query("SELECT email, name FROM users")}
    return {f"{r['event_id']}/{r['person_id']}": {"rm_email": r["rm_email"], "rm_name": names.get(r["rm_email"], r["rm_email"]),
                                                  "assigned_by": r["assigned_by"], "assigned_at": r["assigned_at"]}
            for r in rows}


def assign(event_id: str, person_id: str, rm_email: str | None, by: str) -> dict | None:
    """Assign (or clear with None) one person to an RM. ValueError when the email is not a user."""
    with db.connect() as conn:
        if rm_email is None or rm_email == "":
            conn.execute("DELETE FROM assignments WHERE event_id = %s AND person_id = %s", (event_id, person_id))
            return None
        if not conn.query("SELECT id FROM users WHERE email = %s AND role IN ('rm', 'head', 'admin')", (rm_email,)):
            raise ValueError("That person is not an RM")
        conn.execute("""INSERT INTO assignments (event_id, person_id, rm_email, assigned_by, assigned_at)
                        VALUES (%s, %s, %s, %s, %s) ON CONFLICT (event_id, person_id) DO UPDATE SET
                        rm_email = excluded.rm_email, assigned_by = excluded.assigned_by,
                        assigned_at = excluded.assigned_at""", (event_id, person_id, rm_email, by, _now()))
    return assignments().get(f"{event_id}/{person_id}")


def _day(iso: str | None) -> date | None:
    try:
        return datetime.strptime((iso or "")[:10], "%Y-%m-%d").date() if iso else None
    except ValueError:
        return None


def _blank() -> dict:
    return {"assigned": 0, "calls": 0, "meetings": 0, "won": 0, "won_cr": 0.0, "followups_due": 0, "_days": []}


def _finish(bucket: dict) -> dict:
    days = bucket.pop("_days")
    bucket["won_cr"] = round(bucket["won_cr"], 2)
    bucket["days_to_first_call"] = round(statistics.median(days), 1) if days else None
    bucket["days_samples"] = len(days)
    return bucket


def dashboard(events: list[dict], rm_lookup: dict) -> dict:
    """The Head of RMs view: per RM, per event type, and a total, from stored rm_state rows and assignments."""
    people = {u["email"]: u for u in rms()}
    assigned = assignments()
    today = views.as_of()
    types = {e["spec"].event_id: e["spec"].event_type for e in events}
    dates = {e["spec"].event_id: (_day(e["spec"].event_date) or _day(views.money_date(e)["date_iso"])) for e in events}
    per_rm: dict[str, dict] = {}
    per_type: dict[str, dict] = {}
    total = _blank()
    for key, info in assigned.items():
        per_rm.setdefault(info["rm_email"], _blank())["assigned"] += 1
        total["assigned"] += 1
        per_type.setdefault(types.get(key.split("/", 1)[0], "other"), _blank())["assigned"] += 1
    for (event_id, person_id), row in rm_lookup.items():
        status = row.get("status") or "to_call"
        if status == "to_call" or event_id not in types:
            continue
        owner = (assigned.get(f"{event_id}/{person_id}") or {}).get("rm_email") or row.get("updated_by") or "unknown"
        buckets = [per_rm.setdefault(owner, _blank()), per_type.setdefault(types[event_id], _blank()), total]
        called = _day(row.get("first_called_at"))
        for b in buckets:
            b["calls"] += 1
            if status in ("meeting_booked", "won"):
                b["meetings"] += 1
            if status == "won":
                b["won"] += 1
                b["won_cr"] += float(row.get("won_amount_cr") or 0)
            due = _day(row.get("follow_up_date"))
            if status == "follow_up" and due and due <= today:
                b["followups_due"] += 1
            if called and dates.get(event_id):
                b["_days"].append(max((called - dates[event_id]).days, 0))
    rows = []
    for email, bucket in per_rm.items():
        user = people.get(email) or {}
        rows.append({"email": email, "name": user.get("name") or ("Not assigned" if email == "unknown" else email),
                     "role": user.get("role"), **_finish(bucket)})
    for email, user in people.items():
        if email not in per_rm and user["role"] == "rm":
            rows.append({"email": email, "name": user["name"], "role": "rm", **_finish(_blank())})
    rows.sort(key=lambda r: (-r["won_cr"], -r["won"], -r["meetings"], -r["calls"], r["name"]))
    type_rows = [{"event_type": t, "type_label": views.type_label(t), **_finish(b)} for t, b in per_type.items()]
    type_rows.sort(key=lambda r: (-r["calls"], r["type_label"]))
    return {"as_of": today.isoformat(), "total": _finish(total), "rms": rows, "event_types": type_rows,
            "unassigned_calls": next((r["calls"] for r in rows if r["email"] == "unknown"), 0)}
