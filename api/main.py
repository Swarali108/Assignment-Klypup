"""FinSight demo API. Run: .venv/bin/python -m uvicorn api.main:app --port 8000

Every GET reads the stored files fresh (mtime cache) so a finished run shows at once.
See api/CONTRACT.md for every response shape.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from agents.spec import EventSpec
from tools.netguard import public_url
from api import ask as ask_mod
from api import brief as brief_mod
from api import auth, db, evidence, jobs, overrides, prefs, rm_state, seed_users, store, team, views, watch
from api.admin import router as admin_router
from api.chat.routes import router as chat_router
from api.discovery_routes import router as discovery_router
from api.enrich_routes import router as enrich_router
from api.trail import router as trail_router
from api.guard import WriteGuard

app = FastAPI(title="FinSight API", version="1.0", docs_url=None, redoc_url=None, openapi_url=None)
# The browser reaches this API only through the web app's /api rewrite (same origin), so there is no CORS.
app.add_middleware(WriteGuard)
app.include_router(chat_router)  # control tower chat: api/CHAT_CONTRACT.md
app.include_router(discovery_router)  # sources, check-now, auto-processing log: api/discovery_routes.py
app.include_router(trail_router)  # GET /api/people/{e}/{p}/trail (api/trail.py)
app.include_router(enrich_router)  # Bright Data enrichment routes (api/enrich_routes.py)
app.include_router(admin_router)  # admin pipeline console, /ops/health, /ops/accuracy: api/CONTRACT.md
app.include_router(brief_mod.router)  # daily brief + since-last-visit: api/brief.py
prefs.install(app)  # /api/me, preferences, client book, and the "In your book" flag
# Tests replace this with a stub; None means "use the model".
ASK_MODEL = None


def _warm_evidence(limit: int = 25) -> None:
    """Render the headline evidence pages of the top calls once, so the first click is instant."""
    try:
        events, rm = store.load_events(), rm_state.all_states()
        for item in views.today_queue(events, rm, limit):
            event = store.find_event(item["event"]["id"])
            card = views.person_card(event, item["person"]["id"], None) if event else None
            for figure in (card or {}).get("amounts") or []:
                for row in figure["inputs"]:
                    for ref in row["evidence"][:1]:
                        if ref["cached"] and ref["pdf_index"]:
                            evidence.render(ref["doc_sha"], int(ref["pdf_index"]), ref["quote"])
    except Exception:  # warming is best effort; a real request renders on demand
        return


@app.on_event("startup")
def _startup() -> None:
    """Create the tables, seed the demo users, and warm the evidence cache in the background (FINSIGHT_WARM=0 skips)."""
    import threading

    from dotenv import load_dotenv

    load_dotenv(store.ROOT / ".env")  # DATABASE_URL / SESSION_SECRET (never printed)
    auth.check_config()  # APP_ENV=production without SESSION_SECRET: refuse to start
    db.ensure_tables()
    seed_users.seed_once()
    if (os.environ.get("FINSIGHT_WARM") or "1") != "0":
        threading.Thread(target=_warm_evidence, daemon=True).start()
    from api import scheduler

    scheduler.start()  # discovery every DISCOVERY_EVERY_HOURS, auto-processing under the daily cap


def _ctx() -> tuple[list[dict], dict]:
    """(events, rm lookup) for one request."""
    return store.load_events(), rm_state.all_states()


def _event_or_404(event_id: str) -> dict:
    """One event, or a 404 with a plain message."""
    event = store.find_event(event_id)
    if event is None:
        raise HTTPException(404, "No such event")
    return event


def _person_in_event_or_404(event_id: str, person_id: str) -> dict:
    """The event, if person_id is a holder named on it (called, entity or context), else a 404: no orphan rows."""
    event = _event_or_404(event_id)
    known = event["processed"] and (views.people_by_id(event).get(person_id) is not None
                                    or any(e.get("person_id") == person_id for g in ("callable", "entities", "context")
                                           for e in (event["out"]["ranked"] or {}).get(g) or []))
    if not known:
        raise HTTPException(404, "No such person in this event")
    return event


class LoginIn(BaseModel):
    """POST /api/auth/login body."""

    email: str
    password: str


def _user_view(user: dict) -> dict:
    """{email, name, role, permissions, onboarded} for the web app (onboarded: the setup guide is done)."""
    return {"email": user["email"], "name": user["name"], "role": user["role"],
            "permissions": auth.permissions_for(user["role"]), "onboarded": prefs.get_preferences(user["email"])["onboarded"],
            "production": auth.is_production()}


@app.get("/api/auth/config")
def auth_config() -> dict:
    """Public: whether this is a production deployment, and the demo accounts the login page may offer."""
    return {"production": auth.is_production(), "demo_accounts": [user[0] for user in seed_users.demo_users()]}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    """Check email and password; set the signed session cookie."""
    seed_users.seed_once()
    row = seed_users.find_user(body.email)
    # Same work and same message whether the email exists or not.
    stored = row["password_hash"] if row else auth.hash_password("not-a-real-password")
    if not auth.verify_password(body.password, stored) or row is None or seed_users.is_blocked_demo(body.email):
        raise HTTPException(401, "That email and password do not match")
    response.set_cookie(auth.COOKIE, auth.make_session(row), max_age=auth.SESSION_SECONDS, httponly=True,
                        samesite="lax", secure=auth.cookie_secure(request), path="/")
    return _user_view(row)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    """Clear the session cookie."""
    response.delete_cookie(auth.COOKIE, path="/", secure=auth.cookie_secure(request), httponly=True, samesite="lax")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = auth.VIEW_USER) -> dict:
    """Who is signed in, and what they may do (401 when nobody is)."""
    return _user_view(user)


@app.get("/api/health")
def health() -> Response:
    """Readiness: the API answers and its database takes a query. 503 with the reason's class name when it does not."""
    try:
        with db.connect() as conn:
            conn.query("SELECT 1 AS one")
    except Exception as exc:  # the URL or password is never echoed, only the kind of failure
        body = {"ok": False, "db": db.backend(), "error": type(exc).__name__}
        return Response(json.dumps(body), status_code=503, media_type="application/json")
    return Response(json.dumps({"ok": True, "db": db.backend()}), media_type="application/json")


