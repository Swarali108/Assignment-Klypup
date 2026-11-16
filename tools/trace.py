"""The agent trace: one record per agent or code step of a pipeline run.

A run (run.py --step all) opens tracing(). Each step and each agent inside it is a span:

    with agent("verify_waca", label=..., why=..., given=..., runs_on="code") as rec:
        ...
        rec["returns"] = {"kept": 15, "rejected": 0}

A span prints one "AGENT {json}" line when it starts and one when it ends, so api/jobs.py can
light up the agent tree while the run is going. It also remembers which cost_log.csv rows of
this run were written while it was open. build_trace() then gives every cost row of the run to
exactly one record (the innermost open span; a row outside every agent goes to its step's
"other model calls" record), so the trace totals always equal the run's cost and calls.

No tracer open (a test calling an agent directly) means every span is a no-op.

For an event processed before traces existed, trace_from_logs() rebuilds a coarser trace from
timeline.json, the outputs on disk and the cost log, with the same record shape.
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from tools.costs import run_rows

AGENT_PREFIX = "AGENT "
TRACE_VERSION = 1
_ACTIVE: ContextVar["Tracer | None"] = ContextVar("trace", default=None)

# Plain words per step, for a step record and the live tree.
STEP_LABELS = {"locate": "Find the right pages", "extract": "Read the tables", "people": "Match people and families",
               "rank": "Rank who to call", "brief": "Write call briefs", "report": "Assemble the call list"}

# Plain words per extract section, for agent labels ("Read: average cost of shares").
SECTION_WORDS = {
    "selling_shareholders": "selling shareholders", "seller_amounts": "shares each seller offers",
    "waca": "average cost of shares", "promoter_holding": "promoter holdings",
    "shareholding_pattern": "shareholding pattern", "offer_structure": "offer size and structure",
    "price": "offer price", "timetable": "offer timetable", "announcement": "exchange notice",
    "allotment": "allotment notice", "buyback_terms": "buyback terms", "promoter_intention": "promoter intention",
    "ofs_terms": "sale terms", "ofs_sellers": "sellers", "kmp": "key people", "esop": "employee stock options",
    "lock_in": "lock-in rules",
}


DOC_WORDS = {"rhp": "red herring prospectus", "prospectus": "prospectus", "letter_of_offer": "letter of offer",
             "public_announcement": "public announcement", "announcement": "exchange notice", "news": "news article"}


def doc_words(doc_type: str) -> str:
    """Plain words for a document type ("rhp" -> "red herring prospectus")."""
    return DOC_WORDS.get(doc_type, doc_type.replace("_", " "))


def section_words(section: str) -> str:
    """Plain words for a section key; unknown keys read as their words."""
    return SECTION_WORDS.get(section, section.replace("_", " "))


class Tracer:
    """Spans of one run, in the order they opened. Rows are indexes into run_rows(run_id)."""

    def __init__(self, run_id: str, event_id: str, emit: bool = True):
        self.run_id = run_id
        self.event_id = event_id
        self.emit = emit
        self.spans: list[dict] = []
        self.step: str | None = None
        self.started = time.perf_counter()
        self.started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def row_count(self) -> int:
        """Cost rows this run has written so far."""
        return len(run_rows(self.run_id))

    def print(self, payload: dict) -> None:
        """One AGENT line on stdout, flushed, for the job stream."""
        if self.emit:
            sys.stdout.write(AGENT_PREFIX + json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()


def active() -> Tracer | None:
    """The open tracer, or None."""
    return _ACTIVE.get()


@contextmanager
def tracing(run_id: str, event_id: str, emit: bool = True):
    """Open a tracer for one run."""
    tracer = Tracer(run_id, event_id, emit)
    token = _ACTIVE.set(tracer)
    try:
        yield tracer
    finally:
        _ACTIVE.reset(token)


@contextmanager
def step(name: str, why: str = ""):
    """A pipeline step (locate, extract, ...). Agents opened inside it belong to it."""
    with _span(name, kind="step", label=STEP_LABELS.get(name, name), why=why, given="", runs_on="code") as rec:
        tracer = active()
        previous = tracer.step if tracer else None
        if tracer:
            tracer.step = name
        try:
            yield rec
        finally:
            if tracer:
                tracer.step = previous


@contextmanager
def agent(name: str, *, label: str, why: str, given: str, runs_on: str = "code", doing: str = ""):
    """One agent or code sub-step. Set rec["returns"] (counts) before the block ends."""
    with _span(name, kind="agent", label=label, why=why, given=given, runs_on=runs_on, doing=doing) as rec:
        yield rec


def progress(name: str, doing: str, **extra) -> None:
    """A one-line "now doing" update for an open agent (brief 7 of 23)."""
    tracer = active()
    if tracer is None:
        return
    tracer.print({"phase": "progress", "agent": name, "step": tracer.step, "doing": doing, **extra})


@contextmanager
def _span(name: str, *, kind: str, label: str, why: str, given: str, runs_on: str, doing: str = ""):
    """Record one span and print its start and end lines. A no-op without a tracer."""
    tracer = active()
    rec: dict = {"name": name, "kind": kind, "label": label, "why": why, "given": given, "runs_on": runs_on,
                 "doing": doing, "returns": {}, "status": "ok"}
    if tracer is None:
        yield rec
        return
    rec["step"] = name if kind == "step" else tracer.step
    rec["row_start"] = tracer.row_count()
    rec["order"] = len(tracer.spans)
    tracer.spans.append(rec)
    started = time.perf_counter()
    rec["start_ms"] = round((started - tracer.started) * 1000, 1)
    tracer.print({"phase": "start", "agent": name, "kind": kind, "step": rec["step"], "label": label, "why": why,
                  "given": given, "runs_on": runs_on, "doing": doing or label})
    try:
        yield rec
    except BaseException as exc:
        rec["status"] = "failed"
        rec["error"] = str(exc)[:300]
        raise
    finally:
        rec["ms"] = round((time.perf_counter() - started) * 1000, 1)
        rec["row_end"] = tracer.row_count()
        rows = run_rows(tracer.run_id)[rec["row_start"]:rec["row_end"]]
        money = _money(rows)
        tracer.print({"phase": "done", "agent": name, "kind": kind, "step": rec["step"], "label": label,
                      "status": rec["status"], "returns": rec["returns"], "ms": rec["ms"],
                      "runs_on": _runs_on(runs_on, rows), **money})


# ---------- building trace.json ----------

def build_trace(tracer: Tracer) -> dict:
    """trace.json for a finished run: records, per-step rollups and totals that equal the cost log."""
    rows = run_rows(tracer.run_id)
    owner = _row_owners(tracer.spans, len(rows))
    records: list[dict] = []
    by_order: dict[int, dict] = {}
    for span in tracer.spans:
        record = _public(span)
        by_order[span["order"]] = record
        records.append(record)
    leftovers: dict[str, list[dict]] = {}
    for index, row in enumerate(rows):
        order = owner[index]
        if order is None:
            leftovers.setdefault("", []).append(row)
            continue
        span = tracer.spans[order]
        if span["kind"] == "step":
            leftovers.setdefault(span["name"], []).append(row)
            continue
        by_order[order].setdefault("_rows", []).append(row)
    for step_name, step_rows in leftovers.items():
        records.append(_other_record(step_name, step_rows))
    for record in records:
        _fill_money(record, record.pop("_rows", []))
    total_ms = round((time.perf_counter() - tracer.started) * 1000, 1)
    return _assemble(tracer.event_id, tracer.run_id, tracer.started_at, total_ms, records, rows, source="live")


def write_trace(tracer: Tracer, folder: Path) -> Path:
    """Write outputs/<event_id>/trace.json and return the path."""
    out = Path(folder) / "trace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_trace(tracer), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _row_owners(spans: list[dict], n_rows: int) -> list[int | None]:
    """For each cost row, the innermost span open when it was written (the latest-opened that contains it)."""
    owner: list[int | None] = [None] * n_rows
    for span in spans:  # opened in order, so a later (inner) span overwrites its parent
        for index in range(span["row_start"], min(span.get("row_end", span["row_start"]), n_rows)):
            owner[index] = span["order"]
    return owner


def _public(span: dict) -> dict:
    """A span as it goes in trace.json (no row bookkeeping)."""
    keep = ("name", "kind", "step", "label", "why", "given", "returns", "runs_on", "status", "ms", "start_ms", "error")
    record = {key: span[key] for key in keep if key in span}
    record["order"] = span["order"]
    return record


def _other_record(step_name: str, rows: list[dict]) -> dict:
    """Model calls made inside a step but outside every named agent (kept so totals balance)."""
    return {"name": f"{step_name or 'run'}_other", "kind": "agent", "step": step_name or None,
            "label": "Other model calls", "why": "model calls not inside a named agent", "given": "",
            "returns": {}, "runs_on": "code", "status": "ok", "ms": round(sum(_latency(r) for r in rows) * 1000, 1),
            "order": 10_000, "_rows": rows}


def _fill_money(record: dict, rows: list[dict]) -> None:
    """calls, cached calls, tokens, cost and the model ids for one record's own rows."""
    record.update(_money(rows))
    record["runs_on"] = _runs_on(record.get("runs_on") or "code", rows)


