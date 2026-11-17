"""Run the pipeline for one event as a subprocess and stream its progress.

`run.py --event <path> --step all` prints "STEP <name> start" and "STEP <name> done ..." lines.
Each becomes a job event {step, label, state, seconds, cost_usd, calls, cached}; a done event also
carries {agent, why, runs_on} for the step. The job ends with {state: complete|failed, reason}.

run.py also prints "AGENT {json}" lines (tools/trace.py), one when an agent or code sub-step starts
and one when it ends. Each becomes an agent event {type: "agent", phase: start|done|progress, agent,
parent, label, why, given, runs_on, doing, returns, calls, cached, cost_usd, ms}. Agent events carry
no "step" and no "state" key, so a consumer that only knows step events skips them. The event's previous outputs are copied aside first and
put back when the run fails, so a failed live run keeps the old call list.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from api import store
from api.views import STEP_LABELS
from tools.trace import AGENT_PREFIX
from ui.components import parse_step_line, parse_total_line

BACKUP_DIR = Path(__file__).resolve().parent / "state" / "backup"
STEPS = ("locate", "extract", "people", "rank", "brief", "report")
STEP_DOING = {"locate": "finding the right pages", "extract": "reading the tables", "people": "matching people",
              "rank": "ranking who to call", "brief": "writing call briefs", "report": "assembling the call list"}
JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def running_events() -> set[str]:
    """Event ids with a job still running."""
    with _LOCK:
        return {job["event_id"] for job in JOBS.values() if job["state"] == "running"}


def start(event_id: str, event_path: Path, command: list[str] | None = None, *, step: str = "all",
          person_id: str | None = None, fresh: bool = False, by: str | None = None) -> dict:
    """Start a run (or return the one already running for this event).

    step: "all" or one of STEPS (the admin console). person_id: with step "brief", write that person's brief only.
    fresh: read with an empty model cache (a temp LLM_CACHE_DIR, removed afterwards), so every call is paid for again.
    """
    with _LOCK:
        for job in JOBS.values():
            if job["event_id"] == event_id and job["state"] == "running":
                return job
        job = {"job_id": uuid.uuid4().hex[:12], "event_id": event_id, "state": "running", "events": [], "log": [],
               "started_at": time.time(), "reason": None, "step": step, "person_id": person_id, "fresh": fresh, "by": by}
        JOBS[job["job_id"]] = job
    cmd = command or [sys.executable, str(store.ROOT / "run.py"), "--event", str(event_path), "--step", step]
    if person_id and not command:
        cmd += ["--person", person_id]
    threading.Thread(target=_run, args=(job, cmd), daemon=True).start()
    return job


def recent(limit: int = 20) -> list[dict]:
    """The latest jobs (newest first) without their event lists: job_id, event_id, state, step, fresh, started_at, reason."""
    with _LOCK:
        rows = [{key: job.get(key) for key in ("job_id", "event_id", "state", "step", "person_id", "fresh", "started_at", "reason", "by")}
                for job in JOBS.values()]
    return sorted(rows, key=lambda row: -row["started_at"])[:limit]


def log_snapshot(job_id: str, start_at: int = 0) -> tuple[list[str], str] | None:
    """(log lines from start_at, state) for a job, or None. The log is the run's own output, one line per entry."""
    with _LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return list(job.get("log", [])[start_at:]), job["state"]


def _emit(job: dict, payload: dict) -> None:
    """Append one progress event."""
    with _LOCK:
        job["events"].append({**payload, "at": round(time.time() - job["started_at"], 1)})


def _backup(event_id: str) -> Path | None:
    """Copy outputs/<event_id> aside; None when there is nothing yet."""
    source = store.OUTPUTS_DIR / event_id
    if not source.is_dir():
        return None
    target = BACKUP_DIR / event_id
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return target


def _restore(event_id: str, backup: Path | None) -> None:
    """Put the previous outputs back after a failed run."""
    if backup is None or not backup.is_dir():
        return
    target = store.OUTPUTS_DIR / event_id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(backup, target)


def _plain_reason(lines: list[str], step: str | None) -> str:
    """A one-line reason for a failed run, from the last error-looking line."""
    tail = [line.strip() for line in lines if line.strip()]
    error = next((line for line in reversed(tail) if "Error" in line or "error" in line or "failed" in line), None)
    where = f" while {STEP_DOING.get(step, step)}" if step else ""
    if error and "FetchError" in error:
        return f"A document could not be downloaded{where}. The previous call list is kept."
    if error and ("LLMError" in error or "openrouter" in error.lower()):
        return f"The reading service did not answer{where}. The previous call list is kept."
    detail = (error or (tail[-1] if tail else "no output")).split(": ", 1)[-1][:160]
    return f"Processing stopped{where}: {detail}. The previous call list is kept."


def _run(job: dict, cmd: list[str]) -> None:
    """Thread body: run, parse lines, finish the job."""
    backup = _backup(job["event_id"])
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    cache_dir = None
    if job.get("fresh"):
        cache_dir = tempfile.mkdtemp(prefix="finsight-fresh-llm-")
        env["LLM_CACHE_DIR"] = cache_dir
    single = job.get("step") not in (None, "all")
    if single:
        _emit(job, {"step": job["step"], "label": STEP_LABELS.get(job["step"], job["step"]), "state": "start", "index": 1, "total": 1})
    try:
        _run_process(job, cmd, env, backup, single)
    finally:
        if cache_dir:
            shutil.rmtree(cache_dir, ignore_errors=True)


