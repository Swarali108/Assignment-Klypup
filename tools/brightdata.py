"""Bright Data API client: bearer token, timeouts, 5xx-only retries, a local monthly request counter with a hard
stop, and a response cache that only ever stores already-filtered data.

Docs read 2026-11-15 (all under https://docs.brightdata.com):
  Auth: every call sends "Authorization: Bearer <API key>" (api-reference/.../monitor-progress).
  Scraper API: POST /datasets/v3/scrape (sync, waits up to 1 minute; past that answers 202 with a
      snapshot_id), POST /datasets/v3/trigger (async, returns snapshot_id), GET /datasets/v3/progress/{id}
      (status starting | running | ready | failed | canceled), GET /datasets/v3/snapshot/{id}?format=json
      (202 "Snapshot is not ready yet, try again in 10s" while building). Discovery always runs async.
      (api-reference/scrapers/synchronous-requests, api-reference/rest-api/scraper/asynchronous-requests,
       api-reference/scrapers/delivery-apis/download-snapshot, api-reference/marketplace-dataset-api/troubleshooting)
  SERP API: POST /request {"zone": <serp zone>, "url": "https://www.google.com/search?q=...&brd_json=1",
      "format": "raw"} returns Google results parsed as JSON (api-reference/serp/google-search/parsed-json).
  Account: GET /zone/get_active_zones -> [{"name", "type"}] (api-reference/account-management-api/Get_active_Zones).
  Errors: 400 validation_error, 401 invalid credentials, 404 dataset or snapshot not found, 202 not ready.
  Metering (general/account/billing-and-pricing/free-tier): 5,000 free credits a month in one shared pool;
      SERP API and Web Scraper API cost one credit per request or delivered record; reset on the 1st; an
      unfunded account hard-stops when the credits run out (an account with deposited funds moves on to paid
      pay-as-you-go rates instead). The docs conflict on reading the balance: the free-tier page names
      GET /trials/free_tier, the balance page's FAQ says no endpoint returns it. On 2026-11-15 this project's token
      got 403 (permissions) from both /trials/free_tier and /customer/balance, so whether the account holds
      deposited funds is unconfirmed, and we count locally.
  Account status: GET /status -> {status, can_make_requests, auth_fail_reason}
      (account-management-api/Get_account_status). On 2026-11-15 it said active, can_make_requests false,
      zone_not_found, and /datasets/v3/trigger answered 400 "Customer is not active".

Local counting is deliberately pessimistic: every HTTP attempt (retries and progress polls included) counts 1,
and a response that carries N records counts N - 1 more. Bright Data bills only requests to billed products and
delivered records, so the local "used" figure is never below the real spend. The count is written before the
request is sent, so a crash cannot lose it.

There is deliberately no generic "fetch this URL through Bright Data" method: the SERP call builds its own Google
URL and refuses a zone whose type is not "serp". No unblocker or proxy is used for any other site (owner ruling).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv

from config import enrichment as cfg

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.brightdata.com"
# Read the project .env once at import (a variable already set wins), so LINKEDIN_ENRICHMENT and
# BRIGHTDATA_REQUEST_CAP from .env apply before the first request, not only after the token is read.
load_dotenv(ROOT / ".env")
TIMEOUT_S = 70.0  # the sync scrape waits up to 60 s before answering 202
RETRIES = 2  # 5xx only
BACKOFF_S = 2.0


class BrightDataError(Exception):
    """A Bright Data call failed. status is the HTTP code, or None when there was no response."""

    def __init__(self, status: int | None, message: str):
        self.status = status
        super().__init__(message)


class CapReached(BrightDataError):
    """The local monthly request cap would be crossed, so nothing was sent."""


def now_iso() -> str:
    """UTC time in ISO format, seconds precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def month_key(moment: datetime | None = None) -> str:
    """Calendar month (UTC) the counter is kept under, e.g. "2026-11"."""
    return (moment or datetime.now(timezone.utc)).strftime("%Y-%m")


