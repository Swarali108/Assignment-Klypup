"""Public enrichment for one call-list person: a public LinkedIn profile and web mentions, through Bright Data.

Owner rules (2026-11-15/16) enforced here and in agents/enrich_linkedin.py, agents/enrich_news.py:
  - LinkedIn is on by default (LINKEDIN_ENRICHMENT=off switches it off); the web search is always available.
  - Public professional fields only (allow-lists in config/enrichment.py); the token comes from .env only and is
    never returned, logged or stored.
  - Every lookup is a paid step: estimate() gives the worst-case request count, the caller confirms that number,
    and the Bright Data client refuses before sending if the monthly cap could be crossed.
  - An unconfirmed LinkedIn match is shown with its match level and the reason; it is never merged into the
    person's facts.

The last result for each person is kept in cache/brightdata/people/<event>__<person>.json (cache/ is not committed),
so the person page and the trail read it for free. A lookup runs on a background thread; the page polls state().
Organisations (funds, companies) are never looked up on LinkedIn.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone

from agents import enrich_linkedin as li
from agents import enrich_news as news
from agents.names import clean_name
from api import store, views
from config import enrichment as cfg
from tools import brightdata as bd

KINDS = ("linkedin", "web")
KIND_LABEL = {"linkedin": "Public profile (LinkedIn)", "web": "Mentions on the web"}
MAX_CANDIDATES = 5

_LOCK = threading.Lock()
_RUNNING: dict[tuple[str, str], dict] = {}


# ---------- status ----------

def token_configured() -> bool:
    """True when BRIGHTDATA_API_TOKEN is available (the value is never read out of here)."""
    try:
        bd._token()
        return True
    except bd.BrightDataError:
        return False


def status() -> dict:
    """For the Sources page row: requests used / cap this month, the LinkedIn switch, whether a token is set."""
    out = {"linkedin_enabled": cfg.linkedin_enabled(), "web_enabled": True, "token_configured": token_configured(),
           "month": bd.month_key(), "cap": cfg.request_cap(), "used": 0, "remaining": cfg.request_cap(),
           "error": None}
    try:
        usage = bd.usage_summary()
        out.update({k: usage[k] for k in ("month", "cap", "used", "remaining", "requests", "records", "counting")})
    except bd.BrightDataError as exc:
        out["error"] = str(exc)
    out["ready"] = out["token_configured"] and out["error"] is None
    return out


# ---------- storage ----------

def _path(event_id: str, person_id: str):
    safe = lambda s: re.sub(r"[^a-zA-Z0-9_.-]", "_", s)  # noqa: E731
    folder = bd.cache_dir() / "people"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{safe(event_id)}__{safe(person_id)}.json"


def load(event_id: str, person_id: str) -> dict | None:
    """The stored lookup result for this person, or None when nothing was looked up yet."""
    path = _path(event_id, person_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(record: dict) -> None:
    bd._write_json(_path(record["event_id"], record["person_id"]), record)


# ---------- what can be looked up ----------

def _person(event_id: str, person_id: str) -> tuple[dict, dict]:
    """(event, people.json person); KeyError when either is missing."""
    event = store.find_event(event_id)
    if not event or not event["processed"]:
        raise KeyError("event")
    person = views.people_by_id(event).get(person_id)
    if person is None:
        raise KeyError("person")
    return event, person


def _eligibility(person: dict) -> dict[str, dict]:
    """{kind: {allowed, reason}} before any cap check."""
    org = views.is_organisation(person.get("name_as_printed"), person.get("holder_type"))
    ok = token_configured()
    return {
        "linkedin": {"allowed": ok and not org and cfg.linkedin_enabled(),
                     "reason": (None if ok and not org and cfg.linkedin_enabled() else
                                "LinkedIn lookups are only for people, not funds or companies." if org else
                                "LinkedIn lookups are switched off." if not cfg.linkedin_enabled() else
                                "Bright Data is not connected (no access token on the server).")},
        "web": {"allowed": ok, "reason": None if ok else "Bright Data is not connected (no access token on the server)."},
    }


def _queries(person: dict, company: str) -> dict[str, tuple[str, dict, float]]:
    """kind -> (cache kind, cache payload, max age days), mirroring what the agents cache on."""
    first, last = li.split_name(person["name_as_printed"])
    shown = " ".join(w.capitalize() for w in clean_name(person["name_as_printed"]).split())
    return {
        "linkedin": ("linkedin_discover", {"dataset": cfg.DATASET_DISCOVER_BY_NAME, "first_name": first,
                                           "last_name": last, "limit": cfg.DISCOVER_LIMIT},
                     cfg.CACHE_DAYS["linkedin_discover"]),
        "web": ("serp", {"q": f'"{shown}" "{company}"', "news": False, "n": cfg.SEARCH_RESULTS}, cfg.CACHE_DAYS["serp"]),
    }


def _cache_file(kind: str, payload: dict):
    return bd.cache_dir() / kind / f"{bd.request_hash(kind, payload)}.json"


def _is_cached(kind: str, payload: dict, days: float) -> bool:
    path = _cache_file(kind, payload)
    if not path.is_file():
        return False
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(saved["fetched_at"])
        return age.total_seconds() <= days * 86400
    except (OSError, ValueError, KeyError):
        return False


def estimate(event_id: str, person_id: str, kinds: list[str] | tuple[str, ...] = KINDS, refresh: bool = False) -> dict:
    """Worst-case Bright Data requests per kind for this person, what the cap allows, and whether a cached copy
    makes it free. {kinds: {kind: {allowed, reason, requests, cached}}, total, remaining, cap, over_cap}."""
    event, person = _person(event_id, person_id)
    can = _eligibility(person)
    queries = _queries(person, event["spec"].company)
    usage = status()
    out, total = {}, 0
    for kind in KINDS:
        if kind not in kinds:
            continue
        worst = cfg.worst_case_requests("find_profiles" if kind == "linkedin" else "search")
        cached = (not refresh) and _is_cached(*queries[kind])
        requests = 0 if cached else worst
        out[kind] = {**can[kind], "label": KIND_LABEL[kind], "requests": requests if can[kind]["allowed"] else 0,
                     "cached": bool(cached), "worst_case": worst}
        total += out[kind]["requests"]
    return {"kinds": out, "total": total, "cap": usage["cap"], "used": usage["used"], "remaining": usage["remaining"],
            "over_cap": total > usage["remaining"], "month": usage["month"]}


# ---------- running a lookup ----------

def _linkedin(person: dict, company: str, client: bd.Client) -> dict:
    found = li.find_profiles(person["name_as_printed"], company, client=client)[:MAX_CANDIDATES]
    return {"state": "found" if found else "none", "candidates": found,
            "fetched_at": max((c.get("fetched_at") or "" for c in found), default=None) or bd.now_iso(), "error": None}


def _web(person: dict, company: str, client: bd.Client) -> dict:
    rows = news.search(person["name_as_printed"], company, client=client)
    return {"state": "found" if rows else "none", "rows": rows,
            "fetched_at": (rows[0].get("fetched_at") if rows else None) or bd.now_iso(), "error": None}


def run(event_id: str, person_id: str, kinds: list[str] | tuple[str, ...], refresh: bool = False) -> dict:
    """Run the lookups now (blocking), merge them into the stored record and return it.

    refresh drops the cached copy first so the request is really sent (and counted). A failure in one kind is kept
    as that kind's error and does not stop the other.
    """
    event, person = _person(event_id, person_id)
    company = event["spec"].company
    can = _eligibility(person)
    queries = _queries(person, company)
    record = load(event_id, person_id) or {"event_id": event_id, "person_id": person_id, "name": person["name_as_printed"]}
    client = bd.Client()
    for kind in KINDS:
        if kind not in kinds:
            continue
        previous = record.get(kind) or {}
        if not can[kind]["allowed"]:
            record[kind] = {**previous, "state": "off", "error": can[kind]["reason"], "requests": 0}
            continue
        if refresh:
            _cache_file(*queries[kind][:2]).unlink(missing_ok=True)
        before = client.requests_made
        try:
            result = _linkedin(person, company, client) if kind == "linkedin" else _web(person, company, client)
        except (bd.BrightDataError, li.EnrichmentOff) as exc:
            # keep the last good data on screen; say plainly why the new lookup did not happen
            result = {**previous, "error": str(exc), "state": previous.get("state") if previous.get("state") in ("found", "none") else "error"}
        except Exception:  # noqa: BLE001 - never leak internals (or a token) to the page
            result = {**previous, "error": "The lookup failed. Try again later.",
                      "state": previous.get("state") if previous.get("state") in ("found", "none") else "error"}
        result["requests"] = client.requests_made - before
        record[kind] = result
    record["updated_at"] = bd.now_iso()
    _save(record)
    return record


def start(event_id: str, person_id: str, kinds: list[str], refresh: bool) -> bool:
    """Run in the background. False when a lookup for this person is already running."""
    key = (event_id, person_id)
    with _LOCK:
        if key in _RUNNING:
            return False
        _RUNNING[key] = {"kinds": list(kinds), "started_at": bd.now_iso()}

    def work() -> None:
        try:
            run(event_id, person_id, kinds, refresh)
        finally:
            with _LOCK:
                _RUNNING.pop(key, None)

    threading.Thread(target=work, daemon=True).start()
    return True


def state(event_id: str, person_id: str) -> dict:
    """What the person page shows: the stored record, whether a lookup is running, the estimate for a refresh."""
    event, person = _person(event_id, person_id)
    with _LOCK:
        running = _RUNNING.get((event_id, person_id))
    record = load(event_id, person_id)
    return {"event_id": event_id, "person_id": person_id, "name": person["name_as_printed"],
            "company": event["spec"].company, "record": record, "running": running,
            "estimate": estimate(event_id, person_id, KINDS, refresh=True),
            "eligibility": _eligibility(person), "status": status(),
            "web_label": cfg.SEARCH_LABEL}