@app.get("/api/summary", dependencies=[auth.VIEW])
def summary() -> dict:
    """KPIs for the Today header."""
    events, rm = _ctx()
    return views.summary(events, rm)


@app.get("/api/today", dependencies=[auth.VIEW])
def today(limit: int | None = Query(None, ge=1, le=500)) -> dict:
    """Cross-event call queue, households folded into one slot."""
    events, rm = _ctx()
    items = views.today_queue(events, rm, limit)
    return {"as_of": views.as_of().isoformat(), "count": len(items), "items": items}


@app.get("/api/events", dependencies=[auth.VIEW])
def events_index() -> dict:
    """Every event with status, people count, cash total and documents."""
    events, rm = _ctx()
    running, failures = jobs.running_events(), views.failure_reasons()
    rows = [views.event_summary(e, running, failures, rm) for e in events]
    order = {"processing": 0, "ready": 1, "failed": 2, "scanned": 3, "not_processed": 4, "not_supported": 5}
    rows.sort(key=lambda r: (order.get(r["status"], 9), -(r["people_count"] > 0), r["money_date"]["date_iso"] or "",))
    rows.sort(key=lambda r: (order.get(r["status"], 9), r["people_count"] == 0))
    return {"count": len(rows), "events": rows}


@app.get("/api/events/{event_id}", dependencies=[auth.VIEW])
def event_detail(event_id: str) -> dict:
    """Facts strip for one event."""
    event = _event_or_404(event_id)
    return views.event_detail(event, jobs.running_events(), views.failure_reasons())


@app.get("/api/events/{event_id}/people", dependencies=[auth.VIEW])
def event_people(event_id: str) -> dict:
    """Call list, entities and context holders for one event, with empty_reason."""
    event = _event_or_404(event_id)
    rm = rm_state.all_states()
    lists = views.event_lists(event, rm) if event["processed"] else {"callable": [], "entities": [], "context": []}
    docs = views.documents_view(event)
    return {"event": views.event_ref(event), **lists, "empty_reason": views.empty_reason(event, lists, docs)}


@app.get("/api/events/{event_id}/trace", dependencies=[auth.VIEW])
def event_trace(event_id: str) -> dict:
    """How the call list was built: one record per agent or code step of the last run (tools/trace.py)."""
    from tools.trace import load_trace

    _event_or_404(event_id)
    found = load_trace(event_id, store.OUTPUTS_DIR / event_id)
    if found is None:
        raise HTTPException(404, "This event has not been processed yet")
    return found


