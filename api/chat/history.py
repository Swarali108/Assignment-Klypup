"""Conversations and messages, stored per user in the app database (api/db.py tables chat_*).

v2: each conversation also stores its memory (chat_conversations.state, api/chat/memory.py); each assistant
message stores its meta (models, tokens, cached tokens, cost, context size, focus). Listing can search titles
and message text (?q=).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from api import db

TITLE_CHARS = 60


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def title_for(message: str) -> str:
    """A conversation title from its first message (no model): first line, cut at a word."""
    text = " ".join((message or "").split()) or "New conversation"
    if len(text) <= TITLE_CHARS:
        return text
    return text[:TITLE_CHARS].rsplit(" ", 1)[0] + "…"


def owned(conversation_id: str, email: str) -> dict | None:
    """The conversation row when it belongs to this user, else None."""
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM chat_conversations WHERE id = %s AND user_email = %s", (conversation_id, email))
    return rows[0] if rows else None


def ensure(conversation_id: str | None, email: str, first_message: str) -> dict:
    """The user's conversation (created when the id is empty or not theirs)."""
    if conversation_id:
        found = owned(conversation_id, email)
        if found:
            return found
    row = {"id": uuid.uuid4().hex, "user_email": email, "title": title_for(first_message), "created_at": _now(),
           "updated_at": _now()}
    with db.connect() as conn:
        conn.execute("INSERT INTO chat_conversations (id, user_email, title, created_at, updated_at) "
                     "VALUES (%s, %s, %s, %s, %s)", (row["id"], email, row["title"], row["created_at"], row["updated_at"]))
    return row


def add_message(conversation_id: str, role: str, text: str, cards: list | None = None, steps: list | None = None,
                estimate: dict | None = None, extra: dict | None = None) -> None:
    """Store one message and touch the conversation."""
    payload = {"cards": cards or [], "steps": steps or [], "estimate": estimate, **(extra or {})}
    now = _now()
    with db.connect() as conn:
        conn.execute("INSERT INTO chat_messages (id, conversation_id, role, text, payload, created_at) "
                     "VALUES (%s, %s, %s, %s, %s, %s)",
                     (uuid.uuid4().hex, conversation_id, role, text or "", json.dumps(payload, ensure_ascii=False), now))
        conn.execute("UPDATE chat_conversations SET updated_at = %s WHERE id = %s", (now, conversation_id))


def list_for(email: str, q: str | None = None) -> list[dict]:
    """[{id, title, updated_at, messages, cost_usd}] newest first; q matches the title or any message's text."""
    sql = ("SELECT c.id, c.title, c.updated_at, COUNT(m.id) AS messages FROM chat_conversations c "
           "LEFT JOIN chat_messages m ON m.conversation_id = c.id WHERE c.user_email = %s")
    params: tuple = (email,)
    needle = " ".join((q or "").split()).lower()[:120]
    if needle:
        sql += (" AND (LOWER(c.title) LIKE %s OR c.id IN (SELECT conversation_id FROM chat_messages "
                "WHERE LOWER(text) LIKE %s))")
        like = "%" + needle.replace("%", "").replace("_", "") + "%"
        params = (email, like, like)
    sql += " GROUP BY c.id, c.title, c.updated_at ORDER BY c.updated_at DESC"
    with db.connect() as conn:
        rows = conn.query(sql, params)
        costs = _costs(conn, [r["id"] for r in rows])
    return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"], "messages": int(r["messages"] or 0),
             "cost_usd": costs.get(r["id"], 0.0)} for r in rows]


def _costs(conn, ids: list[str]) -> dict[str, float]:
    """Total spend per conversation, summed from each assistant message's stored done event."""
    if not ids:
        return {}
    marks = ", ".join(["%s"] * len(ids))
    rows = conn.query(f"SELECT conversation_id, payload FROM chat_messages WHERE role = 'assistant' AND "
                      f"conversation_id IN ({marks})", tuple(ids))
    totals: dict[str, float] = {}
    for row in rows:
        try:
            done = json.loads(row["payload"] or "{}").get("done") or {}
        except ValueError:
            continue
        totals[row["conversation_id"]] = round(totals.get(row["conversation_id"], 0.0)
                                               + float(done.get("total_cost_usd") or 0), 6)
    return totals


def messages(conversation_id: str) -> list[dict]:
    """The stored messages of a conversation in order (no ownership check: callers already hold the id)."""
    with db.connect() as conn:
        rows = conn.query("SELECT role, text, payload, created_at FROM chat_messages WHERE conversation_id = %s "
                          "ORDER BY created_at", (conversation_id,))
    out = []
    for row in rows:
        payload = json.loads(row["payload"] or "{}")
        out.append({"role": row["role"], "text": row["text"], "cards": payload.pop("cards", []),
                    "steps": payload.pop("steps", []), "estimate": payload.pop("estimate", None),
                    "created_at": row["created_at"], **payload})
    return out


def all_meta() -> list[dict]:
    """Every assistant message's meta across users (for /api/ops/tokens)."""
    with db.connect() as conn:
        rows = conn.query("SELECT payload FROM chat_messages WHERE role = 'assistant'")
    found = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except ValueError:
            continue
        if payload.get("meta") or payload.get("done"):
            found.append({"meta": payload.get("meta") or {}, "done": payload.get("done") or {}})
    return found


def all_states() -> list[dict]:
    """Every conversation's memory (for compression totals)."""
    with db.connect() as conn:
        rows = conn.query("SELECT state FROM chat_conversations")
    found = []
    for row in rows:
        try:
            found.append(json.loads(row.get("state") or "{}"))
        except (TypeError, ValueError):
            continue
    return found


def get(conversation_id: str, email: str) -> dict | None:
    """{id, title, messages: [{role, text, cards, steps, estimate, created_at, meta?, ...}]} or None when not theirs."""
    found = owned(conversation_id, email)
    if not found:
        return None
    return {"id": found["id"], "title": found["title"], "created_at": found.get("created_at"),
            "updated_at": found.get("updated_at"), "messages": messages(conversation_id)}


def delete(conversation_id: str, email: str) -> bool:
    """Delete a conversation of this user and its messages; False when it is not theirs."""
    if not owned(conversation_id, email):
        return False
    with db.connect() as conn:
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = %s", (conversation_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id = %s AND user_email = %s", (conversation_id, email))
    return True