def _money(rows: list[dict]) -> dict:
    """Totals for a list of cost rows. A blank cost (unpriced) counts as 0 and is flagged."""
    cached = sum(1 for row in rows if _is_cached(row))
    return {
        "calls": len(rows),
        "cached_calls": cached,
        "fresh_calls": len(rows) - cached,
        "failed_calls": sum(1 for row in rows if (row.get("status") or "").strip() == "error"),
        "unpriced_calls": sum(1 for row in rows if not (row.get("cost_usd") or "").strip()),
        "tokens_in": sum(_int(row.get("input_tokens")) for row in rows),
        "tokens_out": sum(_int(row.get("output_tokens")) for row in rows),
        "cost_usd": round(sum(_float(row.get("cost_usd")) for row in rows), 6),
        "model_s": round(sum(_latency(row) for row in rows), 3),
    }


def _runs_on(declared: str, rows: list[dict]) -> str:
    """The model id(s) that actually answered, else what the span declared ("code")."""
    models = sorted({(row.get("model") or "").strip() for row in rows if (row.get("model") or "").strip()})
    if not models:
        return declared
    if declared == "code":
        return "code + " + ", ".join(models)
    return ", ".join(models)


def _assemble(event_id: str, run_id: str, started_at: str, total_ms: float, records: list[dict],
              rows: list[dict], source: str) -> dict:
    """The trace document: records in run order, step rollups, totals and the cost-log check."""
    records.sort(key=lambda r: (r.get("order", 0)))
    agents = [r for r in records if r["kind"] != "step"]
    totals = _sum_records(agents)
    log = _money(rows)
    steps = []
    for step_rec in (r for r in records if r["kind"] == "step"):
        mine = [r for r in agents if r.get("step") == step_rec["name"]]
        step_rec.update(_sum_records(mine))
        models = sorted({m for r in mine for m in _models_of(r)})
        step_rec["runs_on"] = ", ".join(models) if models else "code"
        step_rec["agents"] = [r["name"] for r in mine]
        steps.append(step_rec)
    return {
        "version": TRACE_VERSION,
        "event_id": event_id,
        "run_id": run_id,
        "started_at": started_at,
        "source": source,
        "total_ms": total_ms,
        "totals": {**totals, "ms": total_ms},
        "cost_log": {"calls": log["calls"], "cached_calls": log["cached_calls"], "cost_usd": log["cost_usd"]},
        "balanced": totals["calls"] == log["calls"] and abs(totals["cost_usd"] - log["cost_usd"]) < 1e-9,
        "steps": steps,
        "agents": agents,
    }