@app.get("/api/events/{event_id}/runs", dependencies=[auth.VIEW])
def event_runs(event_id: str) -> dict:
    """Every full run of this event, the first and the latest: cost, time, calls, cached share."""
    from tools.costs import _read_rows
    from tools.runlog import _runs_path
    from tools.trace import event_runs as runs_for

    _event_or_404(event_id)
    rows = [row for row in _read_rows() if row.get("event_id") == event_id]
    return runs_for(event_id, _runs_path(), rows)


@app.get("/api/people/{event_id}/{person_id}", dependencies=[auth.VIEW])
def person(event_id: str, person_id: str) -> dict:
    """The call card."""
    event = _event_or_404(event_id)
    if not event["processed"]:
        raise HTTPException(404, "This event has no people yet")
    rm = rm_state.all_states()
    card = views.person_card(event, person_id, rm.get((event_id, person_id)), rm)
    if card is None:
        raise HTTPException(404, "No such person in this event")
    card["reviewed"] = overrides.for_person(event_id, person_id)  # the small "Reviewed by" note (v3)
    return card


@app.get("/api/evidence/page.png", dependencies=[auth.VIEW])
def evidence_page(doc_sha: str, pdf_index: int = Query(..., ge=1), quote: str | None = None) -> Response:
    """The page image with the quote highlighted; X-Highlight: found | none; X-Highlight-Box: x0,y0,x1,y1 (0..1)."""
    try:
        data, found = evidence.render(doc_sha, pdf_index, quote)
    except FileNotFoundError:
        raise HTTPException(404, "This document is not stored on this machine")
    except IndexError:
        raise HTTPException(404, "That page is not in the document")
    # private: signed-in content, so a shared cache (the CDN in front of the web app) must not keep it.
    headers = {"X-Highlight": "found" if found else "none", "Cache-Control": "private, max-age=3600"}
    if found:
        headers["X-Highlight-Box"] = found
    return Response(data, media_type="image/png", headers=headers)


@app.get("/api/docs/{doc_sha}.pdf", dependencies=[auth.VIEW])
def doc_pdf(doc_sha: str) -> FileResponse:
    """The cached PDF."""
    path = store.pdf_path(doc_sha)
    if path is None:
        raise HTTPException(404, "This document is not stored on this machine")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.get("/api/calendar", dependencies=[auth.VIEW])
def calendar(from_: str | None = Query(None, alias="from"), to: str | None = None) -> dict:
    """Dated money items between from and to (ISO dates, inclusive)."""
    for value in (from_, to):
        if value and not _ISO.match(value):
            raise HTTPException(422, "Dates must be YYYY-MM-DD")
    events, rm = _ctx()
    items = views.calendar(events, rm, from_, to)
    return {"from": from_, "to": to, "as_of": views.as_of().isoformat(), "count": len(items), "items": items}


@app.get("/api/network", dependencies=[auth.VIEW])
def network() -> dict:
    """Relationship graph."""
    events, rm = _ctx()
    return views.network(events, rm)


@app.get("/api/feed", dependencies=[auth.VIEW])
def feed() -> dict:
    """Discovered filings grouped Today / Upcoming / Recent."""
    events, _rm = _ctx()
    return views.feed(events)


@app.get("/api/ops", dependencies=[auth.OPS])
def ops() -> dict:
    """Cost, run time and verification counts per event."""
    events, _rm = _ctx()
    return views.ops(events)


class LinksIn(BaseModel):
    """POST /api/events/from-links body."""

    urls: list[str]


@app.post("/api/events/from-links", dependencies=[auth.PROCESS])
def from_links(body: LinksIn) -> dict:
    """A proposal (document type, event type, company) for each link."""
    from tools.propose import propose

    urls = [u.strip() for u in body.urls if u and u.strip()][:6]
    if not urls:
        raise HTTPException(422, "Paste at least one link")
    proposals = [propose(url) for url in urls]
    companies = [p["company"] for p in proposals if p.get("company")]
    types = [p["event_type"] for p in proposals if p.get("event_type")]
    suggested = {"company": companies[0] if companies else None, "event_type": types[0] if types else None}
    # Additive (Task 6): the id of an event already in the app with one of these links (or the same
    # company, type and month), so the UI can offer "open / process again" instead of a duplicate.
    from tools.propose import existing_event
    from datetime import date

    existing = existing_event(urls, suggested["company"] or "", suggested["event_type"] or "",
                              date.today().strftime("%Y%m"), store.EVENTS_DIR)
    return {"proposals": proposals, "suggested": suggested, "existing_event_id": existing}


