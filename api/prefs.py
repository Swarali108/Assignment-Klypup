"""Per-RM preferences and client book: the setup guide's storage, plus the "In your book" flag on people rows.

Routes (all need a session; any role may set its own preferences):
  GET  /api/me              who is signed in + their preferences (onboarded, coverage, alerts, book_count)
  GET  /api/me/preferences  {onboarded, event_types, min_ticket_cr, alerts, book_count}
  PUT  /api/me/preferences  same shape, partial ok
  POST /api/me/book         {names: [str]} (parsed from a CSV in the browser, at most 5,000) -> {book_count}
  DELETE /api/me/book       clears the book -> {book_count: 0}

Rows are keyed on the signed-in email (the session cookie carries no user id). A user with no stored row is
not onboarded yet, except the seeded demo accounts that predate the guide (they start onboarded, so a demo of
Today is never interrupted). install(app) adds the router and a tiny ASGI middleware that remembers who is asking,
so views.call_item can mark people already in that RM's book without passing the request around.
"""

from __future__ import annotations

import contextvars
import json
import re
import threading
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import auth, db

TABLES = (
    """CREATE TABLE IF NOT EXISTS user_prefs (
        email TEXT PRIMARY KEY, onboarded INTEGER NOT NULL DEFAULT 0, event_types TEXT NOT NULL DEFAULT '[]',
        min_ticket_cr REAL, alerts TEXT NOT NULL DEFAULT 'daily', updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS user_book (
        email TEXT NOT NULL, name_key TEXT NOT NULL, name TEXT NOT NULL, added_at TEXT NOT NULL,
        PRIMARY KEY (email, name_key))""",
)
# Demo accounts that existed before the guide: treated as already set up when they have no row yet.
PRE_ONBOARDED = {"admin@aurelia.demo", "rm@aurelia.demo", "viewer@aurelia.demo"}
ALERTS = ("daily", "weekly", "off")
MAX_BOOK = 5000

_tables_ready: set[str] = set()
_lock = threading.Lock()
_books: dict[str, frozenset[str]] = {}  # email -> normalised names (cleared on every book write)
_asker: contextvars.ContextVar[str | None] = contextvars.ContextVar("aurelia_asker", default=None)

