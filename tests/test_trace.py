"""The agent trace: every cost row of a run lands in exactly one record, so the trace totals equal
the run's cost and calls. No network, no model."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from api.jobs import agent_payload
from tools import trace
from tools.costs import append_row
from tools.runlog import run_scope

ROOT = Path(__file__).resolve().parents[1]


def _row(run_id: str, agent: str, cost: str, cached: bool = False, tokens: tuple[int, int] = (100, 10)) -> dict:
    return {"timestamp": "2026-11-16T00:00:00Z", "run_id": run_id, "event_id": "e1", "agent_name": agent,
            "model": "test-model", "input_tokens": tokens[0], "output_tokens": tokens[1], "cost_usd": cost,
            "latency_s": "0.5", "cached": "true" if cached else "false"}


@pytest.fixture()
def logs(tmp_path, monkeypatch):
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("RUNS_CSV_PATH", str(tmp_path / "runs.csv"))
    return tmp_path


def test_trace_totals_equal_the_cost_log(logs, capsys):
    run_id = "e1-run"
    append_row(_row("other-run", "extract_x", "0.5"))  # another run's row is never counted
    with run_scope(run_id, "e1"), trace.tracing(run_id, "e1") as tracer:
        with trace.step("extract"):
            with trace.agent("extract_a", label="Read a", why="pages found", given="2 pages", runs_on="test-model") as rec:
                append_row(_row(run_id, "extract_a", "0.001200"))
                append_row(_row(run_id, "extract_a", "0.000300"))  # a schema retry: same agent, second row
                rec["returns"] = {"rows": 3}
            with trace.agent("verify_a", label="Verify a", why="quotes", given="3 quotes"):
                pass
            append_row(_row(run_id, "extract_b", "", cached=False))  # unpriced, outside any agent
        with trace.step("brief"):
            with trace.agent("brief", label="Briefs", why="people", given="2 people", runs_on="test-model"):
                append_row(_row(run_id, "brief", "0", cached=True, tokens=(0, 0)))
                with trace.agent("inner", label="Inner", why="nested", given=""):
                    append_row(_row(run_id, "brief", "0.000050"))
        built = trace.build_trace(tracer)

    assert built["balanced"] is True
    assert built["totals"]["calls"] == built["cost_log"]["calls"] == 5
    assert built["totals"]["cost_usd"] == pytest.approx(0.00155)
    assert built["totals"]["cached_calls"] == 1
    by_name = {a["name"]: a for a in built["agents"]}
    assert by_name["extract_a"]["calls"] == 2 and by_name["extract_a"]["returns"] == {"rows": 3}
    assert by_name["verify_a"]["calls"] == 0 and by_name["verify_a"]["runs_on"] == "code"
    assert by_name["extract_other"]["calls"] == 1 and by_name["extract_other"]["unpriced_calls"] == 1
    assert by_name["brief"]["calls"] == 1 and by_name["inner"]["calls"] == 1  # innermost span owns the row
    steps = {s["name"]: s for s in built["steps"]}
    assert steps["extract"]["calls"] == 3 and steps["brief"]["cost_usd"] == pytest.approx(0.00005)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith(trace.AGENT_PREFIX)]
    assert len(lines) == 2 * 6  # a start and a done line per span (2 steps + 4 agents)

    with (logs / "runs.csv").open(newline="", encoding="utf-8") as handle:
        run = next(row for row in csv.DictReader(handle) if row["run_id"] == run_id)
    assert int(run["n_llm_calls"]) == built["totals"]["calls"]
    assert float(run["total_cost_usd"]) == pytest.approx(built["totals"]["cost_usd"])


def test_spans_are_no_ops_without_a_tracer(capsys):
    with trace.agent("x", label="X", why="", given="") as rec:
        rec["returns"] = {"n": 1}
    assert capsys.readouterr().out == ""


def test_agent_lines_become_events_that_old_consumers_skip():
    start = trace.AGENT_PREFIX + json.dumps({"phase": "start", "agent": "verify_a", "kind": "agent", "step": "extract",
                                             "label": "Verify", "doing": "checking 47 quotes on their pages"})
    event = agent_payload(start)
    assert event["type"] == "agent" and event["parent"] == "extract" and event["doing"].startswith("checking 47")
    assert "step" not in event and "state" not in event  # api/chat/actions.py keys on these two
    step_done = agent_payload(trace.AGENT_PREFIX + json.dumps({"phase": "done", "agent": "extract", "kind": "step",
                                                               "runs_on": "code + m", "why": "rules"}))
    assert step_done["kind"] == "step" and step_done["runs_on"] == "code + m"
    assert agent_payload(trace.AGENT_PREFIX + "not json") is None


def test_first_run_and_latest(tmp_path):
    runs = tmp_path / "runs.csv"
    runs.write_text(
        "run_id,event_id,started_at,ended_at,wall_s,n_llm_calls,n_cached_calls,total_cost_usd,status,error\n"
        "r1,e1,2026-11-16T00:00:00Z,,80.0,31,0,0.028900,ok,\n"
        "r2,e1,2026-11-16T01:00:00Z,,3.0,9,9,0.000000,ok,\n"  # a brief-only rerun: not a full run
        "r3,e1,2026-11-16T02:00:00Z,,1.2,31,31,0.000000,ok,\n",
        encoding="utf-8",
    )
    runs.write_text(runs.read_text(encoding="utf-8").replace(
        "r1,", "r0,e1,2026-11-15T00:00:00Z,,2.0,1,0,0.000000,ok,\nr1,", 1), encoding="utf-8")
    priced = {"cost_usd": "0.001"}
    rows = [{"run_id": "r0", "agent_name": "extract_a", "cost_usd": ""},  # unpriced early run: not a "first run"
            {"run_id": "r1", "agent_name": "extract_a", **priced}, {"run_id": "r2", "agent_name": "brief", **priced},
            {"run_id": "r3", "agent_name": "extract_a", "cost_usd": "0"}]
    result = trace.event_runs("e1", runs, rows)
    assert result["first"]["run_id"] == "r1" and result["latest"]["run_id"] == "r3"
    assert result["latest"]["cached_share"] == 1.0
    assert result["saved_vs_first"]["cost_usd"] == pytest.approx(0.0289)


def _committed_traces() -> list[Path]:
    return sorted(path for path in (ROOT / "outputs").glob("*/trace.json"))


@pytest.mark.parametrize("path", _committed_traces(), ids=lambda p: p.parent.name)
def test_committed_trace_matches_the_cost_log(path):
    """A trace written by a real run balances against that run's rows in cost_log.csv and runs.csv."""
    built = json.loads(path.read_text(encoding="utf-8"))
    with (ROOT / "cost_log.csv").open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("run_id") == built["run_id"]]
    assert built["balanced"] is True
    assert built["totals"]["calls"] == len(rows)
    assert built["totals"]["cost_usd"] == pytest.approx(sum(float(r["cost_usd"] or 0) for r in rows), abs=1e-6)
    assert sum(a["calls"] for a in built["agents"]) == len(rows)
    with (ROOT / "outputs" / "runs.csv").open(newline="", encoding="utf-8") as handle:
        run = next(row for row in csv.DictReader(handle) if row["run_id"] == built["run_id"])
    assert int(run["n_llm_calls"]) == built["totals"]["calls"]
    assert float(run["total_cost_usd"]) == pytest.approx(built["totals"]["cost_usd"], abs=1e-6)


