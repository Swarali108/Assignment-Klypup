"""Process an event from the chat: resolve the target, estimate it, and (after a confirm) run the pipeline.

A target is an event id already in the app, or a pasted link. A link that belongs to a known event (its own
documents, or a filing in the discovery index) runs that event; a new link is read first (tools.propose: rules,
then one cheap-model call only if they fail), written as events/<id>.json and then processed. Runs go through
api/jobs (the same subprocess the Events screen uses), and its step events are streamed as chat steps.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date

from pydantic import ValidationError

from agents.spec import EventSpec
from api import jobs, store, views
from api.chat import estimate as est
from api.chat import tools
from tools.netguard import public_url

URL = re.compile(r"https?://[^\s<>\"')]+")
POLL_SECONDS = 0.5
MAX_WAIT_SECONDS = 15 * 60


class TargetError(Exception):
    """The target cannot be processed (message is for the RM)."""


def resolve(target: str) -> dict:
    """{kind: event|link, event_id|url, title}; raises TargetError."""
    target = (target or "").strip()
    if URL.match(target):
        refused = public_url(target)
        if refused:
            raise TargetError(f"That link cannot be read: {refused}.")
        for event in store.load_event_files():
            if any(doc.url == target for doc in event["spec"].documents):
                return _event_target(event["spec"].event_id)
        for item in (store.discovery() or {}).get("items") or []:
            if target == item.get("link") or target in (item.get("documents") or []):
                if item.get("event_id") and store.find_event(item["event_id"]):
                    return _event_target(item["event_id"])
        return {"kind": "link", "url": target, "title": "A new filing from your link"}
    if store.find_event(target):
        return _event_target(target)
    raise TargetError("I could not find that event. Paste the filing's link instead.")


def _event_target(event_id: str) -> dict:
    """A target for an event in the app; refuses types the pipeline cannot read."""
    event = store.find_event(event_id)
    spec = event["spec"]
    if spec.event_type not in store.SUPPORTED_TYPES:
        raise TargetError(f"{views.type_label(spec.event_type)} events are not supported yet.")
    return {"kind": "event", "event_id": event_id, "title": f"{spec.company} · {views.type_label(spec.event_type)}"}


def target_key(target: dict) -> str:
    """What the confirm token binds to."""
    return target.get("event_id") or target["url"]


def estimate(target: dict) -> dict:
    """Pipeline estimate for this target (plus reading the link when it is new)."""
    if target["kind"] == "event":
        found = est.pipeline_estimate(target["event_id"])
        breakdown = found["breakdown"]
    else:
        found = est.pipeline_estimate(None)
        breakdown = [est.propose_estimate()] + found["breakdown"]
    low, high = est.total(breakdown)
    return {"low": low, "high": high, "seconds_low": found["seconds_low"], "seconds_high": found["seconds_high"],
            "breakdown": breakdown, "basis": found["basis"]}


def _new_event_from_link(url: str) -> str:
    """Read a new link and write events/<id>.json; returns the event id. Raises TargetError."""
    from tools.discover import slug
    from tools.propose import existing_event, propose

    proposal = propose(url)
    if proposal.get("error"):
        raise TargetError(f"I could not read that link: {proposal['error']}.")
    if not proposal.get("event_type") or proposal["event_type"] not in store.SUPPORTED_TYPES or not proposal.get("company"):
        raise TargetError("I could not tell what kind of filing this is, or whose. Add it from the Events screen.")
    month = date.today().strftime("%Y%m")
    found = existing_event([url], proposal["company"], proposal["event_type"], month, store.EVENTS_DIR)
    if found:
        return found
    event_id = f"{'_'.join(slug(proposal['company']).split('_')[:6])}_{proposal['event_type']}_{month}"
    if store.find_event(event_id):  # events/ or events/auto/: open it, never overwrite its spec
        return event_id
    spec = {"event_id": event_id, "event_type": proposal["event_type"], "company": proposal["company"],
            "documents": [{"url": url, "doc_type": proposal["doc_type"], "note": "Added from the control tower"}]}
    try:
        spec = EventSpec.model_validate(spec).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise TargetError(f"That filing could not be added: {exc.errors()[0].get('msg', 'invalid')}.") from exc
    try:  # mode "x": fails instead of overwriting if another request wrote the same id meanwhile
        with open(store.EVENTS_DIR / f"{event_id}.json", "x", encoding="utf-8") as handle:
            handle.write(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    except FileExistsError:
        pass
    return event_id


def run(turn, target: dict):
    """Generator: process the target, streaming pipeline steps; returns the tool result (data + cards)."""
    event_id = target.get("event_id")
    if target["kind"] == "link":
        step = yield from turn.begin("Reading the first pages of your link", model="rules")
        offset = _log_offset()
        try:
            event_id = _new_event_from_link(target["url"])
        except TargetError as exc:
            yield from turn.end(step, "failed", str(exc))
            raise
        cost = _spent_since(offset, "add_event_propose")
        yield from turn.end(step, "done", f"Filed as {store.find_event(event_id)['spec'].company}", cost=cost,
                            calls=1 if cost else 0, model=_pipeline_model() if cost else "rules")
    event = store.find_event(event_id)
    models = {row["step"]: row["model"] for row in est.pipeline_estimate(event_id)["breakdown"]}
    job = jobs.start(event_id, event["path"])
    sent, open_steps, waited, final = 0, {}, 0.0, None
    while waited < MAX_WAIT_SECONDS:
        snap = jobs.snapshot(job["job_id"], sent)
        if snap is None:
            break
        new, state = snap
        sent += len(new)
        for item in new:
            if item.get("step") and item.get("state") == "start":
                open_steps[item["step"]] = yield from turn.begin(item["label"], model=None)
            elif item.get("step") and item.get("state") in ("done", "failed"):
                step = open_steps.pop(item["step"], None) or (yield from turn.begin(item["label"]))
                calls = int(item.get("calls") or 0) - int(item.get("cached") or 0)
                model = models.get(item["label"]) if item.get("calls") else None
                detail = f"{item.get('calls', 0)} model calls, {item.get('cached', 0)} from cache" if item.get("calls") else None
                yield from turn.end(step, item["state"], detail, cost=float(item.get("cost_usd") or 0), calls=max(calls, 0),
                                    model=model)
            elif item.get("state") in ("complete", "failed"):
                final = item
        if state != "running" and not new:
            break
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    if not final or final.get("state") != "complete":
        reason = (final or {}).get("reason") or "Processing did not finish."
        raise TargetError(reason)
    result = tools.search_events(company=store.find_event(event_id)["spec"].company)
    events, rm = tools.context()
    fresh = next(e for e in events if e["spec"].event_id == event_id)
    callable_items = views.event_lists(fresh, rm)["callable"] if fresh["processed"] else []
    cards = result["cards"] + ([tools._card("people", f"Who to call: {fresh['spec'].company}", callable_items)]
                               if callable_items else [])
    data = {"event": fresh["spec"].company, "type": views.type_label(fresh["spec"].event_type),
            "people_to_call": len(callable_items), "seconds": final.get("seconds"), "cost_usd": final.get("cost_usd"),
            "top": [tools.compact(i) for i in callable_items[:5]]}
    return {"data": data, "cards": cards}


def _pipeline_model() -> str | None:
    """The pipeline's cheap model (LLM_MODEL)."""
    from tools import llm

    return llm.LLM_MODEL


def _log_offset() -> int:
    from tools import costs

    path = costs.cost_log_path()
    return path.stat().st_size if path.exists() else 0


def _spent_since(offset: int, agent: str) -> float:
    from api.chat.llm import row_cost, rows_after

    return round(sum(row_cost(r) for r in rows_after(offset) if r.get("agent_name") == agent), 6)
