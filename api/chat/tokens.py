"""Confirm tokens: an HMAC-signed promise that this user approved this exact action at this estimate.

Payload: user email, action kind, target, estimate high end (USD), expiry (10 minutes), a nonce. Signed with the
session secret plus a chat-only label, so a session cookie can never pass as a confirm token or the reverse.
A token runs once: its nonce is remembered after use (in this process).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from api import auth
from config.chat import CONFIRM_LIMIT_USD, CONFIRM_TTL_SECONDS

_USED: set[str] = set()
_LOCK = threading.Lock()


class TokenError(Exception):
    """The token is missing, forged, expired, for someone else, or used already (shown to the RM as is)."""


def _key() -> bytes:
    """The signing key: the session secret, domain-separated for confirm tokens."""
    return hashlib.sha256(auth._secret() + b"|chat-confirm-v1").digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(email: str, kind: str, target: str, cost_high_usd: float, now: float | None = None,
         cost_low_usd: float = 0.0) -> tuple[str, int]:
    """(token, expires_at unix seconds) for one action."""
    expires = int((now if now is not None else time.time()) + CONFIRM_TTL_SECONDS)
    payload = {"u": email, "k": kind, "t": target, "hi": round(float(cost_high_usd), 6),
               "lo": round(float(cost_low_usd), 6), "exp": expires, "n": secrets.token_hex(8)}
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    mac = _b64(hmac.new(_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{mac}", expires


def read(token: str | None, email: str, now: float | None = None) -> dict:
    """The payload of a valid token for this user; raises TokenError otherwise. Does not mark it used."""
    if not token or token.count(".") != 1:
        raise TokenError("This confirmation is not valid. Ask again to get a fresh estimate.")
    body, mac = token.split(".")
    expected = _b64(hmac.new(_key(), body.encode("ascii", "ignore"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, mac):
        raise TokenError("This confirmation is not valid. Ask again to get a fresh estimate.")
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        raise TokenError("This confirmation is not valid. Ask again to get a fresh estimate.")
    if payload.get("u") != email:
        raise TokenError("This confirmation belongs to another user.")
    if payload.get("exp", 0) < (now if now is not None else time.time()):
        raise TokenError("This estimate has expired (they last 10 minutes). Ask again for a fresh one.")
    if payload.get("n") in _USED:
        raise TokenError("This action has already run. Ask again to run it once more.")
    return payload


def spend(payload: dict) -> None:
    """Mark a token used, so the same confirmation cannot run twice."""
    with _LOCK:
        if payload["n"] in _USED:
            raise TokenError("This action has already run. Ask again to run it once more.")
        _USED.add(payload["n"])


def limit_for(role: str) -> float | None:
    """The most a role may approve with one confirm (None: no limit)."""
    return CONFIRM_LIMIT_USD.get(role, 0.0)


def can_confirm(role: str, cost_high_usd: float) -> tuple[bool, str | None]:
    """(allowed, reason when not) for a role and an estimate's high end."""
    cap = limit_for(role)
    if role == "viewer" or cap == 0.0:
        return False, "Your role can ask questions that cost nothing; an RM or admin can run this."
    if cap is not None and cost_high_usd > cap:
        return False, f"This could cost more than your approval limit of ${cap:.2f}; an admin can run it."
    return True, None
