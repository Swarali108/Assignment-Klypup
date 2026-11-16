"""Discovery on a timer while the API runs, then auto-processing under a daily spend cap.

    start()            called once at API startup. When DISCOVERY_ENABLED is not 0, the first
                       process to take the scheduler lock (api/state/scheduler.lock) runs the
                       loop: one cycle every DISCOVERY_EVERY_HOURS (default 3). Other processes
                       (a second uvicorn worker) see the lock taken and stay idle.
    run_cycle(...)     one cycle: tools.discover.refresh (SEBI, plus NSE/BSE when
                       EXCHANGE_SOURCES=on), then new or changed supported events, oldest first,
                       while today's auto spend stays under AUTO_PROCESS_DAILY_CAP_USD (default
                       1.00). An event whose estimate does not fit waits as "needs_approval".
                       Only one cycle runs at a time (api/state/discovery-run.lock), whether the
                       timer or "Check for new filings now" started it.
    check_estimate()   what a check would cost, from measured history. No network, no model, no writes.

Spend is read back from cost_log.csv after every run: rows whose run_id starts with "auto-" and
whose timestamp (UTC) falls on today in CAP_TIMEZONE. Before each run the event's estimate
(the costliest comparable run so far) must fit in what is left of the cap, so a run cannot
start that would be expected to cross it. A run that costs more than any run before it can
still overshoot by that difference; then nothing more starts today.
"""

from __future__ import annotations

import csv
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from config import signals as cfg
from tools import costs

STATE_DIR = Path(__file__).resolve().parent / "state"
SCHEDULER_LOCK = STATE_DIR / "scheduler.lock"
RUN_LOCK = STATE_DIR / "discovery-run.lock"
AUTO_PREFIX = "auto-"
LOG_KEEP = 200
# What one cheap-model classification of one title costs at most, when none is logged yet:
# about 400 prompt tokens and 40 answer tokens at the cheap model's price, rounded up.
CLASSIFY_FALLBACK_USD = 0.0002


# ---------- settings ----------

def _env_float(name: str, default: float) -> float:
    """A float from the environment; the default when unset or unreadable."""
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def settings() -> dict:
    """The scheduler's settings: env vars over config/signals.py defaults."""
    return {
        "enabled": os.environ.get("DISCOVERY_ENABLED", "1").strip().lower() not in ("0", "off", "false", "no"),
        "every_hours": max(0.05, _env_float("DISCOVERY_EVERY_HOURS", cfg.DISCOVERY_EVERY_HOURS)),
        "since_days": max(1.0, _env_float("DISCOVERY_SINCE_DAYS", cfg.DISCOVERY_SINCE_DAYS)),
        "cap_usd": max(0.0, _env_float("AUTO_PROCESS_DAILY_CAP_USD", cfg.AUTO_PROCESS_DAILY_CAP_USD)),
        "timezone": cfg.CAP_TIMEZONE,
    }


# ---------- locks ----------

class FileLock:
    """An exclusive, non-blocking lock on a file (flock on Unix, msvcrt on Windows).

    The operating system drops it when the process ends, so a crash never leaves a stale lock.
    flock belongs to the open file, so two FileLocks on one path conflict even in one process.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> bool:
        """Take the lock; False at once when someone else holds it."""
        if self._handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        """Let go of the lock (closing the file releases it)."""
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self._handle.close()
        self._handle = None

    @property
    def held(self) -> bool:
        """True while this object holds the lock."""
        return self._handle is not None


# ---------- spend ----------

def local_day(now: datetime | None = None) -> str:
    """Today's date (YYYY-MM-DD) in CAP_TIMEZONE."""
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(cfg.CAP_TIMEZONE)).date().isoformat()


def _row_cost(row: dict) -> float:
    """What a cost-log row spent: OpenRouter's charge when logged, else our estimate, else 0."""
    for key in ("charged_usd", "cost_usd"):
        text = (row.get(key) or "").strip()
        if text:
            try:
                return float(text)
            except ValueError:
                continue
    return 0.0