def _sum_records(records: list[dict]) -> dict:
    """Add the money fields of several records."""
    keys = ("calls", "cached_calls", "fresh_calls", "failed_calls", "unpriced_calls", "tokens_in", "tokens_out")
    out = {key: sum(int(r.get(key) or 0) for r in records) for key in keys}
    out["cost_usd"] = round(sum(float(r.get("cost_usd") or 0) for r in records), 6)
    return out


def _models_of(record: dict) -> list[str]:
    """Model ids named in a record's runs_on."""
    text = (record.get("runs_on") or "").replace("code + ", "")
    return [part.strip() for part in text.split(",") if part.strip() and part.strip() != "code"]


def _is_cached(row: dict) -> bool:
    return (row.get("cached") or "").strip().lower() == "true"


def _int(value) -> int:
    try:
        return int(float(str(value or "0").strip() or 0))
    except ValueError:
        return 0


def _float(value) -> float:
    try:
        return float(str(value or "").strip() or 0)
    except ValueError:
        return 0.0


def _latency(row: dict) -> float:
    return _float(row.get("latency_s"))


# ---------- a trace for a run that had no tracer ----------

def trace_from_logs(event_id: str, folder: Path) -> dict | None:
    """Rebuild a trace from timeline.json, the outputs on disk and the cost log. None without a timeline.

    Coarser than a live trace: one record per model agent name (extract_<section>, identity, brief)
    plus one per code step, and agent times are model seconds, not wall time.
    """
    folder = Path(folder)
    timeline = _read(folder / "timeline.json")
    if not timeline or not timeline.get("run_id"):
        return None
    run_id = timeline["run_id"]
    rows = run_rows(run_id)
    outputs = {name: _read(folder / f"{name}.json") for name in ("locate", "extract", "people", "ranked", "briefs")}
    records: list[dict] = []
    order = 0
    for step_row in timeline.get("steps") or []:
        name = step_row["step"]
        records.append({"name": name, "kind": "step", "step": name, "label": STEP_LABELS.get(name, name),
                        "why": "", "given": "", "returns": {}, "runs_on": "code", "status": "ok",
                        "ms": round(float(step_row.get("seconds") or 0) * 1000, 1), "order": order})
        order += 1
        for record in _rebuilt_agents(name, rows, outputs):
            record["order"] = order
            order += 1
            records.append(record)
    claimed = {id(row) for record in records for row in record.get("_rows", [])}
    stray = [row for row in rows if id(row) not in claimed]
    if stray:
        records.append(_other_record("", stray))
    for record in records:
        if record["kind"] != "step":
            _fill_money(record, record.pop("_rows", []))
            if not record.get("ms"):
                record["ms"] = round(float(record.get("model_s") or 0) * 1000, 1)
    _single_agent_times(records)
    total_ms = round(float(timeline.get("total_s") or 0) * 1000, 1)
    started_at = rows[0].get("timestamp", "") if rows else ""
    return _assemble(event_id, run_id, started_at, total_ms, records, rows, source="rebuilt from logs")


