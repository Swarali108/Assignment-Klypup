"""Write docs/cost_report.md from cost_log.csv, outputs/runs.csv and outputs/<event_id>/. Code only.

    python -m tools.cost_report

Per event (every events/*.json that has outputs):
  fresh cost        what the latest run would cost with no cache: each cached call is
                    priced at the last uncached call of the same agent, model and person
                    (tools.costs.per_person_cost). An estimate, labelled so.
  latest run        its cost (a cached rerun costs 0), wall time and calls, from runs.csv.
  latest fresh run  the latest run with at least one uncached call, from runs.csv.
  per callable      fresh cost / number of callable people in ranked.json.
  spent             every logged call for the event, charged_usd when set, else cost_usd.
Total development spend is the same sum over every row except the ping check.
The pricing lines are copied from the PRICES block in tools/llm.py.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from tools.costs import per_person_cost

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Build the report and write docs/cost_report.md."""
    out = ROOT / "docs" / "cost_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(ROOT), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def build_report(root: Path) -> str:
    """The whole report as Markdown."""
    rows = read_csv(root / "cost_log.csv")
    runs = read_csv(root / "outputs" / "runs.csv")
    events = sorted(path.stem for path in (root / "events").glob("*.json") if (root / "outputs" / path.stem).is_dir())
    summaries = [event_summary(event_id, rows, runs, root) for event_id in events]
    spend, unpriced = development_spend(rows)
    lines = [
        "# Cost report",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `python -m tools.cost_report` "
        "from `cost_log.csv`, `outputs/runs.csv` and `outputs/<event_id>/ranked.json`.",
        "",
        "| Event | Fresh cost (estimate) | Latest run cost | Latest run wall time | Latest run calls (cached) | "
        "Latest fresh run: cost, wall time | Callable people | Fresh cost per callable person | Spent on this event |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(_summary_row(summary) for summary in summaries)
    lines += [
        "",
        f"Total development spend: **${spend:.4f}** over {sum(1 for r in rows if r.get('agent_name') != 'ping')} logged "
        f"calls (charged_usd where OpenRouter reported it, else our cost_usd estimate; the ping row is excluded)."
        + (f" {unpriced} {'call has' if unpriced == 1 else 'calls have'} no price and {'is' if unpriced == 1 else 'are'} "
           "not in the sum." if unpriced else ""),
        "",
        "Fresh cost is an estimate: the cost log does not record which earlier call a cache hit came from, so each "
        "cached call is priced at the last uncached call with the same agent, model and person.",
        "",
        "## Pricing source (copied from tools/llm.py)",
        "",
        *[f"- {line}" for line in pricing_lines(root / "tools" / "llm.py")],
        "",
    ]
    return "\n".join(lines)


def event_summary(event_id: str, rows: list[dict], runs: list[dict], root: Path) -> dict:
    """The numbers for one event."""
    mine = [run for run in runs if run.get("event_id") == event_id]
    latest = mine[-1] if mine else {}
    fresh_runs = [run for run in mine if int(run.get("n_cached_calls") or 0) < int(run.get("n_llm_calls") or 0)]
    totals = per_person_cost(event_id, latest.get("run_id"), people=[], rows=rows)["totals"] if latest else {}
    callable_count = _callable_count(root / "outputs" / event_id / "ranked.json")
    fresh = totals.get("fresh_usd")
    return {
        "event_id": event_id,
        "fresh_usd": fresh,
        "latest": latest,
        "latest_fresh": fresh_runs[-1] if fresh_runs else {},
        "callable": callable_count,
        "per_callable": (fresh / callable_count) if fresh is not None and callable_count else None,
        "spent": development_spend([row for row in rows if row.get("event_id") == event_id])[0],
    }


def development_spend(rows: list[dict]) -> tuple[float, int]:
    """(sum of charged_usd, else cost_usd, over every non-ping row; rows with neither)."""
    total, unpriced = 0.0, 0
    for row in rows:
        if row.get("agent_name") == "ping":
            continue
        value = (row.get("charged_usd") or "").strip() or (row.get("cost_usd") or "").strip()
        if value:
            total += float(value)
        elif (row.get("cached") or "").lower() != "true" and (row.get("status") or "ok") == "ok":
            unpriced += 1
    return total, unpriced


def pricing_lines(llm_path: Path) -> list[str]:
    """The comment and entry lines of the PRICES block in tools/llm.py, as written there."""
    text = llm_path.read_text(encoding="utf-8")
    start = text.index("# USD per 1,000,000 tokens")
    end = text.index("\n}", text.index("PRICES:", start)) + 2
    lines = []
    for raw in text[start:end].splitlines():
        line = raw.strip()
        if line.startswith("#"):
            lines.append(line.lstrip("# ").strip())
        elif re.match(r'^"[^"]+": \(', line):
            lines.append(f"`{line.rstrip(',')}` (USD per 1M input, output tokens)")
    return lines


def read_csv(path: Path) -> list[dict]:
    """Rows of a CSV file, or [] when it is missing."""
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _callable_count(path: Path) -> int | None:
    """How many callable people ranked.json lists, or None when it is missing."""
    if not path.is_file():
        return None
    return len(json.loads(path.read_text(encoding="utf-8")).get("callable") or [])


def _summary_row(summary: dict) -> str:
    """One table row. A missing number reads "unknown"."""
    latest, fresh_run = summary["latest"], summary["latest_fresh"]

    def money(value) -> str:
        return "unknown" if value is None or value == "" else f"${float(value):.4f}"

    def seconds(value) -> str:
        return "unknown" if not value else f"{float(value):.1f} s"

    calls = f"{latest.get('n_llm_calls', 'unknown')} ({latest.get('n_cached_calls', 'unknown')})" if latest else "unknown"
    fresh_text = f"{money(fresh_run.get('total_cost_usd'))}, {seconds(fresh_run.get('wall_s'))}" if fresh_run else "unknown"
    return (
        f"| {summary['event_id']} | {money(summary['fresh_usd'])} | {money(latest.get('total_cost_usd'))} | "
        f"{seconds(latest.get('wall_s'))} | {calls} | {fresh_text} | {summary['callable'] if summary['callable'] is not None else 'unknown'} | "
        f"{money(summary['per_callable'])} | {money(summary['spent'])} |"
    )


if __name__ == "__main__":
    raise SystemExit(main())