def _row_day(row: dict) -> str | None:
    """The CAP_TIMEZONE day of a cost-log row's UTC timestamp, or None when unreadable."""
    try:
        stamp = datetime.strptime((row.get("timestamp") or "").strip(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return local_day(stamp)


def auto_rows(day: str | None = None) -> list[dict]:
    """cost_log.csv rows of automatic runs (run_id starting "auto-") on one day (default today)."""
    path = costs.cost_log_path()
    if not path.is_file():
        return []
    wanted = day or local_day()
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle)
                if (row.get("run_id") or "").startswith(AUTO_PREFIX) and _row_day(row) == wanted]


def today_auto_spend(day: str | None = None) -> float:
    """US$ spent by automatic runs today (CAP_TIMEZONE), from cost_log.csv."""
    return round(sum(_row_cost(row) for row in auto_rows(day)), 6)


# ---------- estimates ----------

def classify_estimate(n_items: int) -> float:
    """The most sorting n unsettled titles with the cheap model could cost (costliest logged call × n)."""
    path = costs.cost_log_path()
    seen = []
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as handle:
            seen = [_row_cost(row) for row in csv.DictReader(handle)
                    if row.get("agent_name") == "discover_classify" and row.get("cached") != "true"]
    per_item = max(seen) if seen else CLASSIFY_FALLBACK_USD
    return round(per_item * max(0, n_items), 6)


def event_estimate(event_id: str) -> dict:
    """{low, high, basis} for processing one event, from api/chat/estimate.py's measured history."""
    from api.chat.estimate import pipeline_estimate

    estimate = pipeline_estimate(event_id)
    return {"low": float(estimate["low"]), "high": float(estimate["high"]), "basis": estimate["basis"]}


def _outputs_dir() -> Path:
    from api import store

    return store.OUTPUTS_DIR


def _events_dir() -> Path:
    from api import store

    return store.EVENTS_DIR


def pending_events(report: dict | None, outputs_dir: Path | None = None) -> list[dict]:
    """Events the next cycle would try to process, oldest first (tools.discover.candidates)."""
    from tools import discover

    if not report:
        return []
    days = discover.first_published(report)
    found = discover.candidates(report, outputs_dir or _outputs_dir())
    return sorted(found, key=lambda event: (days.get(event["event_id"]) or "9999", event["event_id"]))


def check_estimate(estimator: Callable[[str], dict] = event_estimate) -> dict:
    """What "Check for new filings now" would do and cost. Reads files only: no network, no model, no writes.

    ceiling_usd is the most the check may spend: what is left of today's cap. Events already known
    to be waiting are listed with their measured cost range and whether they fit; filings the
    check finds are processed only while the ceiling allows.
    """
    from api import store
    from config.discovery import MAX_MODEL_ITEMS

    conf = settings()
    spent = today_auto_spend()
    remaining = round(max(0.0, conf["cap_usd"] - spent), 6)
    report = store.discovery()
    rows, budget = [], remaining
    for event in pending_events(report):
        estimate = estimator(event["event_id"])
        fits = budget > 1e-9 and estimate["high"] <= budget + 1e-9
        if fits:
            budget -= estimate["high"]
        rows.append({"event_id": event["event_id"], "company": event.get("company"), "event_type": event["event_type"],
                     "low": round(estimate["low"], 6), "high": round(estimate["high"], 6), "fits": fits,
                     "status": "will run" if fits else "needs approval"})
    classify_high = classify_estimate(MAX_MODEL_ITEMS)
    steps = [
        {"step": "Read the sources (SEBI; NSE and BSE when switched on)", "model": None,
         "cost_usd_low": 0.0, "cost_usd_high": 0.0},
        {"step": f"Sort filings no rule settles (cheap model, at most {MAX_MODEL_ITEMS})", "model": "cheap model",
         "cost_usd_low": 0.0, "cost_usd_high": classify_high},
        {"step": f"Process waiting events oldest first ({sum(r['fits'] for r in rows)} of {len(rows)} fit)",
         "model": "cheap model", "cost_usd_low": round(sum(r["low"] for r in rows if r["fits"]), 6),
         "cost_usd_high": round(sum(r["high"] for r in rows if r["fits"]), 6)},
    ]
    return {"today": local_day(), "timezone": conf["timezone"], "spent_today_usd": spent, "cap_usd": conf["cap_usd"],
            "remaining_usd": remaining, "ceiling_usd": remaining, "steps": steps, "events": rows,
            "low": round(sum(step["cost_usd_low"] for step in steps), 6),
            "high": round(min(remaining, sum(step["cost_usd_high"] for step in steps)), 6),
            "basis": ("Measured history: each event's costliest comparable run so far (cost_log.csv). New filings "
                      "found during the check are processed only while the total stays within the ceiling."),
            "last_checked": (report or {}).get("refreshed_at")}


