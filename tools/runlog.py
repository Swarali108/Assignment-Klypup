"""One row per run, written when the run scope exits.

The totals come from cost_log.csv rows with this run_id. wall_s is the time
inside the scope, not the sum of model latencies.
"""

from __future__ import annotations

import csv
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from tools.costs import cost_log_path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    "run_id",
    "event_id",
    "started_at",
    "ended_at",
    "wall_s",
    "n_llm_calls",
    "n_cached_calls",
    "total_cost_usd",
    "status",
    "error",
]
_current_run: ContextVar[str | None] = ContextVar("run_id", default=None)


def current_run_id() -> str:
    """Return the run id of the active scope, or RUN_ID from the environment."""
    scoped = _current_run.get()
    if scoped:
        return scoped
    return os.environ.get("RUN_ID", "").strip()


@contextmanager
def run_scope(run_id: str, event_id: str):
    """Mark model calls with run_id, then append one totals row to outputs/runs.csv."""
    token = _current_run.set(run_id)
    started_at = _now()
    started = time.perf_counter()
    caught: BaseException | None = None
    try:
        yield
    except BaseException as exc:
        caught = exc
        raise
    finally:
        wall_s = time.perf_counter() - started
        ended_at = _now()
        _current_run.reset(token)
        _append_run(run_id, event_id, started_at, ended_at, wall_s, caught)


def _runs_path() -> Path:
    """Return the runs CSV. Tests set RUNS_CSV_PATH."""
    override = os.environ.get("RUNS_CSV_PATH", "").strip()
    return Path(override) if override else ROOT / "outputs" / "runs.csv"


def _append_run(
    run_id: str,
    event_id: str,
    started_at: str,
    ended_at: str,
    wall_s: float,
    caught: BaseException | None,
) -> None:
    """Append one run. status is error when the scope raised or a model call failed."""
    rows = _cost_rows(run_id)
    total = 0.0
    cached = 0
    for row in rows:
        if (row.get("cached") or "").strip().lower() == "true":
            cached += 1
        text = (row.get("cost_usd") or "").strip()
        if text:
            total += float(text)
    status, error = _run_status(rows, caught)
    path = _runs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _prepare_runs(path)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "run_id": run_id,
                "event_id": event_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "wall_s": f"{wall_s:.3f}",
                "n_llm_calls": len(rows),
                "n_cached_calls": cached,
                "total_cost_usd": f"{total:.6f}",
                "status": status,
                "error": error,
            }
        )


def _run_status(rows: list[dict], caught: BaseException | None) -> tuple[str, str]:
    """ok when the scope finished and no model call logged an error."""
    if caught is not None:
        return "error", str(caught)
    for row in rows:
        if (row.get("status") or "").strip() == "error":
            return "error", (row.get("error") or "").strip() or "model call failed"
    return "ok", ""


def _prepare_runs(path: Path) -> None:
    """Add status and error to an existing header so new rows line up.

    Rows written before those columns existed get a blank status. Blank means
    unknown, not a successful run.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return
    header = rows[0]
    changed = False
    for name in ("status", "error"):
        if name in header:
            continue
        header.append(name)
        for row in rows[1:]:
            if len(row) == len(header) - 1:
                row.append("")
        changed = True
    if not changed:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def _cost_rows(run_id: str) -> list[dict]:
    path = cost_log_path()
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("run_id") == run_id]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_ranked(run_id: str, event_folder: Path) -> Path | None:
    """Keep a copy of the event's ranked.json as <event_folder>/runs/<run_id>.json, so two runs can be compared.

    Returns the path, or None when there is no ranked.json (a run that stopped before ranking) or it cannot be copied.
    """
    source = Path(event_folder) / "ranked.json"
    if not run_id or not source.is_file():
        return None
    target = Path(event_folder) / "runs" / f"{run_id}.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    except OSError:
        return None
    return target