def cache_dir() -> Path:
    """cache/brightdata, or BRIGHTDATA_CACHE_DIR (tests point it at a temp folder)."""
    override = (os.environ.get("BRIGHTDATA_CACHE_DIR") or "").strip()
    path = Path(override) if override else ROOT / "cache" / "brightdata"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data) -> None:
    """Write JSON atomically (temp file + rename) so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=1)
    os.replace(temp, path)


# ---- usage counter -------------------------------------------------------------------------------------------

def _usage_path() -> Path:
    return cache_dir() / "usage.json"


def _read_usage() -> dict:
    path = _usage_path()
    if not path.is_file():
        return {"months": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A damaged counter must not reset spend to zero: refuse until a human looks at it.
        raise BrightDataError(None, f"The Bright Data usage file {path} cannot be read; fix it before more lookups.")


def _month(usage: dict, key: str) -> dict:
    return usage["months"].setdefault(key, {"requests": 0, "records": 0, "extra_records": 0, "by_kind": {}})


def usage_summary(cap: int | None = None) -> dict:
    """{"month", "cap", "used", "remaining", "requests", "records"} for this calendar month. For the UI / Sources."""
    cap = cfg.request_cap() if cap is None else cap
    key = month_key()
    month = _read_usage()["months"].get(key, {})
    used = int(month.get("requests", 0)) + int(month.get("extra_records", 0))
    return {"month": key, "cap": cap, "used": used, "remaining": max(cap - used, 0),
            "requests": int(month.get("requests", 0)), "records": int(month.get("records", 0)),
            "counting": "each HTTP call counts 1; each record past the first in a response counts 1 more"}


def ensure_budget(requests: int, cap: int | None = None) -> None:
    """Raise CapReached when `requests` more would cross this month's cap. Nothing is counted here."""
    summary = usage_summary(cap)
    if summary["used"] + requests > summary["cap"]:
        raise CapReached(None, f"Bright Data monthly cap reached: {summary['used']} of {summary['cap']} requests used "
                               f"in {summary['month']}; this lookup could need {requests}. Nothing was sent.")


def _count(kind: str, requests: int = 0, records: int = 0, cap: int | None = None) -> None:
    """Add to this month's counter. A request is refused (CapReached) before it is counted or sent."""
    usage = _read_usage()
    month = _month(usage, month_key())
    if requests:
        limit = cfg.request_cap() if cap is None else cap
        if month["requests"] + month["extra_records"] + requests > limit:
            raise CapReached(None, f"Bright Data monthly cap of {limit} requests reached; nothing was sent.")
    month["requests"] += requests
    month["records"] += records
    month["extra_records"] += max(records - 1, 0)
    month["by_kind"][kind] = month["by_kind"].get(kind, 0) + requests + max(records - 1, 0)
    _write_json(_usage_path(), usage)


# ---- response cache ------------------------------------------------------------------------------------------

