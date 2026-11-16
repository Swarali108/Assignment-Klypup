"""Scheduler, daily cap and check-now (tier 1): no network, no model, no real runs.

The cap must stop auto-processing; check-now without a token must only estimate; the lock must
keep a second runner out.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api import scheduler
from tools import costs, discover

PDF = "https://www.sebi.gov.in/sebi_data/attachdocs/nov-2026/"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Temp cost log, outputs, events and lock files; cap $1.00."""
    log = tmp_path / "cost_log.csv"
    monkeypatch.setenv("COST_LOG_PATH", str(log))
    monkeypatch.setenv("AUTO_PROCESS_DAILY_CAP_USD", "1.00")
    (tmp_path / "outputs").mkdir()
    (tmp_path / "events").mkdir()
    monkeypatch.setattr(scheduler, "_outputs_dir", lambda: tmp_path / "outputs")
    monkeypatch.setattr(scheduler, "_events_dir", lambda: tmp_path / "events")
    monkeypatch.setattr(scheduler, "RUN_LOCK", tmp_path / "run.lock")
    monkeypatch.setattr(scheduler, "SCHEDULER_LOCK", tmp_path / "scheduler.lock")
    return tmp_path


def _spend(run_id: str, usd: float) -> None:
    """One cost-log row for run_id, stamped now."""
    costs.append_row({"timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "run_id": run_id,
                      "event_id": "x", "agent_name": "extract_x", "model": "m", "cost_usd": f"{usd:.6f}", "cached": "false"})


def _report(n: int) -> dict:
    """n processable IPO events, the first published earliest."""
    return {"events": [{"event_id": f"example_{i}_ipo_202611", "event_type": "ipo", "processable": True,
                        "status": "created", "file": f"events/auto/example_{i}.json", "company": f"Example {i}",
                        "documents": [{"url": f"{PDF}{i}.pdf", "doc_type": "prospectus"}]} for i in range(1, n + 1)],
            "items": [{"event_id": f"example_{i}_ipo_202611", "published_iso": f"2026-11-{i:02d}"} for i in range(1, n + 1)],
            "sources": [{"id": "sebi_rhp", "name": "SEBI", "status": "ok", "items": n}]}


def _cycle(report: dict, runner, high: float, **kwargs) -> dict:
    """run_cycle with a stub refresh (returns report), a fixed estimate and a fake runner."""
    return scheduler.run_cycle("schedule", refresher=lambda *a, **k: report,
                               estimator=lambda event_id: {"low": 0.0, "high": high, "basis": "test"},
                               runner=runner, **kwargs)


def test_the_daily_cap_stops_auto_processing(sandbox):
    """Each run spends $0.45 (logged as auto); estimates are $0.40. Two fit under $1.00, the third waits."""
    ran = []

    def runner(path: Path, event_id: str) -> dict:
        ran.append(event_id)
        _spend(f"auto-{event_id}-1", 0.45)
        return {"status": "ok", "reason": "", "cost_usd": 0.45, "seconds": 1.0, "run_id": f"auto-{event_id}-1"}

    cycle = _cycle(_report(3), runner, high=0.40)
    assert ran == ["example_1_ipo_202611", "example_2_ipo_202611"]  # oldest first
    statuses = [entry["status"] for entry in cycle["processed"]]
    assert statuses == ["ok", "ok", "needs_approval"]
    assert "Needs approval" in cycle["processed"][2]["reason"]
    assert scheduler.today_auto_spend() == pytest.approx(0.90)
    # Next cycle the same day: the waiting event still does not fit, nothing runs.
    again = _cycle(_report(3), runner, high=0.40)
    assert len(ran) == 2 and [e["status"] for e in again["processed"]] == ["needs_approval"]
    log = json.loads((sandbox / "outputs" / "auto_log.json").read_text(encoding="utf-8"))["cycles"]
    assert len(log) == 2 and log[0]["spent_usd"] == pytest.approx(0.90)


def test_a_cap_of_zero_runs_nothing_and_manual_spend_does_not_count(sandbox, monkeypatch):
    """Only auto- runs count toward the cap; at cap 0 every event waits for approval."""
    _spend("example_1_ipo_202611-20261115T000000Z", 5.0)  # a manual run: not auto
    assert scheduler.today_auto_spend() == 0.0
    monkeypatch.setenv("AUTO_PROCESS_DAILY_CAP_USD", "0")
    runner = lambda path, event_id: pytest.fail("nothing may run at cap 0")
    cycle = _cycle(_report(2), runner, high=0.0)  # even a $0 estimate waits when nothing is left
    assert [entry["status"] for entry in cycle["processed"]] == ["needs_approval", "needs_approval"]