def test_rebuilt_trace_for_an_old_event_balances():
    """An event processed before traces existed still gets a trace whose totals equal its run."""
    # A document event (it has locate.json); structured events skip that step and start at people.
    folders = [p.parent for p in sorted((ROOT / "outputs").glob("*/timeline.json")) if (p.parent / "locate.json").is_file()]
    assert folders
    built = trace.trace_from_logs(folders[0].name, folders[0])
    assert built is not None and built["balanced"] is True
    assert [s["name"] for s in built["steps"]][0] == "locate"


def test_lean_budget_mode(monkeypatch):
    """BUDGET_MODE=lean: model briefs for the top few only, no strong model for names; a near-spent budget stops briefs."""
    from config import budget

    monkeypatch.delenv("BUDGET_MODE", raising=False)
    assert budget.event_budget_usd() == 2.0 and budget.strong_model_for_names()
    assert budget.model_brief_allowed(40, 0.01) is None
    monkeypatch.setenv("BUDGET_MODE", "lean")
    assert budget.event_budget_usd() == 0.5 and not budget.strong_model_for_names()
    assert budget.model_brief_allowed(0, 0.01) is None
    assert "top" in budget.model_brief_allowed(budget.LEAN_MODEL_BRIEFS, 0.01)
    assert "budget nearly spent" in budget.model_brief_allowed(0, 0.46)