def _single_agent_times(records: list[dict]) -> None:
    """A rebuilt step with one agent gives that agent the step's wall time."""
    for step_rec in (r for r in records if r["kind"] == "step"):
        mine = [r for r in records if r["kind"] != "step" and r.get("step") == step_rec["name"]]
        if len(mine) == 1:
            mine[0]["ms"] = step_rec.get("ms") or mine[0].get("ms") or 0.0


def _rebuilt_agents(step_name: str, rows: list[dict], outputs: dict) -> list[dict]:
    """The agent records one step of an old run would have had, from its cost rows and outputs."""
    if step_name == "locate":
        located = outputs.get("locate") or {}
        docs = located.get("documents") or []
        pages = sum(int(d.get("page_count") or 0) for d in docs)
        sections = located.get("sections") or {}
        found = sum(1 for hits in sections.values() if hits)
        return [_code_record("locate", "locate", "Score every page for each section", "the event type's section list",
                             f"{len(docs)} documents, {pages} pages", {"sections_found": found, "sections": len(sections)})]
    if step_name == "extract":
        extracted = outputs.get("extract") or {}
        out = []
        counts = extracted.get("counts") or {}
        chosen = extracted.get("chosen_pages") or {}
        for section, count in counts.items():
            mine = [r for r in rows if r.get("agent_name") == f"extract_{section}"]
            pages = chosen.get(section) or []
            record = _code_record(f"extract_{section}", "extract", f"Read: {section_words(section)}",
                                  (extracted.get("page_choice") or {}).get(section, ""),
                                  f"{len(pages)} pages" + (f" (pdf {', '.join(str(p.get('pdf_index')) for p in pages[:6])})" if pages else ""),
                                  {"proposed": count.get("proposed", 0), "kept": count.get("kept", 0),
                                   "rejected": count.get("rejected", 0)})
            record["_rows"] = mine
            record["runs_on"] = "model"
            if not record["why"] or record["why"] == "top pages":
                record["why"] = "these pages scored highest for this table" if section in (extracted.get("page_choice") or {}) \
                    else "short notice: its first pages are read whole"
            if not mine:
                record["status"] = "skipped"
                record["runs_on"] = "skipped"
                record["why"] = "no page scored for this section, so no call"
            out.append(record)
        return out
    if step_name == "people":
        people = outputs.get("people") or {}
        counts = people.get("counts") or {}
        record = _code_record("match_people", "people", "Match the same person across tables", "rows kept by verify",
                              f"{len((outputs.get('extract') or {}).get('rows') or [])} rows",
                              {"people": counts.get("people", 0), "merges": counts.get("identity_merges", 0),
                               "model_asks": counts.get("llm_asks", 0)})
        record["_rows"] = [r for r in rows if r.get("agent_name") == "identity"]
        return [record]
    if step_name == "rank":
        ranked = outputs.get("ranked") or {}
        return [_code_record("rank", "rank", "Rank who to call", "money in hand ranks above money later", "the matched people",
                             {"callable": len(ranked.get("callable") or []), "entities": len(ranked.get("entities") or [])})]
    if step_name == "brief":
        briefs = (outputs.get("briefs") or {}).get("briefs") or []
        sources = [b.get("brief_source") for b in briefs]
        record = _code_record("brief", "brief", "Write a checked call brief per person", "one per callable person",
                              f"{len(briefs)} people", {"model": sources.count("llm"), "template": sources.count("template")})
        record["runs_on"] = "model"
        record["_rows"] = [r for r in rows if r.get("agent_name") == "brief"]
        return [record]
    if step_name == "report":
        return [_code_record("report", "report", "Assemble the call list and cost file", "the last step", "the checked results", {})]
    return []