# ---------- the auto log ----------

def auto_log_path() -> Path:
    """outputs/auto_log.json: one entry per cycle."""
    return _outputs_dir() / "auto_log.json"


def read_auto_log() -> list[dict]:
    """Cycles, oldest first."""
    path = auto_log_path()
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("cycles", []) if path.is_file() else []
    except (OSError, ValueError):
        return []


def _save_cycle(cycle: dict) -> None:
    """Add or replace one cycle (by id) in outputs/auto_log.json; the last LOG_KEEP are kept."""
    cycles = [entry for entry in read_auto_log() if entry.get("id") != cycle["id"]] + [cycle]
    path = auto_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"cycles": cycles[-LOG_KEEP:]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


# ---------- one cycle ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_cycle(trigger: str, ceiling_usd: float | None = None, progress: Callable[[dict], None] | None = None,
              lock: FileLock | None = None, refresher: Callable[..., dict] | None = None,
              processor: Callable[..., dict] | None = None, estimator: Callable[[str], dict] = event_estimate,
              runner: Callable[[Path, str], dict] | None = None, spend: Callable[[], float] = today_auto_spend) -> dict:
    """Discovery, then auto-processing under the cap (and under ceiling_usd when a check-now set one).

    lock: an already-held run lock (check-now takes it before answering); otherwise one is taken
    here and the cycle returns {"status": "busy"} when another cycle holds it.
    """
    from tools import discover
    from tools.runlog import _current_run

    say = progress or (lambda _payload: None)
    lock = lock or FileLock(RUN_LOCK)
    if not lock.acquire():
        return {"status": "busy", "reason": "Another check is already running."}
    conf = settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cycle = {"id": f"{trigger}-{stamp}-{uuid.uuid4().hex[:4]}", "trigger": trigger, "started_at": _now_iso(),
             "finished_at": None, "status": "running", "cap_usd": conf["cap_usd"], "ceiling_usd": ceiling_usd,
             "day": local_day(), "spent_before_usd": spend(), "spent_usd": 0.0, "sources": [], "events_found": 0,
             "events_new": 0, "processed": [], "error": None}
    _save_cycle(cycle)
    start_spend = cycle["spent_before_usd"]

    def left() -> float:
        """What may still be spent: the cap's remainder, and the confirmed ceiling's when set."""
        now_spent = spend()
        room = conf["cap_usd"] - now_spent
        if ceiling_usd is not None:
            room = min(room, ceiling_usd - (now_spent - start_spend))
        return room

    def ask(items: list[dict]) -> None:
        """The cheap model sorts unsettled titles only when its worst case fits what is left."""
        if classify_estimate(min(len(items), _max_model_items())) > left():
            for item in items:
                discover.set_class(item, None, "unclassified (today's auto-processing budget is spent)", "none")
            say({"stage": "classify", "skipped": len(items), "reason": "today's auto-processing budget is spent"})
            return
        discover.classify_with_model(items)

    def gate(event: dict) -> dict:
        """Hold an event whose estimate does not fit what is left."""
        estimate = estimator(event["event_id"])
        room = left()
        if room <= 1e-9 or estimate["high"] > room + 1e-9:
            why = (f"its estimate (up to ${estimate['high']:.3f}) is more than what is left of today's "
                   f"${conf['cap_usd']:.2f} auto-processing cap (${max(room, 0):.3f})")
            if ceiling_usd is not None and conf["cap_usd"] - spend() > room:
                why = f"its estimate (up to ${estimate['high']:.3f}) is more than the confirmed check's ceiling allows"
            return {"hold": f"Needs approval: {why}", "estimate_usd": estimate["high"]}
        return {"estimate_usd": estimate["high"]}

    companies: dict[str, str] = {}

    def on_entry(state: str, entry: dict) -> None:
        say({"stage": "process", "state": state, "event_id": entry["event_id"],
             "company": companies.get(entry["event_id"]), "status": entry.get("status"),
             "cost_usd": entry.get("cost_usd"), "estimate_usd": entry.get("estimate_usd"),
             "reason": entry.get("reason") or "", "seconds": entry.get("seconds")})

    token = _current_run.set(f"{AUTO_PREFIX}discovery-{stamp}")
    try:
        say({"stage": "start", "trigger": trigger, "cap_usd": conf["cap_usd"], "spent_today_usd": start_spend,
             "ceiling_usd": ceiling_usd})
        refresh = refresher or discover.refresh
        options = discover.live_options() if refresher is None else {}
        report = refresh(conf["since_days"], events_dir=_events_dir(), outputs_dir=_outputs_dir(), ask=ask,
                         progress=say, **options)
        cycle["sources"] = [{"id": s["id"], "name": s.get("name"), "status": s["status"], "items": s.get("items", 0),
                             "reason": s.get("reason") if s["status"] != "ok" else ""} for s in report["sources"]]
        cycle["events_found"] = len(report["events"])
        cycle["events_new"] = sum(e["status"] in ("created", "updated") for e in report["events"])
        companies.update({e["event_id"]: e.get("company") for e in report["events"]})
        _current_run.reset(token)
        token = None
        process = processor or discover.process_events
        # The gate is the cap (it re-reads today's spend before each run); max_cost is not used here.
        result = process(report, limit=_max_events(), max_cost=float("inf"), outputs_dir=_outputs_dir(),
                         runner=runner or _auto_runner, gate=gate, oldest_first=True,
                         tag={"trigger": trigger, "auto": True, "cycle": cycle["id"]}, on_entry=on_entry)
        cycle["processed"] = [{**{key: entry.get(key) for key in ("event_id", "status", "reason", "cost_usd",
                                                                   "estimate_usd", "seconds", "run_id", "at")},
                               "company": companies.get(entry["event_id"])} for entry in result["processed"]]
        cycle["status"] = "done"
    except Exception as exc:  # a cycle must never take the API down; the reason is kept
        cycle["status"], cycle["error"] = "failed", f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if token is not None:
            _current_run.reset(token)
        cycle["finished_at"] = _now_iso()
        cycle["spent_usd"] = round(max(0.0, spend() - start_spend), 6)
        cycle["spent_today_usd"] = spend()
        _save_cycle(cycle)
        lock.release()  # a check-now lock was taken by the request; the cycle frees it either way
    say({"stage": "finish", "status": cycle["status"], "error": cycle["error"], "spent_usd": cycle["spent_usd"],
         "spent_today_usd": cycle["spent_today_usd"], "cap_usd": conf["cap_usd"],
         "processed": len([p for p in cycle["processed"] if p["status"] == "ok"]),
         "needs_approval": len([p for p in cycle["processed"] if p["status"] == "needs_approval"]),
         "events_new": cycle["events_new"]})
    return cycle