@app.post("/api/events", dependencies=[auth.PROCESS])
def create_event(body: dict) -> dict:
    """Validate an event spec and write events/<event_id>.json."""
    try:
        spec = EventSpec.model_validate(body)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(422, f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}")
    for document in spec.documents:
        refused = public_url(document.url)
        if refused:
            raise HTTPException(400, f"{document.url[:80]}: {refused}")
    path = store.EVENTS_DIR / f"{spec.event_id}.json"
    if path.exists() or (store.EVENTS_DIR / "auto" / f"{spec.event_id}.json").exists():
        raise HTTPException(409, "An event with this id already exists")
    path.write_text(json.dumps(spec.model_dump(exclude_none=True), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"event_id": spec.event_id, "created": True}


@app.post("/api/events/{event_id}/run", dependencies=[auth.PROCESS])
def run_event(event_id: str) -> dict:
    """Start processing; returns {job_id}."""
    event = _event_or_404(event_id)
    if event["spec"].event_type not in store.SUPPORTED_TYPES:
        raise HTTPException(422, "This kind of event is not supported yet")
    job = jobs.start(event_id, event["path"])
    return {"job_id": job["job_id"], "event_id": event_id, "state": job["state"],
            "steps": [{"step": step, "label": views.STEP_LABELS[step]} for step in jobs.STEPS],
            "stream_url": f"/api/jobs/{job['job_id']}/stream"}


@app.get("/api/jobs/{job_id}", dependencies=[auth.VIEW])
def job_state(job_id: str) -> dict:
    """All events so far and the state."""
    snap = jobs.snapshot(job_id)
    if snap is None:
        raise HTTPException(404, "No such job")
    return {"job_id": job_id, "state": snap[1], "events": snap[0]}


@app.get("/api/jobs/{job_id}/stream", dependencies=[auth.VIEW])
async def job_stream(job_id: str) -> StreamingResponse:
    """Server-sent events: one `data: {...}` per step event, ending with state complete|failed."""
    if jobs.snapshot(job_id) is None:
        raise HTTPException(404, "No such job")

    async def gen():
        sent = 0
        while True:
            snap = jobs.snapshot(job_id, sent)
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
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


class AskIn(BaseModel):
    """POST /api/ask body."""

    q: str


@app.post("/api/ask", dependencies=[auth.ASK])
def ask(body: AskIn) -> dict:
    """Question -> filters (model or rules) -> people chosen by code."""
    events, rm = _ctx()
    items = views.all_items(events, rm)
    companies = [e["spec"].company for e in events if e["processed"]]
    model = ASK_MODEL if ASK_MODEL is not None else ask_mod.model_filters
    found = ask_mod.ask(body.q, items, companies, model)
    people = views.fold_repeat_trades(found["people"])  # filters judge each trade; then one row per holder and company
    return {**found, "people": people, "count": len(people),
            "explanation": found["explanation"].replace(f"{found['count']} match.", f"{len(people)} match.")}


class RmIn(BaseModel):
    """PUT /api/rm body; omitted fields keep their stored value."""

    status: str | None = None
    note: str | None = None
    follow_up_date: str | None = None
    won_amount_cr: float | None = None  # v3: the amount (Rs Cr) the RM entered when the deal is won


@app.get("/api/rm/{event_id}/{person_id}", dependencies=[auth.VIEW])
def rm_get(event_id: str, person_id: str) -> dict:
    """RM state for one person."""
    return rm_state.get(event_id, person_id)


@app.put("/api/rm/{event_id}/{person_id}")
def rm_put(event_id: str, person_id: str, body: RmIn, user: dict = auth.EDIT_RM_USER) -> dict:
    """Save RM state (who saved it and the first-call moment are kept for the team dashboard)."""
    _person_in_event_or_404(event_id, person_id)
    if body.follow_up_date and not _ISO.match(body.follow_up_date):
        raise HTTPException(422, "follow_up_date must be YYYY-MM-DD")
    if body.status == "won" and body.won_amount_cr is None and (rm_state.get(event_id, person_id).get("won_amount_cr") is None):
        raise HTTPException(422, "Enter the amount won (in crore) when you mark a deal as won")
    if body.status == "follow_up":
        # A follow-up with no date never comes back as a reminder: the new or the stored date must be there.
        date = body.follow_up_date if body.follow_up_date is not None else rm_state.get(event_id, person_id).get("follow_up_date")
        if not date:
            raise HTTPException(422, "Pick a follow-up date to set a follow-up")
    try:
        return rm_state.put(event_id, person_id, body.status, body.note, body.follow_up_date, user["email"],
                            body.won_amount_cr)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/export/calls.csv", dependencies=[auth.EXPORT])
def export_calls() -> PlainTextResponse:
    """CRM-ready CSV."""
    events, rm = _ctx()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(views.CSV_COLUMNS)
    for row in views.export_rows(events, rm):
        writer.writerow([views.csv_cell(c) for c in row])
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="finsight-calls.csv"'})


# ---------- v3: Head of RMs, review queue, watchlists and alerts ----------

@app.get("/api/team", dependencies=[auth.TEAM])
def team_dashboard() -> dict:
    """Outcomes per RM and per event type from the RMs' own call logs."""
    events, rm = _ctx()
    return team.dashboard(events, rm)


@app.get("/api/team/rms", dependencies=[auth.EDIT_RM])
def team_rms() -> dict:
    """Who a person can be assigned to."""
    return {"rms": team.rms()}


@app.get("/api/assignments", dependencies=[auth.VIEW])
def assignments_all() -> dict:
    """'event_id/person_id' -> assigned RM, for every assigned person (small: shown on rows and the person page)."""
    return {"assignments": team.assignments()}


class AssignIn(BaseModel):
    """PUT /api/assignments/{event_id}/{person_id} body; rm_email null clears the assignment."""

    rm_email: str | None = None


@app.put("/api/assignments/{event_id}/{person_id}")
def assign_person(event_id: str, person_id: str, body: AssignIn, user: dict = auth.TEAM_USER) -> dict:
    """Assign a person to an RM (Head of RMs and admin)."""
    _person_in_event_or_404(event_id, person_id)
    try:
        return {"assignment": team.assign(event_id, person_id, body.rm_email, user["email"])}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/review", dependencies=[auth.REVIEW])
def review_queue() -> dict:
    """Open and decided review items (admin / head)."""
    items = overrides.queue(store.load_events())
    return {"open": sum(1 for i in items if not i["decision"]), "decided": sum(1 for i in items if i["decision"]),
            "items": items}


class ReviewIn(BaseModel):
    """POST /api/review/decide body."""

    id: str
    action: str


@app.post("/api/review/decide")
def review_decide(body: ReviewIn, user: dict = auth.REVIEW_USER) -> dict:
    """Confirm / reject / merge: stored in the database and written to outputs/overrides.json, applied at once."""
    try:
        return {"decision": overrides.decide(store.load_events(), body.id, body.action, user)}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.delete("/api/review", dependencies=[auth.REVIEW])
def review_undo(id: str) -> dict:
    """Take a decision back."""
    return {"undone": overrides.undo(id)}


@app.get("/api/watch")
def watch_list(user: dict = auth.VIEW_USER) -> dict:
    """What this user follows."""
    return {"follows": watch.follows(user["email"])}


@app.get("/api/watch/status")
def watch_status(kind: str, event_id: str, person_id: str | None = None, user: dict = auth.VIEW_USER) -> dict:
    """Is this person / company followed by me?"""
    return watch.status(user["email"], kind, event_id, person_id)


class FollowIn(BaseModel):
    """POST /api/watch body: kind person (event_id + person_id) or company (event_id)."""

    kind: str
    event_id: str
    person_id: str | None = None


@app.post("/api/watch")
def watch_add(body: FollowIn, user: dict = auth.VIEW_USER) -> dict:
    """Follow a person or a company."""
    try:
        return watch.follow(user["email"], body.kind, body.event_id, body.person_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.delete("/api/watch")
def watch_remove(kind: str, key: str, user: dict = auth.VIEW_USER) -> dict:
    """Stop following."""
    watch.unfollow(user["email"], kind, key)
    return {"ok": True}


@app.get("/api/alerts")
def alerts_list(user: dict = auth.VIEW_USER) -> dict:
    """The bell: {unread, items}, worked out from the current data on every call."""
    return watch.alerts(user["email"])


class ReadIn(BaseModel):
    """POST /api/alerts/read body; ids null marks everything read."""

    ids: list[str] | None = None


@app.post("/api/alerts/read")
def alerts_read(body: ReadIn, user: dict = auth.VIEW_USER) -> dict:
    """Mark alerts read."""
    return {"changed": watch.mark_read(user["email"], body.ids)}
