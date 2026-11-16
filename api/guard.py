"""CSRF defence for every write: a page on another site must not be able to make this API spend money.

Rule for POST/PUT/PATCH/DELETE: the body must be application/json (a browser sends that cross-site only
after a preflight, which this API does not allow) and, when the request carries an Origin header, that
Origin must be the web app. The allowed origins come from ALLOWED_ORIGINS (comma separated, e.g.
"https://aurelia.example.com,https://aurelia.vercel.app"); unset, they are the local web app
(http://localhost:3000 and http://127.0.0.1:3000). AURELIA_ORIGINS (the older name) is added on top.
"""

from __future__ import annotations

import json
import os

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DEFAULT_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def _origin_list(value: str | None) -> list[str]:
    """'a, b/ ,' -> ['a', 'b'] (trimmed, trailing slashes dropped, lower-cased)."""
    return [o.strip().rstrip("/").lower() for o in (value or "").split(",") if o.strip()]


def allowed_origins() -> set[str]:
    """The origins that may write: ALLOWED_ORIGINS when set (else the local web app), plus AURELIA_ORIGINS."""
    configured = _origin_list(os.environ.get("ALLOWED_ORIGINS"))
    return {*(configured or DEFAULT_ORIGINS), *_origin_list(os.environ.get("AURELIA_ORIGINS"))}


def refusal(headers: dict[str, str], method: str) -> tuple[int, str] | None:
    """(status, plain reason) when a write must be refused, else None."""
    if method not in WRITE_METHODS:
        return None
    origin = headers.get("origin")
    if origin is not None and origin.strip().rstrip("/").lower() not in allowed_origins():
        return 403, "Requests from this site are not allowed"
    if not headers.get("content-type", "").lower().startswith("application/json"):
        return 415, "Send JSON (Content-Type: application/json)"
    return None


class WriteGuard:
    """Pure ASGI middleware applying refusal() before any route (and any session check) runs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            verdict = refusal(headers, scope["method"])
            if verdict:
                body = json.dumps({"detail": verdict[1]}).encode()
                await send({"type": "http.response.start", "status": verdict[0],
                            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
