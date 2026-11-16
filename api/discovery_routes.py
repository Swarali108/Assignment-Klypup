"""Signal sources, "Check for new filings now" and the auto-processing log. Admin only.

    GET  /api/sources                    every source: on / off / blocked / failed, why, terms, risk,
                                         last checked, items, errors; the EXCHANGE_SOURCES switch.
    POST /api/discovery/check-now        {} -> the estimate and a single-use confirm token (nothing runs);
                                         {"confirm": token} -> starts discovery + auto-processing within
                                         the confirmed ceiling: {job_id, stream_url}.
    GET  /api/discovery/jobs/{id}        all progress events so far and the state.
    GET  /api/discovery/jobs/{id}/stream server-sent events, one `data: {...}` per stage, ending with
                                         stage "finish".
    GET  /api/discovery/auto-log         cycles (newest first), what ran and its cost, today's auto spend
                                         against the cap, events waiting for approval, the scheduler.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api import auth, scheduler, store
from config import signals as cfg

router = APIRouter()
ADMIN_VIEW = [auth.OPS]
ADMIN_USER = auth.require("process")


# ---------- sources ----------

def owner_of(source_id: str) -> str:
    """SEBI / NSE / BSE from a source id's prefix; "Other" when none matches."""
    lowered = (source_id or "").lower()
    return next((owner for prefix, owner in cfg.SOURCE_OWNERS if lowered.startswith(prefix)), "Other")


def _state(status: str | None, enabled: bool) -> str:
    """The Sources page's word for a source: on, off, blocked, failed or not checked."""
    if not enabled:
        return "off"
    return {"ok": "on", "disabled": "off", "blocked": "blocked", "failed": "failed"}.get(status or "", "not checked")


def sources_view() -> dict:
    """Configured SEBI sources, the SEBI draft-offer watchlist, and the exchange sources the last
    refresh reported (or one honest row per exchange when none ran), each with its last status."""
    from config.sources import SOURCES
    from tools import discover

    report = store.discovery() or {}
    last = {status.get("id"): status for status in report.get("sources") or []}
    item_errors: dict[str, list[str]] = {}
    for item in report.get("items") or []:
        if item.get("error"):
            item_errors.setdefault(item.get("source"), []).append(str(item["error"])[:200])
    exchange_state = discover.exchange_module_state()
    rows, seen = [], set()

    def add(source_id: str, name: str, url: str, terms_url: str, reason: str, enabled: bool,
            status: dict | None, what: str) -> None:
        owner = owner_of(source_id)
        is_exchange = owner in ("NSE", "BSE")
        state = _state((status or {}).get("status"), enabled)
        why = (status or {}).get("reason") or reason
        if is_exchange and exchange_state == "off":
            state, why = "off", "Switched off: EXCHANGE_SOURCES=off."
        elif is_exchange and exchange_state == "missing" and not status:
            state, why = "off", "The NSE/BSE reader is not installed in this build."
        errors = list(item_errors.get(source_id, []))
        if state in ("blocked", "failed") and why:
            errors.insert(0, why)
        rows.append({"id": source_id, "name": name, "owner": owner, "url": url, "what": what,
                     "terms_url": terms_url or cfg.EXCHANGE_TERMS.get(owner, ""), "state": state, "reason": why,
                     "risk": (status or {}).get("risk") if isinstance((status or {}).get("risk"), dict)
                     else cfg.RISK.get(owner, {"level": "unknown", "label": "Risk not assessed"}),
                     "last_checked": None if state == "off" or not status
                     else status.get("checked_at") or report.get("refreshed_at"),
                     "items": int((status or {}).get("items") or 0), "records": (status or {}).get("records"),
                     "errors": errors[:5], "error_count": len(errors)})
        seen.add(source_id)

    for source in tuple(SOURCES) + tuple(cfg.WATCH_SOURCES):
        what = "Draft offer documents: IPOs coming" if source.get("force_class") == "ipo_coming" else source["name"].split("·", 1)[-1].strip()
        add(source["id"], source["name"], source["url"], source["terms_url"], source["reason"],
            bool(source.get("enabled")) and (owner_of(source["id"]) == "SEBI" or exchange_state == "on"),
            last.get(source["id"]), what)
    for source_id, status in last.items():
        if source_id in seen or not source_id:
            continue
        add(source_id, status.get("name") or source_id, status.get("url") or "", status.get("terms_url") or "",
            status.get("reason") or "", True, status, status.get("name") or source_id)
    for owner in ("NSE", "BSE"):
        if not any(row["owner"] == owner for row in rows):
            add(f"{owner.lower()}_exchange", f"{owner} · announcements, deals and insider disclosures", "",
                cfg.EXCHANGE_TERMS[owner], "Not read yet.", exchange_state == "on", None,
                "Announcements, OFS notices, block and bulk deals, insider disclosures")
    return {"refreshed_at": report.get("refreshed_at"),
            "switch": {"name": "EXCHANGE_SOURCES", "value": "off" if exchange_state == "off" else "on",
                       "reader": "missing" if exchange_state == "missing" else "installed"},
            "sources": rows}