def _scrub(line: str) -> str:
    """Hide this server's folder paths: the live log shows 'outputs/x/people.json', never '/Users/.../outputs/...'."""
    for root in {str(store.ROOT), str(store.ROOT.resolve())}:
        line = line.replace(root + os.sep, "").replace(root, ".")
    return line


def _log(job: dict, line: str) -> None:
    """Keep one output line for the live log tail (the first 5,000 lines of a run)."""
    with _LOCK:
        if len(job["log"]) < 5000:
            job["log"].append(_scrub(line)[:400])


def _run_process(job: dict, cmd: list[str], env: dict, backup: Path | None, single: bool) -> None:
    """Run the subprocess, turn its lines into job events, and close the job."""
    current, lines, total = job.get("step") if single else None, [], None
    started = time.time()
    try:
        proc = subprocess.Popen(cmd, cwd=str(store.ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env)
    except OSError as exc:
        _finish(job, "failed", f"Processing could not start: {exc}")
        return
    step_info: dict[str, dict] = {}
    for raw in proc.stdout:  # type: ignore[union-attr]
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped and not stripped.startswith(AGENT_PREFIX):
            _log(job, line)
        if stripped.startswith(AGENT_PREFIX):
            agent_event = agent_payload(stripped)
            if agent_event and agent_event.get("kind") == "step":
                step_info[agent_event["agent"]] = agent_event  # merged into the STEP done event below
            elif agent_event:
                _emit(job, agent_event)
            continue
        lines.append(line)
        lines[:] = lines[-200:]
        if stripped.startswith("STEP ") and stripped.endswith(" start"):
            current = stripped.split()[1]
            _emit(job, {"step": current, "label": STEP_LABELS.get(current, current), "state": "start",
                        "index": STEPS.index(current) + 1 if current in STEPS else None, "total": len(STEPS)})
            continue
        done = parse_step_line(stripped)
        if done:
            info = step_info.get(done["step"]) or {}
            _emit(job, {"step": done["step"], "label": STEP_LABELS.get(done["step"], done["step"]), "state": "done",
                        "index": STEPS.index(done["step"]) + 1 if done["step"] in STEPS else None, "total": len(STEPS),
                        "seconds": float(done["seconds"]), "cost_usd": float(done["cost"]),
                        "calls": int(done["calls"]), "cached": int(done["cached"]),
                        "agent": done["step"], "why": info.get("why") or "", "runs_on": info.get("runs_on") or "code"})
            current = None
            continue
        parsed = parse_total_line(stripped)
        if parsed:
            total = parsed
    code = proc.wait()
    if code == 0:
        if single:  # run.py prints no STEP lines for one step: the run's own totals row (outputs/runs.csv) says what it cost
            mine = [r for r in store.runs() if r.get("event_id") == job["event_id"]]
            row = mine[-1] if mine else {}
            seconds, cost = round(time.time() - started, 1), float(row.get("total_cost_usd") or 0)
            _emit(job, {"step": job["step"], "label": STEP_LABELS.get(job["step"], job["step"]), "state": "done", "index": 1,
                        "total": 1, "seconds": seconds, "cost_usd": cost, "calls": int(row.get("n_llm_calls") or 0),
                        "cached": int(row.get("n_cached_calls") or 0), "agent": job["step"], "why": "", "runs_on": "code"})
            total = {"seconds": seconds, "cost": f"{cost:.6f}"}
        _finish(job, "complete", None, total)
        return
    if current:
        _emit(job, {"step": current, "label": STEP_LABELS.get(current, current), "state": "failed"})
    _restore(job["event_id"], backup)
    _finish(job, "failed", _plain_reason(lines, current))


def agent_payload(line: str) -> dict | None:
    """An "AGENT {json}" line as a job event, or None when it does not parse.

    A step span (kind "step") keeps its name in "agent" so _run can fold it into the STEP done
    event. Every other span becomes {type: "agent", phase, agent, parent, ...} with no "step" key.
    """
    try:
        data = json.loads(line[len(AGENT_PREFIX):])
    except ValueError:
        return None
    if not isinstance(data, dict) or not data.get("agent"):
        return None
    if data.get("kind") == "step":
        return {"kind": "step", "agent": data["agent"], "phase": data.get("phase"),
                "why": data.get("why") or "", "runs_on": data.get("runs_on") or "code"}
    keep = ("phase", "agent", "label", "why", "given", "runs_on", "doing", "returns", "status", "calls",
            "cached_calls", "fresh_calls", "tokens_in", "tokens_out", "cost_usd", "ms", "done", "total")
    event = {"type": "agent", "parent": data.get("step"), **{key: data[key] for key in keep if key in data}}
    if "cached_calls" in event:
        event["cached"] = event["cached_calls"]
    return event


def _finish(job: dict, state: str, reason: str | None, total: dict | None = None) -> None:
    """Close the job with a final event."""
    payload = {"state": state, "reason": reason}
    if total:
        payload.update(seconds=float(total["seconds"]), cost_usd=float(total["cost"]))
    _emit(job, payload)
    with _LOCK:
        job["state"], job["reason"] = state, reason


def snapshot(job_id: str, start_at: int = 0) -> tuple[list[dict], str] | None:
    """(events from start_at, state) for a job, or None."""
    with _LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return list(job["events"][start_at:]), job["state"]
