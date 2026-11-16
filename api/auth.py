"""Login, roles and the signed session cookie.

Passwords: PBKDF2-HMAC-SHA256 (stdlib). Session: an HMAC-SHA256-signed cookie (httpOnly, SameSite=Lax, 12 h)
that carries email, name, role and expiry, signed with SESSION_SECRET. Locally an unset secret is generated into
api/state/; with APP_ENV=production the API refuses to start without one (check_config). The cookie is Secure
when COOKIE_SECURE=1, never when COOKIE_SECURE=0, and otherwise when the request arrived over https.

Roles (one source of truth; /api/auth/me hands the same table to the web app):
  admin   everything: process events, add events, Trust & Ops
  head    Head of RMs: everything an RM does, plus the team dashboard, assigning people to RMs and the review queue
  rm      view, log call outcomes and notes, export, ask
  viewer  read only
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, HTTPException, Request

COOKIE = "aurelia_session"
SESSION_SECONDS = 12 * 3600
ITERATIONS = 200_000
SECRET_FILE = Path(__file__).resolve().parent / "state" / "session_secret"

ROLES = ("admin", "head", "rm", "viewer")
# permission -> roles that have it. "view" is every signed-in role.
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "view": ROLES,
    "edit_rm": ("admin", "head", "rm"),
    "export": ("admin", "head", "rm"),
    "ask": ("admin", "head", "rm"),
    "team": ("admin", "head"),
    "review": ("admin", "head"),
    "process": ("admin",),
    "ops": ("admin",),
}


def permissions_for(role: str) -> dict[str, bool]:
    """{permission: allowed} for one role."""
    return {name: role in roles for name, roles in PERMISSIONS.items()}


# ---------- passwords ----------

def hash_password(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    """'pbkdf2_sha256$<iterations>$<salt b64>$<hash b64>'."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """True when password matches a hash made by hash_password (constant-time compare)."""
    try:
        _, iterations, salt, digest = stored.split("$")
        expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(expected, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


# ---------- deployment settings ----------

MIN_SECRET_CHARS = 32


def is_production() -> bool:
    """True when APP_ENV is 'production' (or 'prod')."""
    return (os.environ.get("APP_ENV") or "").strip().lower() in ("production", "prod")


def check_config() -> None:
    """Refuse to run in production without a real SESSION_SECRET (a generated file would change on every deploy)."""
    if not is_production():
        return
    configured = (os.environ.get("SESSION_SECRET") or "").strip()
    if len(configured) < MIN_SECRET_CHARS:
        raise RuntimeError(f"APP_ENV=production needs SESSION_SECRET set to at least {MIN_SECRET_CHARS} random "
                           "characters (for example: openssl rand -hex 32)")


def cookie_secure(request: Request | None) -> bool:
    """Whether the session cookie gets the Secure flag: COOKIE_SECURE=1/0 decides; unset, https decides."""
    setting = (os.environ.get("COOKIE_SECURE") or os.environ.get("AURELIA_COOKIE_SECURE") or "").strip().lower()
    if setting in ("1", "true", "yes"):
        return True
    if setting in ("0", "false", "no"):
        return False
    if request is None:
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


# ---------- session cookie ----------

def _secret() -> bytes:
    """SESSION_SECRET, else (not in production) a random secret kept in api/state/session_secret."""
    configured = (os.environ.get("SESSION_SECRET") or "").strip()
    if configured:
        return configured.encode("utf-8")
    check_config()  # production without a secret: fail here too, never fall back to a file
    if not SECRET_FILE.is_file():
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(secrets.token_urlsafe(48))
    return SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_session(user: dict, now: float | None = None) -> str:
    """The signed cookie value for a user row."""
    payload = {"email": user["email"], "name": user["name"], "role": user["role"],
               "exp": int((now if now is not None else time.time()) + SESSION_SECONDS)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def read_session(value: str | None, now: float | None = None) -> dict | None:
    """The user dict in a cookie value, or None when it is missing, forged or expired."""
    if not value or "." not in value:
        return None
    body, _, signature = value.partition(".")
    expected = _b64(hmac.new(_secret(), body.encode("ascii", "ignore"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if payload.get("exp", 0) < (now if now is not None else time.time()) or payload.get("role") not in ROLES:
        return None
    return {"email": payload["email"], "name": payload["name"], "role": payload["role"]}


# ---------- request guards ----------

def current_user(request: Request) -> dict | None:
    """The signed-in user for this request, or None."""
    return read_session(request.cookies.get(COOKIE))


def _guard_for(permission: str):
    """The guard function for one permission: 401 without a session, 403 when the role lacks it."""
    allowed = PERMISSIONS[permission]

    def guard(request: Request) -> dict:
        user = current_user(request)
        if user is None:
            raise HTTPException(401, "Please sign in")
        if user["role"] not in allowed:
            raise HTTPException(403, "Your role cannot do this")
        return user

    return guard


def require(permission: str):
    """A FastAPI dependency for dependencies=[...]."""
    return Depends(_guard_for(permission))


VIEW = require("view")
EDIT_RM = require("edit_rm")
EXPORT = require("export")
ASK = require("ask")
PROCESS = require("process")
OPS = require("ops")
OPS_USER = Depends(_guard_for("ops"))  # the admin console handlers need the user for confirm tokens
ASK_USER = Depends(_guard_for("ask"))
EDIT_RM_USER = Depends(_guard_for("edit_rm"))
TEAM = require("team")
REVIEW = require("review")
TEAM_USER = Depends(_guard_for("team"))
REVIEW_USER = Depends(_guard_for("review"))
VIEW_USER = Depends(_guard_for("view"))  # as a parameter default when the handler needs the user