def _code_record(name: str, step_name: str, label: str, why: str, given: str, returns: dict) -> dict:
    return {"name": name, "kind": "agent", "step": step_name, "label": label, "why": why, "given": given,
            "returns": returns, "runs_on": "code", "status": "ok", "ms": 0.0}


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_trace(event_id: str, folder: Path) -> dict | None:
    """trace.json when present and matching the last timeline, else one rebuilt from logs."""
    folder = Path(folder)
    stored = _read(folder / "trace.json")
    timeline = _read(folder / "timeline.json") or {}
    if stored and (not timeline.get("run_id") or stored.get("run_id") == timeline.get("run_id")):
        return stored
    return trace_from_logs(event_id, folder)


# ---------- first run vs latest ----------

def event_runs(event_id: str, runs_csv: Path, cost_rows: list[dict]) -> dict:
    """Every full pipeline run of one event (from outputs/runs.csv), with the first and the latest.

    A full run is one whose cost rows include an extract call (run.py --step all always reads
    the tables, from cache or not). Step-only reruns are left out of first/latest.
    """
    import csv

    if not Path(runs_csv).is_file():
        return {"event_id": event_id, "runs": [], "first": None, "latest": None, "count": 0}
    by_run: dict[str, list[dict]] = {}
    for row in cost_rows:
        by_run.setdefault(row.get("run_id") or "", []).append(row)
    with Path(runs_csv).open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("event_id") == event_id]
    runs = []
    for row in rows:
        mine = by_run.get(row["run_id"], [])
        # Full: it read the tables. Clean: every call priced and none failed (an early run that
        # failed before the price table existed must not pose as the "first run" at $0).
        full = any((r.get("agent_name") or "").startswith("extract_") for r in mine)
        clean = all((r.get("cost_usd") or "").strip() and (r.get("status") or "").strip() != "error" for r in mine)
        calls = _int(row.get("n_llm_calls"))
        cached = _int(row.get("n_cached_calls"))
        runs.append({"run_id": row["run_id"], "started_at": row.get("started_at"), "status": row.get("status") or "",
                     "full": full, "clean": clean, "seconds": round(_float(row.get("wall_s")), 1), "calls": calls, "cached_calls": cached,
                     "cached_share": round(cached / calls, 3) if calls else None,
                     "cost_usd": round(_float(row.get("total_cost_usd")), 6)})
    full_ok = [r for r in runs if r["full"] and r["clean"] and r["status"] in ("ok", "")]
    first = full_ok[0] if full_ok else None
    latest = full_ok[-1] if full_ok else None
    saved = None
    if first and latest and first["run_id"] != latest["run_id"]:
        saved = {"cost_usd": round(first["cost_usd"] - latest["cost_usd"], 6),
                 "seconds": round(first["seconds"] - latest["seconds"], 1)}
    return {"event_id": event_id, "count": len(runs), "runs": runs[-20:], "first": first, "latest": latest,
            "saved_vs_first": saved}
