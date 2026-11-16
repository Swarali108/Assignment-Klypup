"""Download a public URL and reuse the file until it is older than max_age_days.

The file name is sha256(url). The body is cache/fetch/<key>.bin. The sidecar is
cache/fetch/<key>.json. A refetch that changes the bytes keeps the previous
body as <key>.<first 8 of the old sha256>.bin. This file does not set cookies
or extra headers, and it does not retry a 401 or 403.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

import httpx

from tools.netguard import public_url

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "Money-event-RM-call-list/0.1 (educational; public filings)"
TIMEOUT_S = 30.0
# One try, then two retries. 401 and 403 are not retried.
RETRIES = 2
MAX_REDIRECTS = 5
REDIRECT_CODES = (301, 302, 303, 307, 308)


class FetchError(Exception):
    """A download failed. status is the HTTP code, or None when there was no response."""

    def __init__(self, url: str, status: int | None, message: str):
        self.url = url
        self.status = status
        super().__init__(message)


def fetch(url: str, max_age_days: float = 7,
          downloader: Callable[[str], httpx.Response] | None = None) -> tuple[Path, dict]:
    """Return (path, meta) for url.

    A cached copy younger than max_age_days is returned without a network call.
    Otherwise the URL is downloaded again. Only http and https are accepted.
    downloader replaces the plain download (tools/exchanges/client.py passes its polite
    session); it must return a successful response or raise FetchError.
    """
    _check_url(url)
    cache_dir = _cache_dir()
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    body_path = cache_dir / f"{key}.bin"
    meta_path = cache_dir / f"{key}.json"
    meta = _read_meta(url, meta_path)
    if meta is not None and _is_fresh(meta, max_age_days) and _body_matches(body_path, meta):
        return body_path, meta

    response = (downloader or _download)(url)
    body = response.content
    new_hash = hashlib.sha256(body).hexdigest()
    _keep_previous_body(body_path, key, meta, new_hash)
    body_path.write_bytes(body)
    saved = {
        "url": url,
        "fetched_at": _now(),
        "sha256": new_hash,
        "content_type": response.headers.get("content-type", ""),
        "status": response.status_code,
    }
    meta_path.write_text(json.dumps(saved), encoding="utf-8")
    return body_path, saved


def _check_url(url: str) -> None:
    """Reject anything that is not an http(s) URL before any request is made."""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise FetchError(url, None, f"Only http and https URLs can be fetched. Got {url!r}.")


def _cache_dir() -> Path:
    """Return the fetch cache. Tests set FETCH_CACHE_DIR."""
    override = os.environ.get("FETCH_CACHE_DIR", "").strip()
    path = Path(override) if override else ROOT / "cache" / "fetch"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_meta(url: str, path: Path) -> dict | None:
    """Return the sidecar, or None when this URL has not been stored."""
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FetchError(url, None, f"Cache sidecar is not valid JSON: {path.name}") from exc
    if not isinstance(meta, dict):
        raise FetchError(url, None, f"Cache sidecar is not an object: {path.name}")
    return meta


def _is_fresh(meta: dict, max_age_days: int) -> bool:
    """True when fetched_at is strictly younger than max_age_days."""
    raw = meta.get("fetched_at") or ""
    try:
        fetched = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age = datetime.now(timezone.utc) - fetched
    return age < timedelta(days=max_age_days)


def _body_matches(path: Path, meta: dict) -> bool:
    """True when the stored file exists and its sha256 matches the sidecar."""
    if not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == meta.get("sha256")


def _keep_previous_body(body_path: Path, key: str, meta: dict | None, new_hash: str) -> None:
    """Rename the old body when a refetch downloaded different bytes."""
    if meta is None or not body_path.is_file():
        return
    old_hash = str(meta.get("sha256") or "")
    if not old_hash or old_hash == new_hash:
        return
    if hashlib.sha256(body_path.read_bytes()).hexdigest() != old_hash:
        return
    archive = body_path.with_name(f"{key}.{old_hash[:8]}.bin")
    body_path.replace(archive)


_LAST_HIT: dict[str, float] = {}


def _pace(url: str) -> None:
    """NSE and BSE files: wait until MIN_GAP_S has passed since this process last asked the same host."""
    from config import exchanges as rules

    host = urlsplit(url).hostname or ""
    if host not in rules.HOSTS:
        return
    wait = _LAST_HIT.get(host, 0.0) + rules.MIN_GAP_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _LAST_HIT[host] = time.monotonic()


def _get_checked(url: str) -> httpx.Response:
    """GET url, following redirects by hand so that every hop is checked with public_url first.

    A public address that redirects to a private one (cloud metadata, localhost, a LAN host) is refused.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _pace(current)
        response = httpx.get(current, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
        location = response.headers.get("location")
        if response.status_code not in REDIRECT_CODES or not location:
            return response
        current = urljoin(current, location)
        _check_url(current)
        refused = public_url(current)
        if refused:
            raise FetchError(url, None, f"A redirect from {url} was refused: {refused}.")
    raise FetchError(url, None, f"Too many redirects from {url}.")


def _download(url: str) -> httpx.Response:
    """GET url. Retry transport errors and HTTP 5xx twice. Never retry 401 or 403.

    The only header sent is User-Agent. No cookies are added.
    """
    last_error: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            response = _get_checked(url)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt >= RETRIES:
                raise FetchError(url, None, f"Download failed for {url}. {exc}") from exc
            time.sleep(0.5 * (2**attempt))
            continue
        if response.status_code in (401, 403):
            raise FetchError(
                url,
                response.status_code,
                f"HTTP {response.status_code} for {url}. Not retrying and not adding headers.",
            )
        if response.status_code >= 500 and attempt < RETRIES:
            time.sleep(0.5 * (2**attempt))
            continue
        if response.status_code >= 400:
            raise FetchError(url, response.status_code, f"HTTP {response.status_code} for {url}.")
        return response
    raise FetchError(url, None, f"Download failed for {url}. {last_error}")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
