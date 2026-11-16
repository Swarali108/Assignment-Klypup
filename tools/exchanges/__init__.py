"""NSE and BSE connectors: discovery items and structured deal/insider records.

    from tools import exchanges
    result = exchanges.read_all(since_days=7)
    # {"sources": [status, ...], "items": [discovery item, ...],
    #  "records": {"deals": [record, ...], "insider": [record, ...]}}

read_all never raises. Each source in config/sources.EXCHANGE_SOURCES is read by
tools/exchanges/<nse|bse>.py through one polite client (tools/exchanges/client.py). A
401/403/429 stops that host for the run: every later source on it is "blocked" with the
status, and no further request goes to it. EXCHANGE_SOURCES=off makes every source
"disabled" with no request at all.

Items use tools/discover.new_item's schema (plus "summary" and "exchange"), already classified.
Records follow the shared schema and are merged by id into outputs/signals/deals.json and
outputs/signals/insider.json; a blocked or failed run updates source_status there and keeps
the records already saved. An insider disclosure filed on both exchanges is kept once (NSE).
signal_events(records) groups sale records into event specs.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from config.exchanges import BLOCK_CODES, SWITCH_ENV, exchange_sources_on
from config.sources import EXCHANGE_SOURCES
from tools.discover import slug
from tools.exchanges import bse, nse
from tools.exchanges.client import ExchangeClient, host_of
from tools.exchanges.common import date_blocks, day_ages, twin_key, window_start
from tools.fetch import FetchError

ROOT = Path(__file__).resolve().parents[2]
READERS = {"NSE": nse, "BSE": bse}
RECORD_FILES = {"deals": ("block_deal", "bulk_deal"), "insider": ("insider_sale",)}
EVENT_TYPE = {"block_deal": "block_deal", "bulk_deal": "block_deal", "insider_sale": "insider_sale"}


class Context:
    """What a reader needs: a latched fetcher, the window (its 7-day blocks and its days), and a cache check."""

    def __init__(self, fetcher: Callable[[str, float], str], is_cached: Callable[[str, float], bool],
                 since_days: float, now: datetime):
        self.fetcher, self.is_cached = fetcher, is_cached
        self.start: date = window_start(since_days, now)
        self.blocks = date_blocks(since_days, now)
        self.days = day_ages(since_days, now)
        self.fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.blocked: dict[str, FetchError] = {}

    def get(self, url: str, max_age_days: float) -> str:
        """fetcher(url, max_age_days), refusing a host that was blocked earlier in this run."""
        host = host_of(url)
        if host in self.blocked:
            raise self.blocked[host]
        try:
            return self.fetcher(url, max_age_days)
        except FetchError as exc:
            if exc.status in BLOCK_CODES:
                self.blocked[host] = exc
            raise


def _status(source: dict, **extra) -> dict:
    """The status dict discover's Sources page shows, for one exchange source."""
    return {"id": source["id"], "name": source["name"], "exchange": source["exchange"], "url": source["url"],
            "terms_url": source["terms_url"], "reason": source["reason"], "risk": source["risk"], "items": 0,
            "records": 0, "note": "", **extra}


def read_source(source: dict, ctx: Context) -> tuple[dict, list[dict], list[dict]]:
    """(status, items, records) for one source; a block, an error or bad data becomes its status."""
    reader = getattr(READERS[source["exchange"]], source["reader"])
    try:
        items, records, notes = reader(source, ctx)
    except FetchError as exc:
        blocked = exc.status in BLOCK_CODES
        reason = f"HTTP {exc.status} — {exc}" if blocked else str(exc)
        return _status(source, status="blocked" if blocked else "failed", http_status=exc.status,
                       note=reason[:300]), [], []
    except Exception as exc:  # a source must never stop the others
        return _status(source, status="failed", note=f"{type(exc).__name__}: {exc}"[:300]), [], []
    records = list({record["id"]: record for record in records}.values())
    note = "; ".join(notes)
    return _status(source, status="ok", items=len(items), records=len(records), note=note), items, records


