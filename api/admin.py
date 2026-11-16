"""Admin pipeline console and system pages (admin only): api/CONTRACT.md "Admin" section.

Runs go through api/jobs (the same subprocess as every other run). A "fresh" run (empty model cache) shows an estimate
first and starts only with the confirm token that estimate returned (api/chat/tokens.py), exactly like the chat does.
"""

from __future__ import annotations

import asyncio
import csv
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api import accuracy, auth, jobs, ops_health, rundiff, store, views
from api.chat import estimate as est
from api.chat import tokens
from tools.costs import cost_log_path

router = APIRouter()
STEP_CHOICES = ("all", *jobs.STEPS)
# Pipeline step -> index into estimate.PIPELINE_STEPS.
STEP_INDEX = {"locate": 0, "extract": 1, "people": 2, "rank": 3, "brief": 4, "report": 5}


class RunIn(BaseModel):
    """POST /api/admin/run body."""

    event_id: str
    step: str = "all"
    person_id: str | None = None
    fresh: bool = False
    confirm_token: str | None = None


def _target(body: RunIn) -> str:
    return f"{body.event_id}|{body.step}|{body.person_id or ''}|{'fresh' if body.fresh else 'cached'}"


def run_estimate(event_id: str, step: str, person_id: str | None, fresh: bool) -> dict:
    """{low, high, seconds_low, seconds_high, breakdown, basis} for one console run."""
    found = est.pipeline_estimate(event_id)
    rows = found["breakdown"]
    if step != "all":
        rows = [rows[STEP_INDEX[step]]]
    if person_id and step == "brief":
        event = store.find_event(event_id)
        count = max(1, len(((event or {}).get("out") or {}).get("ranked", {}).get("callable") or []))
        rows = [{**r, "cost_usd": round(r["cost_usd"] / count, 6), "cost_usd_high": round(r["cost_usd_high"] / count, 6),
                 "cost_usd_low": round(r["cost_usd_low"] / count, 6), "calls": 1} for r in rows]
    if fresh:  # nothing is read from the cache, so the cheap end is not $0 any more
        rows = [{**r, "cost_usd_low": round(r["cost_usd_high"] * 0.7, 6)} for r in rows]
    low, high = est.total(rows)
    basis = found["basis"]
    if fresh:
        basis = ("Fresh run: every model call is paid for again, nothing is read from the answer cache. " + basis)
    return {"low": low, "high": high, "seconds_low": found["seconds_low"], "seconds_high": found["seconds_high"],
            "breakdown": rows, "basis": basis}


@router.get("/api/admin/events", dependencies=[auth.OPS])
def admin_events() -> dict:
    """Every event the console can run: status, people, last run."""
    running = jobs.running_events()
    last: dict[str, dict] = {}
    for row in store.runs():
        last[row.get("event_id") or ""] = row
    rows = []
    for event in store.load_events():
        spec = event["spec"]
        eid = spec.event_id
        callable_n = len(((event["out"].get("ranked") or {}).get("callable")) or [])
        rows.append({"event_id": eid, "company": spec.company, "event_type": spec.event_type,
                     "type_label": views.spec_type_label(spec), "supported": spec.event_type in store.SUPPORTED_TYPES,
                     "processed": event["processed"], "people_count": callable_n, "running": eid in running,
                     "last_run": {k: (last.get(eid) or {}).get(k) for k in ("run_id", "ended_at", "status", "total_cost_usd")}
                     if eid in last else None})
    rows.sort(key=lambda r: (not r["running"], r["company"].lower()))
    return {"count": len(rows), "events": rows, "steps": [{"step": s, "label": views.STEP_LABELS[s]} for s in jobs.STEPS]}