def _auto_runner(path: Path, event_id: str) -> dict:
    """run.py --step all with a run id starting "auto-", so its spend counts toward the cap."""
    from tools import discover

    return discover.run_event(path, event_id, run_prefix=AUTO_PREFIX.rstrip("-"))


def _max_model_items() -> int:
    from config.discovery import MAX_MODEL_ITEMS

    return MAX_MODEL_ITEMS


def _max_events() -> int:
    """At most this many events are processed in one cycle (AUTO_PROCESS_MAX_EVENTS, default 25)."""
    return int(_env_float("AUTO_PROCESS_MAX_EVENTS", 25))


# ---------- the loop ----------

class Scheduler:
    """The background loop. One per process; only the process holding SCHEDULER_LOCK runs cycles."""

    def __init__(self):
        self.lock = FileLock(SCHEDULER_LOCK)
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.state = "not started"
        self.next_run_at: str | None = None

    def start(self) -> str:
        """Start the loop when enabled and the lock is free; returns the resulting state."""
        conf = settings()
        if not conf["enabled"]:
            self.state = "off"
            return self.state
        if self.thread and self.thread.is_alive():
            return self.state
        if not self.lock.acquire():
            self.state = "another process"
            return self.state
        self.state = "running"
        self.thread = threading.Thread(target=self._loop, name="discovery-scheduler", daemon=True)
        self.thread.start()
        return self.state

    def first_delay(self) -> float:
        """Seconds to the first cycle: when the last one finished plus the interval, at least FIRST_CHECK_DELAY_S."""
        every = settings()["every_hours"] * 3600
        finished = [c.get("finished_at") for c in read_auto_log() if c.get("finished_at")]
        if not finished:
            return float(cfg.FIRST_CHECK_DELAY_S)
        last = datetime.fromisoformat(max(finished))
        due = (last + timedelta(seconds=every) - datetime.now(timezone.utc)).total_seconds()
        return max(float(cfg.FIRST_CHECK_DELAY_S), due)

    def _loop(self) -> None:
        delay = self.first_delay()
        while True:
            self.next_run_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
            if self.stop.wait(delay):
                return
            run_cycle("schedule")
            delay = settings()["every_hours"] * 3600

    def shutdown(self) -> None:
        """Stop the loop and free the lock (tests and API shutdown)."""
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.lock.release()
        self.state = "stopped"

    def status(self) -> dict:
        """{state, enabled, every_hours, next_run_at, last_run_at} for the auto log."""
        conf = settings()
        finished = [c.get("finished_at") for c in read_auto_log() if c.get("finished_at")]
        return {"state": self.state, "enabled": conf["enabled"], "every_hours": conf["every_hours"],
                "next_run_at": self.next_run_at if self.state == "running" else None,
                "last_run_at": max(finished) if finished else None}


