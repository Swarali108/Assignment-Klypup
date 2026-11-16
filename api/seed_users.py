"""Demo accounts. Seeded on API start (and by `python -m api.seed_users`); never overwrites an existing user."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from api import auth, db

DEMO_PASSWORD = "demo1234"
# (email, name, role, onboarded). The new RM has not seen the setup guide yet, so the web app shows it.
DEMO_USERS = (
    ("admin@aurelia.demo", "Asha Menon", "admin", True),
    ("rm@aurelia.demo", "Rohan Kapoor", "rm", True),
    ("viewer@aurelia.demo", "Vikram Shah", "viewer", True),
    ("new.rm@aurelia.demo", "Neha Iyer", "rm", False),
    ("head@aurelia.demo", "Meera Joshi", "head", True),
)


def seed_admin() -> int:
    """Production: make the first admin from ADMIN_EMAIL + ADMIN_PASSWORD (never overwrites an existing user).

    Returns 1 when it was created, else 0. Unset variables seed nobody; the API still starts, and the log says why.
    """
    email = _admin_email()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    if not email or not password:
        logging.getLogger("aurelia").warning("APP_ENV=production: ADMIN_EMAIL and ADMIN_PASSWORD are not both set, no admin was created")
        return 0
    with db.connect() as conn:
        if conn.query("SELECT id FROM users WHERE email = %s", (email,)):
            return 0
        conn.execute(
            "INSERT INTO users (id, email, name, role, password_hash, created_at, onboarded) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (email) DO NOTHING",
            (uuid.uuid4().hex, email, (os.environ.get("ADMIN_NAME") or "Administrator").strip(), "admin",
             auth.hash_password(password), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), 0))
    return 1


def demo_users() -> tuple[tuple[str, str, str, bool], ...]:
    """The demo accounts this deployment offers (their password is public: demo1234).

    Local: all of them. Production: none, unless DEMO_ACCOUNTS=1, and then never the admin one,
    because an admin can spend without limit.
    """
    if not auth.is_production():
        return DEMO_USERS
    if (os.environ.get("DEMO_ACCOUNTS") or "").strip().lower() not in ("1", "true", "yes", "on"):
        return ()
    return tuple(user for user in DEMO_USERS if user[2] != "admin")


def is_blocked_demo(email: str) -> bool:
    """True for a demo email this deployment does not offer (it may still be in the database from an earlier setting)."""
    email = email.strip().lower()
    offered = {user[0] for user in demo_users()}
    return email in {user[0] for user in DEMO_USERS} and email not in offered and email != _admin_email()


def _admin_email() -> str:
    """ADMIN_EMAIL, lower-cased ('' when unset). In production it may reuse a demo address with its own password."""
    return (os.environ.get("ADMIN_EMAIL") or "").strip().lower() if auth.is_production() else ""


def seed() -> int:
    """Insert the demo users that are missing; returns how many were added (0 on a repeat).

    Production also makes the admin from ADMIN_EMAIL + ADMIN_PASSWORD (see seed_admin).
    """
    added = seed_admin() if auth.is_production() else 0
    with db.connect() as conn:
        for email, name, role, onboarded in demo_users():
            if conn.query("SELECT id FROM users WHERE email = %s", (email,)):
                continue
            conn.execute(
                "INSERT INTO users (id, email, name, role, password_hash, created_at, onboarded) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (email) DO NOTHING",
                (uuid.uuid4().hex, email, name, role, auth.hash_password(DEMO_PASSWORD),
                 datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), 1 if onboarded else 0))
            added += 1
    return added


def find_user(email: str) -> dict | None:
    """The stored user row for an email (case-insensitive), or None."""
    with db.connect() as conn:
        rows = conn.query("SELECT * FROM users WHERE email = %s", (email.strip().lower(),))
    return rows[0] if rows else None


def set_onboarded(email: str, onboarded: bool = True) -> None:
    """Mark a user as having finished (or not) the first-sign-in setup guide."""
    with db.connect() as conn:
        conn.execute("UPDATE users SET onboarded = %s WHERE email = %s", (1 if onboarded else 0, email.strip().lower()))


_seeded: set[str] = set()


def seed_once() -> None:
    """seed() the first time this process uses this database (a fresh database is never left without users)."""
    key = db._key()
    if key not in _seeded:
        seed()
        _seeded.add(key)


if __name__ == "__main__":
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    print(f"Users added: {seed()}")