@router.post("/api/admin/run", dependencies=[auth.OPS])
def admin_run(body: RunIn, user: dict = auth.OPS_USER) -> dict:
    """Start a run. A fresh run answers {needs_confirm, estimate, confirm_token} first; send the token back to start it."""
    event = store.find_event(body.event_id)
    if event is None:
        raise HTTPException(404, "No such event")
    if event["spec"].event_type not in store.SUPPORTED_TYPES:
        raise HTTPException(422, "This kind of event is not supported yet")
    if body.step not in STEP_CHOICES:
        raise HTTPException(422, "Unknown step")
    if body.person_id and body.step != "brief":
        raise HTTPException(422, "A single person can only be re-run for the brief step")
    if body.person_id and body.person_id not in {e["person_id"] for e in (event["out"].get("ranked") or {}).get("callable") or []}:
        raise HTTPException(422, "That person is not on this event's call list")
    target = _target(body)
    if body.fresh:
        estimate = run_estimate(body.event_id, body.step, body.person_id, True)
        if not body.confirm_token:
            token, expires = tokens.sign(user["email"], "admin_run", target, estimate["high"], cost_low_usd=estimate["low"])
            return {"needs_confirm": True, "estimate": estimate, "confirm_token": token, "expires_at": expires,
                    "message": f"A fresh run pays for every model call again: about ${estimate['low']:.4f} to ${estimate['high']:.4f}."}
        try:
            payload = tokens.read(body.confirm_token, user["email"])
        except tokens.TokenError as exc:
            raise HTTPException(403, str(exc))
        if payload.get("k") != "admin_run" or payload.get("t") != target:
            raise HTTPException(403, "This confirmation is for a different run. Ask again to get a fresh estimate.")
        allowed, reason = tokens.can_confirm(user["role"], float(payload.get("hi") or 0))
        if not allowed:
            raise HTTPException(403, reason or "Not allowed")
        try:
            tokens.spend(payload)
        except tokens.TokenError as exc:
            raise HTTPException(403, str(exc))
    job = jobs.start(body.event_id, event["path"], step=body.step, person_id=body.person_id, fresh=body.fresh, by=user["email"])
    return {"needs_confirm": False, "job_id": job["job_id"], "event_id": body.event_id, "state": job["state"], "step": job["step"],
            "fresh": bool(job.get("fresh")), "stream_url": f"/api/jobs/{job['job_id']}/stream",
            "log_url": f"/api/admin/jobs/{job['job_id']}/log"}


@router.get("/api/admin/jobs", dependencies=[auth.OPS])
def admin_jobs() -> dict:
    """Latest jobs since the API started, newest first."""
    return {"jobs": jobs.recent(20)}


@router.get("/api/admin/jobs/{job_id}/log", dependencies=[auth.OPS])
async def admin_job_log(job_id: str) -> StreamingResponse:
    """Server-sent events: one `data: {"line": ...}` per output line of the run, ending with {"state": ...}."""
    if jobs.log_snapshot(job_id) is None:
        raise HTTPException(404, "No such job")

    async def gen():
        sent = 0
        while True:
            snap = jobs.log_snapshot(job_id, sent)
            if snap is None:
                return
            new, state = snap
            for line in new:
                yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"
            sent += len(new)
            if state != "running" and not new:
                yield f"data: {json.dumps({'state': state})}\n\n"
                return
            if not new:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@router.get("/api/admin/events/{event_id}/history", dependencies=[auth.OPS])
def admin_history(event_id: str) -> dict:
    """Every run of the event from outputs/runs.csv (newest first), which have a snapshot, and the diff of the last two."""
    if store.find_event(event_id) is None:
        raise HTTPException(404, "No such event")
    snaps = set(rundiff.snapshots(event_id))
    rows = [r for r in store.runs() if r.get("event_id") == event_id]
    runs = [{"run_id": r.get("run_id"), "started_at": r.get("started_at"), "ended_at": r.get("ended_at"),
             "wall_s": float(r["wall_s"]) if r.get("wall_s") else None, "calls": int(r.get("n_llm_calls") or 0),
             "cached_calls": int(r.get("n_cached_calls") or 0), "cost_usd": float(r.get("total_cost_usd") or 0),
             "status": r.get("status") or "unknown", "error": r.get("error") or None, "snapshot": r.get("run_id") in snaps}
            for r in reversed(rows)]
    return {"event_id": event_id, "runs": runs, "diff": rundiff.diff(event_id)}


@router.get("/api/admin/events/{event_id}/diff", dependencies=[auth.OPS])
def admin_diff(event_id: str, older: str | None = Query(None), newer: str | None = Query(None)) -> dict:
    """What changed between two runs that have a snapshot (the last two when not given)."""
    if store.find_event(event_id) is None:
        raise HTTPException(404, "No such event")
    return rundiff.diff(event_id, older, newer)


@router.get("/api/ops/health", dependencies=[auth.OPS])
def ops_health_view() -> dict:
    """Scheduler, sources, caches, today's spend against its caps, Bright Data use and failed runs."""
    return ops_health.health()


@router.get("/api/ops/accuracy", dependencies=[auth.OPS])
def ops_accuracy() -> dict:
    """The last accuracy check (eval.check_people), or {result: null} when it has not run yet."""
    return {"result": accuracy.cached()}


@router.post("/api/ops/accuracy/run", dependencies=[auth.OPS])
def ops_accuracy_run() -> dict:
    """Run the check now (no model calls) and return the fresh result."""
    return {"result": accuracy.run()}