@router.get("/api/sources", dependencies=ADMIN_VIEW)
def sources() -> dict:
    """Every signal source with its status, terms and risk."""
    return sources_view()


# ---------- check now ----------

class CheckIn(BaseModel):
    """POST /api/discovery/check-now body: no confirm = estimate only."""

    confirm: str | None = None


@router.post("/api/discovery/check-now")
def check_now(body: CheckIn, user: dict = ADMIN_USER) -> dict:
    """Without a token: the estimate and a token (no network, no model, no writes). With one: start the check."""
    if not body.confirm:
        estimate = scheduler.check_estimate()
        return {"state": "estimate", "estimate": estimate, **scheduler.issue_token(user["email"], estimate)}
    grant = scheduler.redeem_token(body.confirm, user["email"])
    if grant is None:
        raise HTTPException(409, "This estimate has expired or was already used. Ask for a new one.")
    lock = scheduler.FileLock(scheduler.RUN_LOCK)
    if not lock.acquire():
        raise HTTPException(409, "A check is already running. Its results will appear here when it ends.")
    job = scheduler.start_check(grant["ceiling_usd"], lock)
    return {"state": "running", "job_id": job["job_id"], "ceiling_usd": grant["ceiling_usd"],
            "stream_url": f"/api/discovery/jobs/{job['job_id']}/stream"}


@router.get("/api/discovery/jobs/{job_id}", dependencies=ADMIN_VIEW)
def check_job(job_id: str) -> dict:
    """All progress events so far and the state."""
    snap = scheduler.job_snapshot(job_id)
    if snap is None:
        raise HTTPException(404, "No such check")
    return {"job_id": job_id, "state": snap[1], "events": snap[0]}


@router.get("/api/discovery/jobs/{job_id}/stream", dependencies=ADMIN_VIEW)
async def check_stream(job_id: str) -> StreamingResponse:
    """Server-sent events for one check, ending after the "finish" stage."""
    if scheduler.job_snapshot(job_id) is None:
        raise HTTPException(404, "No such check")

    async def gen():
        sent = 0
        while True:
            snap = scheduler.job_snapshot(job_id, sent)
            if snap is None:
                return
            new, state = snap
            for item in new:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            sent += len(new)
            if state != "running" and not new:
                return
            if not new:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


# ---------- auto log ----------

def _company_of(event_id: str) -> str | None:
    """The company of an event id from the last discovery report, if listed."""
    for event in (store.discovery() or {}).get("events") or []:
        if event.get("event_id") == event_id:
            return event.get("company")
    return None


def _processed_since(event_id: str, at: str | None) -> bool:
    """True when the event's call list was written after `at` (someone processed it by hand since)."""
    from datetime import datetime, timezone

    ranked = store.OUTPUTS_DIR / (event_id or "") / "ranked.json"
    if not at or not event_id or not ranked.is_file():
        return False
    try:
        held = datetime.fromisoformat(at)
    except ValueError:
        return False
    return datetime.fromtimestamp(ranked.stat().st_mtime, timezone.utc) > held


@router.get("/api/discovery/auto-log", dependencies=ADMIN_VIEW)
def auto_log(limit: int = 20) -> dict:
    """What ran automatically, its cost, today's spend against the cap, and what waits for approval."""
    conf = scheduler.settings()
    cycles = scheduler.read_auto_log()
    spent = scheduler.today_auto_spend()
    latest: dict[str, dict] = {}
    for entry in store.discovery_log():
        latest[entry.get("event_id")] = entry
    waiting = [{"event_id": event_id, "company": _company_of(event_id), "reason": entry.get("reason"),
                "estimate_usd": entry.get("estimate_usd"), "at": entry.get("at")}
               for event_id, entry in latest.items()
               if entry.get("status") == "needs_approval" and not _processed_since(event_id, entry.get("at"))]
    runs = [{**entry, "company": _company_of(entry.get("event_id"))}
            for cycle in cycles if cycle.get("day") == scheduler.local_day()
            for entry in cycle.get("processed") or [] if entry.get("status") != "needs_approval"]
    return {"today": {"day": scheduler.local_day(), "timezone": conf["timezone"], "spent_usd": spent,
                      "cap_usd": conf["cap_usd"], "remaining_usd": round(max(0.0, conf["cap_usd"] - spent), 6),
                      "runs": len([r for r in runs if r.get("status") == "ok"])},
            "scheduler": scheduler.SCHEDULER.status(), "needs_approval": waiting, "runs_today": runs[::-1],
            "cycles": cycles[::-1][:max(1, min(limit, 100))]}