_TITLES = re.compile(r"^(mr|mrs|ms|miss|dr|shri|smt|sri|prof|late)\.?\s+", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def name_key(name: str | None) -> str:
    """A name folded for matching: accents and punctuation dropped, titles removed, case and spaces folded.

    "Dr. Dharminder Kumar Nagar" and "DHARMINDER  KUMAR NAGAR" give the same key.
    """
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    previous = None
    while previous != text:
        previous, text = text, _TITLES.sub("", text)
    return text


def _ensure() -> None:
    """Create this module's tables once per database (CREATE TABLE IF NOT EXISTS, safe to repeat)."""
    key = db._key()
    if key in _tables_ready:
        return
    with _lock:
        if key in _tables_ready:
            return
        with db.connect() as conn:
            for statement in TABLES:
                conn.execute(statement)
        _tables_ready.add(key)


def _book_count(conn: db.Conn, email: str) -> int:
    rows = conn.query("SELECT COUNT(*) AS n FROM user_book WHERE email = %s", (email,))
    return int(rows[0]["n"]) if rows else 0


def get_preferences(email: str) -> dict:
    """The stored preferences for one email, with defaults."""
    _ensure()
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM user_prefs WHERE email = %s", (email,))
        count = _book_count(conn, email)
    row = rows[0] if rows else None
    if row is None:
        return {"onboarded": email in PRE_ONBOARDED, "event_types": [], "min_ticket_cr": None, "alerts": "daily",
                "book_count": count}
    try:
        types = [str(t) for t in json.loads(row["event_types"] or "[]")]
    except (ValueError, TypeError):
        types = []
    return {"onboarded": bool(row["onboarded"]), "event_types": types,
            "min_ticket_cr": float(row["min_ticket_cr"]) if row["min_ticket_cr"] is not None else None,
            "alerts": row["alerts"] if row["alerts"] in ALERTS else "daily", "book_count": count}


def save_preferences(email: str, patch: dict) -> dict:
    """Merge a partial update into the stored preferences and return the result."""
    current = get_preferences(email)
    merged = {**current, **{k: v for k, v in patch.items() if k in ("onboarded", "event_types", "min_ticket_cr", "alerts")}}
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO user_prefs (email, onboarded, event_types, min_ticket_cr, alerts, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (email) DO UPDATE SET onboarded = excluded.onboarded, "
            "event_types = excluded.event_types, min_ticket_cr = excluded.min_ticket_cr, alerts = excluded.alerts, "
            "updated_at = excluded.updated_at",
            (email, 1 if merged["onboarded"] else 0, json.dumps(list(merged["event_types"] or [])),
             merged["min_ticket_cr"], merged["alerts"], _now()))
    return get_preferences(email)


def save_book(email: str, names: list[str]) -> int:
    """Replace the RM's book with these names (deduplicated by normalised name); returns the stored count."""
    _ensure()
    seen: dict[str, str] = {}
    for raw in names:
        clean = re.sub(r"\s+", " ", str(raw or "")).strip()[:200]
        key = name_key(clean)
        if key and key not in seen:
            seen[key] = clean
    stamp = _now()
    with db.connect() as conn:
        conn.execute("DELETE FROM user_book WHERE email = %s", (email,))
        for key, clean in seen.items():
            conn.execute("INSERT INTO user_book (email, name_key, name, added_at) VALUES (%s, %s, %s, %s) "
                         "ON CONFLICT (email, name_key) DO NOTHING", (email, key, clean, stamp))
        count = _book_count(conn, email)
    _books.pop(email, None)
    return count


def clear_book(email: str) -> None:
    """Forget every name in the RM's book."""
    _ensure()
    with db.connect() as conn:
        conn.execute("DELETE FROM user_book WHERE email = %s", (email,))
    _books.pop(email, None)


def _book(email: str) -> frozenset[str]:
    """The normalised names in one RM's book (cached until the book changes)."""
    cached = _books.get(email)
    if cached is not None:
        return cached
    _ensure()
    with db.connect() as conn:
        keys = frozenset(r["name_key"] for r in conn.query("SELECT name_key FROM user_book WHERE email = %s", (email,)))
    _books[email] = keys
    return keys


def in_book(name: str | None) -> bool:
    """True when the person asking has this name in their client book (False with no session or no book)."""
    email = _asker.get()
    if not email or not name:
        return False
    try:
        book = _book(email)
    except Exception:  # the flag is a nicety: never fail a page over it
        return False
    return bool(book) and name_key(name) in book


# ---------- HTTP ----------

class PrefsIn(BaseModel):
    """PUT /api/me/preferences body (every field optional)."""

    onboarded: bool | None = None
    event_types: list[str] | None = Field(default=None, max_length=20)
    min_ticket_cr: float | None = Field(default=None, ge=0, le=1_000_000)
    alerts: Literal["daily", "weekly", "off"] | None = None


class BookIn(BaseModel):
    """POST /api/me/book body."""

    names: list[str]


router = APIRouter()


@router.get("/api/me")
def me_with_preferences(user: dict = auth.VIEW_USER) -> dict:
    """Who is signed in, what they may do, and their setup state."""
    return {"email": user["email"], "name": user["name"], "role": user["role"],
            "permissions": auth.permissions_for(user["role"]), **get_preferences(user["email"])}


@router.get("/api/me/preferences")
def read_preferences(user: dict = auth.VIEW_USER) -> dict:
    """The signed-in RM's preferences."""
    return get_preferences(user["email"])


@router.put("/api/me/preferences")
def write_preferences(body: PrefsIn, user: dict = auth.VIEW_USER) -> dict:
    """Update the signed-in RM's preferences (fields left out stay as they are)."""
    patch = body.model_dump(exclude_unset=True)
    if "event_types" in patch and patch["event_types"] is not None:
        patch["event_types"] = [t.strip()[:40] for t in patch["event_types"] if t and t.strip()]
    return save_preferences(user["email"], patch)


@router.post("/api/me/book")
def upload_book(body: BookIn, user: dict = auth.VIEW_USER) -> dict:
    """Replace the signed-in RM's client book with these names."""
    if len(body.names) > MAX_BOOK:
        raise HTTPException(413, f"Up to {MAX_BOOK:,} names at a time, please")
    return {"book_count": save_book(user["email"], body.names)}


@router.delete("/api/me/book")
def delete_book(user: dict = auth.VIEW_USER) -> dict:
    """Clear the signed-in RM's client book."""
    clear_book(user["email"])
    return {"book_count": 0}


class _Asker:
    """Pure ASGI middleware: remember the signed-in email for this request (read by in_book)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cookie = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"cookie"), "")
        value = next((part.split("=", 1)[1] for part in (p.strip() for p in cookie.split(";"))
                      if part.startswith(f"{auth.COOKIE}=")), None)
        user = auth.read_session(value)
        token = _asker.set(user["email"] if user else None)
        try:
            await self.app(scope, receive, send)
        finally:
            _asker.reset(token)


def install(app) -> None:
    """Add the /api/me routes and the asker middleware to the app (one line in api/main.py)."""
    app.include_router(router)
    app.add_middleware(_Asker)