def request_hash(kind: str, payload: dict) -> str:
    """sha256 of the kind and the request payload (never the token)."""
    text = json.dumps({"kind": kind, "payload": payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cached(kind: str, payload: dict, max_age_days: float, fetch: Callable[[], object],
           keep: Callable[[object], object]) -> tuple[object, str, bool]:
    """(data, fetched_at, from_cache). A fresh cached copy costs 0 requests.

    On a miss, fetch() runs (it makes the counted requests), then keep() filters the raw data, and only the
    filtered data is written to cache/brightdata/<kind>/<hash>.json. Raw responses never touch the disk.
    """
    path = cache_dir() / kind / f"{request_hash(kind, payload)}.json"
    if path.is_file():
        saved = json.loads(path.read_text(encoding="utf-8"))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(saved["fetched_at"])
        if age.total_seconds() <= max_age_days * 86400:
            return saved["data"], saved["fetched_at"], True
    data = keep(fetch())
    fetched_at = now_iso()
    _write_json(path, {"kind": kind, "request": payload, "fetched_at": fetched_at, "data": data})
    return data, fetched_at, False


# ---- client --------------------------------------------------------------------------------------------------

def _token() -> str:
    """BRIGHTDATA_API_TOKEN from the environment or the project .env. Never logged or put in an error."""
    load_dotenv(ROOT / ".env")
    token = (os.environ.get("BRIGHTDATA_API_TOKEN") or "").strip()
    if not token:
        raise BrightDataError(None, "BRIGHTDATA_API_TOKEN is not set.")
    return token


class Client:
    """Thin Bright Data client. transport and sleep are injectable so tests run with no network."""

    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, cap: int | None = None):
        self._token = token
        self._transport = transport
        self._sleep = sleep
        self.cap = cap
        self.requests_made = 0  # this client's HTTP calls, for "requests used" in a lookup's result

    def _http(self) -> httpx.Client:
        token = self._token or _token()
        return httpx.Client(base_url=API, timeout=TIMEOUT_S, transport=self._transport,
                            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def send(self, kind: str, method: str, path: str, params: dict | None = None,
             body: object = None) -> httpx.Response:
        """One counted call. Retries 5xx up to RETRIES times (each retry counted); any other status is returned
        as-is for 2xx, else raised as BrightDataError with the API's message (never the request headers)."""
        attempt = 0
        with self._http() as http:
            while True:
                _count(kind, requests=1, cap=self.cap)
                self.requests_made += 1
                try:
                    response = http.request(method, path, params=params, json=body)
                except httpx.HTTPError as exc:
                    raise BrightDataError(None, f"Bright Data {path} did not answer: {type(exc).__name__}") from None
                if response.status_code >= 500 and attempt < RETRIES:
                    attempt += 1
                    self._sleep(BACKOFF_S * attempt)
                    continue
                if response.status_code >= 400:
                    raise BrightDataError(response.status_code, _error_message(path, response))
                return response

    # -- account (management endpoints; still counted) --

    def active_zones(self) -> list[dict]:
        """[{"name", "type"}] for the account's active zones."""
        return self.send("zones", "GET", "/zone/get_active_zones").json()

    def serp_zone(self) -> str:
        """The SERP zone to use: BRIGHTDATA_SERP_ZONE if set, else the first active zone of type "serp".
        Either way it must be an active zone of type "serp" (so /request is never used as an unblocker)."""
        wanted = (os.environ.get("BRIGHTDATA_SERP_ZONE") or "").strip()
        keep = lambda raw: [{"name": z.get("name"), "type": z.get("type")} for z in raw or []]  # noqa: E731
        zones, _, from_cache = cached("zones", {}, cfg.CACHE_DAYS["zones"], self.active_zones, keep)
        serp = [z["name"] for z in zones if z.get("type") == "serp"]
        if from_cache and (not serp or (wanted and wanted not in serp)):
            # A cached list without the zone we need may be stale (the owner just added it): ask once more.
            zones, _, _ = cached("zones", {}, -1, self.active_zones, keep)
            serp = [z["name"] for z in zones if z.get("type") == "serp"]
        if wanted:
            if wanted not in serp:
                raise BrightDataError(None, f"Zone {wanted!r} is not an active SERP zone; refusing to use it.")
            return wanted
        if not serp:
            raise BrightDataError(None, "No active SERP zone on this Bright Data account; add one in the control "
                                        "panel (SERP API) before web search can run.")
        return serp[0]

    # -- scraper API --

    def scrape(self, kind: str, dataset_id: str, inputs: list[dict], params: dict | None = None,
               body_extra: dict | None = None) -> list[dict]:
        """Sync scrape (one input). Falls back to polling when Bright Data answers 202 with a snapshot_id."""
        query = {"dataset_id": dataset_id, "format": "json", "include_errors": "true", **(params or {})}
        response = self.send(kind, "POST", "/datasets/v3/scrape", params=query, body={"input": inputs, **(body_extra or {})})
        data = _parse_records(response)
        if response.status_code == 202 or (isinstance(data, dict) and data.get("snapshot_id")):
            return self.wait_for(kind, data["snapshot_id"])
        records = data if isinstance(data, list) else [data]
        _count(kind, records=len(records), cap=self.cap)
        return records

    def collect(self, kind: str, dataset_id: str, inputs: list[dict], params: dict | None = None,
                body_extra: dict | None = None) -> list[dict]:
        """Async: trigger, poll progress, download the snapshot."""
        query = {"dataset_id": dataset_id, "format": "json", "include_errors": "true", **(params or {})}
        response = self.send(kind, "POST", "/datasets/v3/trigger", params=query, body={"input": inputs, **(body_extra or {})})
        snapshot_id = response.json().get("snapshot_id")
        if not snapshot_id:
            raise BrightDataError(response.status_code, "Bright Data trigger returned no snapshot_id.")
        return self.wait_for(kind, snapshot_id)

    def wait_for(self, kind: str, snapshot_id: str) -> list[dict]:
        """Poll progress up to MAX_POLLS times, then download. A failed or empty job returns [] with no error
        only when Bright Data says nothing was found; other failures raise."""
        for _ in range(cfg.MAX_POLLS):
            status = self.send(kind, "GET", f"/datasets/v3/progress/{snapshot_id}").json()
            state = status.get("status")
            if state == "ready":
                break
            if state in ("failed", "canceled"):
                message = str(status.get("error_message") or status.get("error") or state)
                if "no data found" in message.lower() or "snapshot is empty" in message.lower():
                    return []
                raise BrightDataError(None, f"Bright Data job {snapshot_id} {state}: {message[:200]}")
            self._sleep(cfg.POLL_SECONDS)
        else:
            raise BrightDataError(None, f"Bright Data job {snapshot_id} not ready after {cfg.MAX_POLLS} checks; "
                                        "it keeps running on their side and can be downloaded later.")
        response = self.send(kind, "GET", f"/datasets/v3/snapshot/{snapshot_id}", params={"format": "json"})
        if response.status_code == 202:
            raise BrightDataError(202, f"Bright Data snapshot {snapshot_id} still building after progress said ready.")
        data = _parse_records(response)
        records = data if isinstance(data, list) else [data]
        _count(kind, records=len(records), cap=self.cap)
        return records

    # -- SERP API --

    def google(self, query: str, news: bool = False, results: int = cfg.SEARCH_RESULTS) -> dict:
        """Google results for `query` as Bright Data's parsed JSON. The URL is built here; callers pass only words."""
        url = f"https://www.google.com/search?q={quote_plus(query)}&num={int(results)}&hl=en&brd_json=1"
        if news:
            url += "&tbm=nws"
        zone = self.serp_zone()
        response = self.send("serp", "POST", "/request", body={"zone": zone, "url": url, "format": "raw"})
        try:
            return response.json()
        except ValueError:
            raise BrightDataError(response.status_code, "Bright Data SERP answer was not JSON.") from None


# API messages that need an owner action, with the action.
_OWNER_ACTIONS = {
    "customer is not active": "The Bright Data account is not active for this product: activate it in the "
                              "Bright Data control panel (account settings / billing), then retry.",
    "lacks the required permissions": "The API token lacks permission for this endpoint (token settings).",
}


def _error_message(path: str, response: httpx.Response) -> str:
    """The API's own message (first 300 chars), plus the owner action when we know one. Never headers."""
    text = response.text[:300]
    hint = next((action for key, action in _OWNER_ACTIONS.items() if key in text.lower()), "")
    return f"Bright Data {path} answered {response.status_code}: {text}" + (f" {hint}" if hint else "")


def account_status(client: "Client") -> dict:
    """{"status", "can_make_requests", "auth_fail_reason"} from GET /status (1 counted request; no ids kept)."""
    data = client.send("account", "GET", "/status").json()
    return {k: data.get(k) for k in ("status", "can_make_requests", "auth_fail_reason")}


def _parse_records(response: httpx.Response):
    """JSON array/object, or NDJSON (one record per line) when Bright Data ignores format=json."""
    text = response.text.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except ValueError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def drop_error_records(records: list[dict]) -> list[dict]:
    """Records Bright Data marked as errors (include_errors=true) are not data; drop them.

    When every delivered record is an error, raise instead of returning [], so a failed lookup is never cached
    as "nothing found". An empty result is cached only when Bright Data delivered no records at all."""
    good = [r for r in records if isinstance(r, dict) and not r.get("error") and not r.get("error_code")]
    if records and not good:
        first = next((r for r in records if isinstance(r, dict)), {})
        detail = str(first.get("error") or first.get("error_code") or "unknown error")[:200]
        raise BrightDataError(None, f"Bright Data returned only error records: {detail}")
    return good
