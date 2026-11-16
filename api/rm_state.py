"""RM call status, notes and follow-up dates, stored through api/db.py (Postgres when DATABASE_URL is set, else SQLite).

One row per (event_id, person_id).
"""

from __future__ import annotations

from datetime import datetime, timezone

from api import db

STATUSES = ("to_call", "called", "follow_up", "meeting_booked", "won", "not_now", "not_a_fit")


def _row(row: dict | None, event_id: str, person_id: str) -> dict:
    """A stored row, or the default 'to call' state."""
    if row is None:
        return {"event_id": event_id, "person_id": person_id, "status": "to_call", "note": "",
                "follow_up_date": None, "updated_at": None, "updated_by": "", "first_called_at": None,
                "won_amount_cr": None}
    return dict(row)


def get(event_id: str, person_id: str) -> dict:
    """One person's state."""
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM rm_state WHERE event_id = %s AND person_id = %s", (event_id, person_id))
    return _row(rows[0] if rows else None, event_id, person_id)


def put(event_id: str, person_id: str, status: str | None, note: str | None, follow_up_date: str | None,
        updated_by: str = "", won_amount_cr: float | None = None) -> dict:
    """Upsert; fields left as None keep their stored value. A won deal carries the amount (Rs Cr) the RM entered;
    the first time the status leaves "to_call" the moment is kept (time from the event to the first call);
    it is cleared again when the status goes back to "to_call"."""
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    if won_amount_cr is not None and (won_amount_cr < 0 or won_amount_cr > 1_000_000):
        raise ValueError("the won amount must be a number of crore, zero or more")
    current = get(event_id, person_id)
    merged = {"status": status if status is not None else current["status"],
              "note": note if note is not None else current["note"],
              "follow_up_date": follow_up_date if follow_up_date is not None else current["follow_up_date"]}
    if merged["follow_up_date"] == "":
        merged["follow_up_date"] = None
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Putting a person back to "to call" undoes the first call, so the team dashboard does not count it.
    first = None if merged["status"] == "to_call" else (current.get("first_called_at") or stamp)
    won = won_amount_cr if won_amount_cr is not None else (current.get("won_amount_cr") if merged["status"] == "won" else None)
    by = updated_by or current.get("updated_by") or ""
    with db.connect() as conn:
        conn.execute("""INSERT INTO rm_state (event_id, person_id, status, note, follow_up_date, updated_at, updated_by,
                        first_called_at, won_amount_cr) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (event_id, person_id) DO UPDATE SET status = excluded.status, note = excluded.note,
                        follow_up_date = excluded.follow_up_date, updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by, first_called_at = excluded.first_called_at,
                        won_amount_cr = excluded.won_amount_cr""",
                     (event_id, person_id, merged["status"], merged["note"], merged["follow_up_date"], stamp, by,
                      first, won))
    return get(event_id, person_id)


def all_states() -> dict[tuple[str, str], dict]:
    """(event_id, person_id) -> state, for every stored row."""
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM rm_state")
    return {(row["event_id"], row["person_id"]): row for row in rows}