SCHEDULER = Scheduler()


def start() -> str:
    """API startup hook. Never under pytest (tests drive cycles directly)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        SCHEDULER.state = "off"
        return SCHEDULER.state
    return SCHEDULER.start()


# ---------- check-now jobs and confirm tokens ----------

_TOKENS: dict[str, dict] = {}
JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def issue_token(user_email: str, estimate: dict) -> dict:
    """A single-use confirm token for this estimate's ceiling, valid CONFIRM_TTL_S seconds."""
    token = secrets.token_urlsafe(18)
    expires = time.time() + cfg.CONFIRM_TTL_S
    with _JOBS_LOCK:
        for key in [k for k, v in _TOKENS.items() if v["expires"] < time.time()]:
            _TOKENS.pop(key, None)
        _TOKENS[token] = {"user": user_email, "ceiling_usd": estimate["ceiling_usd"], "expires": expires}
    return {"token": token, "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(timespec="seconds"),
            "ttl_s": cfg.CONFIRM_TTL_S}


def redeem_token(token: str, user_email: str) -> dict | None:
    """The token's grant ({ceiling_usd}) once; None when unknown, expired, used or someone else's."""
    with _JOBS_LOCK:
        grant = _TOKENS.pop(token or "", None)
    if not grant or grant["expires"] < time.time() or grant["user"] != user_email:
        return None
    return grant


def start_check(ceiling_usd: float, lock: FileLock, cycle: Callable[..., dict] = run_cycle) -> dict:
    """Run one check-now cycle in a thread (with the run lock already held); returns the job."""
    job = {"job_id": uuid.uuid4().hex[:12], "state": "running", "events": [], "started_at": time.time(),
           "result": None}
    with _JOBS_LOCK:
        JOBS[job["job_id"]] = job

    def emit(payload: dict) -> None:
        with _JOBS_LOCK:
            job["events"].append({**payload, "at": round(time.time() - job["started_at"], 1)})

    def body() -> None:
        try:
            result = cycle("check-now", ceiling_usd=ceiling_usd, progress=emit, lock=lock)
            state = "complete" if result.get("status") == "done" else "failed"
        except Exception as exc:  # recorded on the job, never raised into the server
            result, state = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}, "failed"
            emit({"stage": "finish", "status": "failed", "error": result["error"]})
            lock.release()
        with _JOBS_LOCK:
            job["state"], job["result"] = state, result

    threading.Thread(target=body, name=f"check-now-{job['job_id']}", daemon=True).start()
    return job


def job_snapshot(job_id: str, start_at: int = 0) -> tuple[list[dict], str] | None:
    """(events from start_at, state) for a check-now job, or None."""
    with _JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return list(job["events"][start_at:]), job["state"]
