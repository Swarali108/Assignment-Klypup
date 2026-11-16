"""run_scope writes one totals row from the cost log. No network."""

from __future__ import annotations

import csv

import pytest
from pydantic import BaseModel

import tools.llm as llm
from tools.llm import llm_call
from tools.runlog import _prepare_runs, run_scope

MESSAGES = [{"role": "user", "content": "Return the filing name only."}]


class FilingName(BaseModel):
    name: str


def test_run_scope_writes_one_row_with_totals(tmp_path, monkeypatch):
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm"))
    monkeypatch.setenv("RUNS_CSV_PATH", str(tmp_path / "runs.csv"))
    monkeypatch.delenv("RUN_ID", raising=False)
    llm.PRICES.clear()
    llm.SCHEMAS.clear()
    llm.PRICES["test-model"] = (1.0, 2.0)
    llm.register_schema("filing_name", FilingName)

    def fake_post(model, messages):
        return '{"name": "Acme Ltd"}', 100, 50

    monkeypatch.setattr(llm, "_post_chat", fake_post)
    with run_scope("run-9", "evt-9"):
        llm_call("extractor", MESSAGES, "filing_name", "v1", "evt-9", model="test-model")
        llm_call("extractor", MESSAGES, "filing_name", "v1", "evt-9", model="test-model")

    with (tmp_path / "runs.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "run-9"
    assert row["event_id"] == "evt-9"
    assert row["n_llm_calls"] == "2"
    assert row["n_cached_calls"] == "1"
    assert float(row["total_cost_usd"]) == (100 * 1.0 + 50 * 2.0) / 1_000_000
    assert float(row["wall_s"]) >= 0
    assert row["started_at"].endswith("Z")
    assert row["ended_at"].endswith("Z")
    assert row["status"] == "ok"
    assert row["error"] == ""
    llm.PRICES.clear()
    llm.SCHEMAS.clear()


def test_old_run_rows_get_a_blank_status(tmp_path):
    path = tmp_path / "runs.csv"
    path.write_text("run_id,event_id\nold,evt\n", encoding="utf-8")
    _prepare_runs(path)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == ""
    assert rows[0]["error"] == ""


def test_run_scope_records_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost_log.csv"))
    monkeypatch.setenv("RUNS_CSV_PATH", str(tmp_path / "runs.csv"))
    with pytest.raises(RuntimeError, match="boom"):
        with run_scope("run-err", "evt-err"):
            raise RuntimeError("boom")
    with (tmp_path / "runs.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "error"
    assert rows[0]["error"] == "boom"
    assert rows[0]["n_llm_calls"] == "0"