def read_all(since_days: float, fetcher: Callable[[str, float], str] | None = None,
             outputs_dir: Path | None = ROOT / "outputs", now: datetime | None = None,
             is_cached: Callable[[str, float], bool] | None = None) -> dict:
    """Read every NSE/BSE source for the last since_days; write outputs/signals/*.json. Never raises.

    fetcher(url, max_age_days) -> text defaults to a polite ExchangeClient. outputs_dir=None
    writes nothing (tests, dry runs).
    """
    now = now or datetime.now(timezone.utc)
    if not exchange_sources_on():
        statuses = [_status(source, status="disabled", note=f"{SWITCH_ENV}=off") for source in EXCHANGE_SOURCES]
        return _finish({"sources": statuses, "items": [], "records": {"deals": [], "insider": []}}, outputs_dir, now)
    client = None
    if fetcher is None:
        client = ExchangeClient()
        fetcher = client.get_text
    ctx = Context(fetcher, is_cached or (_cache_check if client else (lambda url, age: True)), since_days, now)
    statuses, items, records, seen = [], [], {"deals": [], "insider": []}, set()
    for source in EXCHANGE_SOURCES:
        status, found, rows = read_source(source, ctx)
        statuses.append(status)
        for item in found:
            if item["link"] not in seen:
                seen.add(item["link"])
                items.append(item)
        if source["records"]:
            records[source["records"]] += rows
    for name in records:
        records[name] = list({record["id"]: record for record in records[name]}.values())
    records["insider"] = _drop_twins(records["insider"], statuses)
    result = {"sources": statuses, "items": items, "records": records,
              "requests": client.requests if client else None}
    return _finish(result, outputs_dir, now)


def _drop_twins(records: list[dict], statuses: list[dict]) -> list[dict]:
    """One disclosure filed on both exchanges is kept once (the NSE copy); the BSE status says how many went."""
    nse_keys = {twin_key(record) for record in records if record["exchange"] == "NSE"}
    kept = [record for record in records if record["exchange"] == "NSE" or twin_key(record) not in nse_keys]
    dropped = len(records) - len(kept)
    for status in statuses:
        if status["id"] == "bse_insider" and status["status"] == "ok":
            status["records"] -= dropped
            status["note"] += f"; {dropped} also filed on NSE, kept once as the NSE record"
    return kept


def _cache_check(url: str, max_age_days: float) -> bool:
    """True when tools/fetch.py holds a fresh, intact copy of url (so reading it costs no request)."""
    import hashlib

    from tools import fetch as fetch_module

    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    folder = fetch_module._cache_dir()
    meta = fetch_module._read_meta(url, folder / f"{key}.json")
    return bool(meta) and fetch_module._is_fresh(meta, max_age_days) and \
        fetch_module._body_matches(folder / f"{key}.bin", meta)


def _finish(result: dict, outputs_dir: Path | None, now: datetime) -> dict:
    """Write outputs/signals/<file>.json for each record file (merged by id) and return result."""
    if outputs_dir is None:
        return result
    for name, kinds in RECORD_FILES.items():
        sources = [status for status in result["sources"]
                   if next(s for s in EXCHANGE_SOURCES if s["id"] == status["id"])["records"] == name]
        try:
            write_records(outputs_dir / "signals" / f"{name}.json", result["records"][name], sources, now)
        except OSError as exc:
            result.setdefault("errors", []).append(f"{name}.json not written: {exc}")
    return result


def write_records(path: Path, records: list[dict], statuses: list[dict], now: datetime) -> dict:
    """Merge records by id into path's earlier records; source_status is replaced by this run's."""
    previous = {}
    if path.is_file():
        try:
            previous = {record["id"]: record for record in json.loads(path.read_text(encoding="utf-8"))["records"]}
        except (OSError, ValueError, KeyError, TypeError):
            previous = {}
    merged = {**previous, **{record["id"]: record for record in records}}
    payload = {"refreshed_at": now.isoformat(timespec="seconds"),
               "source_status": {status["id"]: {key: status.get(key) for key in
                                                ("status", "note", "records", "http_status", "url", "terms_url")}
                                 for status in statuses},
               "records": sorted(merged.values(), key=lambda r: (r["trade_date"], r["company"], r["name_as_printed"]),
                                 reverse=True)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
    return payload


def signal_events(records: list[dict]) -> list[dict]:
    """Event specs for sale records: one per (event type, exchange, symbol, trade date), sells only.

    {"event_id", "event_type": "block_deal"|"insider_sale", "company", "documents": [],
     "records": [record ids], "records_file": "outputs/signals/<file>.json"}
    """
    groups: dict[tuple, dict] = {}
    for record in records:
        if record["side"] != "sell":
            continue
        event_type = EVENT_TYPE[record["kind"]]
        key = (event_type, record["exchange"], record["symbol"], record["trade_date"])
        file_name = next(name for name, kinds in RECORD_FILES.items() if record["kind"] in kinds)
        group = groups.setdefault(key, {
            "event_id": f"{slug(record['company'] or record['symbol'])}_{event_type}_{record['exchange'].lower()}_"
                        f"{record['trade_date'].replace('-', '')}",
            "event_type": event_type, "company": record["company"], "documents": [], "records": [],
            "records_file": f"outputs/signals/{file_name}.json"})
        group["records"].append(record["id"])
    return list(groups.values())