def test_a_confirmed_ceiling_limits_a_check_now_cycle(sandbox):
    """With $1.00 of cap left but a $0.50 ceiling, the second $0.40 event waits."""
    ran = []

    def runner(path, event_id):
        ran.append(event_id)
        _spend(f"auto-{event_id}-1", 0.40)
        return {"status": "ok", "reason": "", "cost_usd": 0.40, "seconds": 1.0}

    cycle = _cycle(_report(2), runner, high=0.40, ceiling_usd=0.50)
    assert ran == ["example_1_ipo_202611"]
    assert cycle["processed"][1]["status"] == "needs_approval"


def test_the_lock_keeps_a_second_runner_out(sandbox, monkeypatch):
    """Two locks on one file: the second fails until the first lets go; a cycle meets a held lock as busy."""
    first, second = scheduler.FileLock(sandbox / "x.lock"), scheduler.FileLock(sandbox / "x.lock")
    assert first.acquire() and not second.acquire()
    first.release()
    assert second.acquire()
    second.release()

    held = scheduler.FileLock(scheduler.RUN_LOCK)
    assert held.acquire()
    busy = scheduler.run_cycle("schedule", refresher=lambda *a, **k: pytest.fail("must not refresh while locked"))
    assert busy["status"] == "busy"
    held.release()

    monkeypatch.setenv("DISCOVERY_ENABLED", "1")
    monkeypatch.setattr(scheduler.Scheduler, "first_delay", lambda self: 3600.0)
    one, two = scheduler.Scheduler(), scheduler.Scheduler()
    try:
        assert one.start() == "running"
        assert two.start() == "another process"
    finally:
        one.shutdown()
        two.shutdown()


def test_check_now_without_a_token_only_estimates(as_role, sandbox, monkeypatch):
    """No network, no model, no cycle, no files written; an rm may not ask; a bad token is refused."""
    def forbidden(*args, **kwargs):
        raise AssertionError("check-now without a token must not run anything")

    monkeypatch.setattr(scheduler, "run_cycle", forbidden)
    monkeypatch.setattr(scheduler, "start_check", forbidden)
    monkeypatch.setattr(discover, "refresh", forbidden)
    monkeypatch.setattr(discover, "fetch", forbidden)
    monkeypatch.setattr(discover, "llm_call", forbidden)
    admin = as_role("admin")
    reply = admin.post("/api/discovery/check-now", json={})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["state"] == "estimate" and body["token"]
    assert body["estimate"]["ceiling_usd"] == pytest.approx(1.00)
    assert not (sandbox / "outputs" / "auto_log.json").exists()
    assert as_role("rm").post("/api/discovery/check-now", json={}).status_code == 403
    assert admin.post("/api/discovery/check-now", json={"confirm": "not-a-token"}).status_code == 409

    started = []
    monkeypatch.setattr(scheduler, "start_check",
                        lambda ceiling, lock: (started.append(ceiling), lock.release(), {"job_id": "j1"})[2])
    confirmed = admin.post("/api/discovery/check-now", json={"confirm": body["token"]})
    assert confirmed.status_code == 200 and started == [pytest.approx(1.00)]
    # The token is single use.
    assert admin.post("/api/discovery/check-now", json={"confirm": body["token"]}).status_code == 409


def test_sources_and_auto_log_are_admin_only(as_role, sandbox):
    """The rm role gets 403; the admin sees every source with a state and a risk label."""
    assert as_role("rm").get("/api/sources").status_code == 403
    assert as_role("rm").get("/api/discovery/auto-log").status_code == 403
    body = as_role("admin").get("/api/sources").json()
    owners = {row["owner"] for row in body["sources"]}
    assert {"SEBI", "NSE", "BSE"} <= owners
    assert all(row["state"] in ("on", "off", "blocked", "failed", "not checked") and row["risk"]["label"]
               for row in body["sources"])
    log = as_role("admin").get("/api/discovery/auto-log").json()
    assert log["today"]["cap_usd"] == pytest.approx(1.00) and log["today"]["spent_usd"] == 0.0
