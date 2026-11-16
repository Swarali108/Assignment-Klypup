"""Append-only cost log and a per-run summary.

The CSV is the budget record. A blank cost_usd means the model price was not
configured. A zero means this call added no spend (a cache hit, or a priced
call that used no tokens).
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

COLUMNS = [
    "timestamp",
    "run_id",
    "event_id",
    "person_id",
    "agent_name",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "latency_s",
    "cached",
]

ROOT = Path(__file__).resolve().parents[1]


def cost_log_path() -> Path:
    """Return the CSV path. Tests set COST_LOG_PATH to a temp file."""
    override = os.environ.get("COST_LOG_PATH", "").strip()
    if override:
        return Path(override)
    return ROOT / "cost_log.csv"


def append_row(row: dict) -> None:
    """Append one call to the cost log, creating the header if the file is empty."""
    path = cost_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in COLUMNS})


def _read_rows() -> list[dict]:
    path = cost_log_path()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _as_float(value: str) -> float | None:
    text = (value or "").strip()
    if text == "":
        return None
    return float(text)


def summarise(run_id: str) -> dict:
    """Print and return spend and latency for one run, by event and by person.

    Blank costs are counted as unpriced and are not added into the total.
    Person id "(none)" means the call was for the event as a whole.
    """
    matched = [row for row in _read_rows() if row.get("run_id", "") == run_id]
    per_event: dict[str, dict] = defaultdict(lambda: _blank_bucket())
    per_person: dict[tuple[str, str], dict] = defaultdict(lambda: _blank_bucket())
    total = _blank_bucket()

    for row in matched:
        cost = _as_float(row.get("cost_usd", ""))
        latency = _as_float(row.get("latency_s", "")) or 0.0
        cached = (row.get("cached", "") or "").strip().lower() == "true"
        event_id = row.get("event_id", "") or "(none)"
        person_id = row.get("person_id", "") or "(none)"
        _add(total, cost, latency, cached)
        _add(per_event[event_id], cost, latency, cached)
        _add(per_person[(event_id, person_id)], cost, latency, cached)

    summary = {
        "run_id": run_id,
        "calls": total["calls"],
        "cost_usd": total["cost_usd"],
        "unpriced_calls": total["unpriced_calls"],
        "latency_s": round(total["latency_s"], 3),
        "cached_calls": total["cached_calls"],
        "per_event": {
            event_id: _public_bucket(bucket) for event_id, bucket in sorted(per_event.items())
        },
        "per_person": [
            {"event_id": event_id, "person_id": person_id, **_public_bucket(bucket)}
            for (event_id, person_id), bucket in sorted(per_person.items())
        ],
    }
    _print_summary(summary)
    return summary


def _blank_bucket() -> dict:
    return {"calls": 0, "cost_usd": 0.0, "unpriced_calls": 0, "latency_s": 0.0, "cached_calls": 0}


def _add(bucket: dict, cost: float | None, latency: float, cached: bool) -> None:
    bucket["calls"] += 1
    bucket["latency_s"] += latency
    if cached:
        bucket["cached_calls"] += 1
    if cost is None:
        bucket["unpriced_calls"] += 1
    else:
        bucket["cost_usd"] += cost


def _public_bucket(bucket: dict) -> dict:
    return {
        "calls": bucket["calls"],
        "cost_usd": round(bucket["cost_usd"], 6),
        "unpriced_calls": bucket["unpriced_calls"],
        "latency_s": round(bucket["latency_s"], 3),
        "cached_calls": bucket["cached_calls"],
    }


def _print_summary(summary: dict) -> None:
    print(f"run_id: {summary['run_id']}")
    print(f"calls: {summary['calls']}")
    print(f"cost_usd: {summary['cost_usd']:.6f}")
    print(f"unpriced_calls: {summary['unpriced_calls']}")
    print(f"latency_s: {summary['latency_s']:.3f}")
    print(f"cached_calls: {summary['cached_calls']}")
    print("per event:")
    for event_id, bucket in summary["per_event"].items():
        print(
            f"  {event_id}  cost_usd={bucket['cost_usd']:.6f}"
            f"  latency_s={bucket['latency_s']:.3f}"
            f"  calls={bucket['calls']}"
            f"  unpriced={bucket['unpriced_calls']}"
        )
    print("per person:")
    for row in summary["per_person"]:
        print(
            f"  {row['event_id']}  {row['person_id']}"
            f"  cost_usd={row['cost_usd']:.6f}"
            f"  latency_s={row['latency_s']:.3f}"
            f"  calls={row['calls']}"
        )
    if summary["unpriced_calls"]:
        print("Some calls have a blank cost. Fill PRICES in tools/llm.py from the provider's pricing page.")


def per_person_cost(
    event_id: str,
    run_id: str | None = None,
    people: list[dict] | None = None,
    rows: list[dict] | None = None,
) -> dict:
    """Spend for one run of one event, split across people.

    run_id defaults to the last run in the log for this event. Two costs are split:
    cost_usd is what this run spent (a cache hit is 0); fresh_usd is what it would
    cost with no cache, taking each cached call's cost from the last uncached call
    with the same agent, model and person_id.

    Split rule, per call:
      brief           charged to its person_id.
      identity        split equally across the two people of the pair.
      extract_<sec>   split equally across people with a kept field from <sec>.
      anything else, or a call no person matches, split equally across all people.
    So the per-person rows add up to the event total, give or take rounding.
    """
    all_rows = rows if rows is not None else _read_rows()
    mine = [row for row in all_rows if row.get("event_id") == event_id]
    run_id = run_id or (mine[-1].get("run_id") if mine else "")
    run_rows = [row for row in mine if row.get("run_id") == run_id]
    people = people if people is not None else _load_people(ROOT / "outputs" / event_id)
    shares = {person["person_id"]: {"cost_usd": 0.0, "fresh_usd": 0.0, "calls": 0.0} for person in people}
    for row in run_rows:
        owners = _owners(row, people)
        cost = _as_float(row.get("cost_usd", "")) or 0.0
        fresh = _fresh_cost(row, mine)
        for person_id in owners:
            shares[person_id]["cost_usd"] += cost / len(owners)
            shares[person_id]["fresh_usd"] += fresh / len(owners)
            shares[person_id]["calls"] += 1 / len(owners)
    names = {person["person_id"]: person.get("name_as_printed") for person in people}
    return {
        "event_id": event_id,
        "run_id": run_id,
        "totals": _run_totals(run_rows, mine),
        "per_person": [
            {
                "person_id": person_id,
                "name_as_printed": names[person_id],
                "cost_usd": round(share["cost_usd"], 6),
                "fresh_usd": round(share["fresh_usd"], 6),
                "calls": round(share["calls"], 3),
            }
            for person_id, share in sorted(shares.items(), key=lambda item: -item[1]["fresh_usd"])
        ],
    }


def write_cost_json(
    event_id: str,
    folder: Path | None = None,
    run_id: str | None = None,
    wall_s: float | None = None,
) -> Path:
    """Write <folder>/cost.json (default outputs/<event_id>). People come from people.json there.

    wall_s comes from the caller, or from runs.csv once the run has closed.
    """
    folder = Path(folder) if folder is not None else ROOT / "outputs" / event_id
    report = per_person_cost(event_id, run_id, people=_load_people(folder))
    report["totals"]["wall_s"] = wall_s if wall_s is not None else _wall_from_runs(report["run_id"])
    report["totals"].update(per_callable(report["totals"], _callable_count(folder)))
    out = folder / "cost.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def per_callable(totals: dict, callable_people: int | None) -> dict:
    """This run's cost and its no-cache cost divided by the callable people; None when there are none."""
    if not callable_people:
        return {"callable_people": callable_people, "cost_per_callable_usd": None, "fresh_per_callable_usd": None}
    return {
        "callable_people": callable_people,
        "cost_per_callable_usd": round(totals.get("cost_usd", 0.0) / callable_people, 6),
        "fresh_per_callable_usd": round(totals.get("fresh_usd", 0.0) / callable_people, 6),
    }


def _callable_count(folder: Path) -> int | None:
    """How many callable people ranked.json in folder lists, or None before ranking."""
    path = folder / "ranked.json"
    if not path.is_file():
        return None
    return len(json.loads(path.read_text(encoding="utf-8")).get("callable") or [])


def run_rows(run_id: str) -> list[dict]:
    """Cost-log rows for one run, in the order they were written."""
    return [row for row in _read_rows() if row.get("run_id", "") == run_id]


def _owners(row: dict, people: list[dict]) -> list[str]:
    """Person ids that share this call's cost, by the rule in per_person_cost."""
    everyone = [person["person_id"] for person in people]
    agent = row.get("agent_name", "")
    if agent == "brief":
        found = [pid for pid in everyone if pid == row.get("person_id")]
    elif agent == "identity":
        names = [part.strip() for part in (row.get("person_id") or "").split(" | ")]
        found = [p["person_id"] for p in people if set(p.get("names_as_printed") or [p.get("name_as_printed")]) & set(names)]
    elif agent.startswith("extract_"):
        section = agent[len("extract_"):]
        found = [p["person_id"] for p in people if _has_kept_field(p, section)]
    else:
        found = []
    return found or everyone


def _has_kept_field(person: dict, section: str) -> bool:
    """True when some evidence the person kept came from this section."""
    return any(
        item.get("section") == section and item.get("field_kept", True) for item in person.get("evidence") or []
    )


def _fresh_cost(row: dict, rows: list[dict]) -> float:
    """This call's cost, or for a cache hit the last uncached matching call's cost."""
    if (row.get("cached") or "").strip().lower() != "true":
        return _as_float(row.get("cost_usd", "")) or 0.0
    key = (row.get("agent_name"), row.get("model"), row.get("person_id"))
    for earlier in reversed(rows):
        if (earlier.get("cached") or "").strip().lower() == "true" or (earlier.get("status") or "ok") != "ok":
            continue
        if (earlier.get("agent_name"), earlier.get("model"), earlier.get("person_id")) == key:
            return _as_float(earlier.get("cost_usd", "")) or 0.0
    return 0.0


def _run_totals(run_rows: list[dict], event_rows: list[dict]) -> dict:
    """Tokens, cost, fresh cost and cached share for one run."""
    cached = sum(1 for row in run_rows if (row.get("cached") or "").strip().lower() == "true")
    tokens_in = sum(int(row.get("input_tokens") or 0) for row in run_rows)
    tokens_out = sum(int(row.get("output_tokens") or 0) for row in run_rows)
    return {
        "calls": len(run_rows),
        "cached_calls": cached,
        "cached_share": round(cached / len(run_rows), 3) if run_rows else None,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost_usd": round(sum(_as_float(row.get("cost_usd", "")) or 0.0 for row in run_rows), 6),
        "fresh_usd": round(sum(_fresh_cost(row, event_rows) for row in run_rows), 6),
        "unpriced_calls": sum(1 for row in run_rows if _as_float(row.get("cost_usd", "")) is None),
    }


def _load_people(folder: Path) -> list[dict]:
    """people from <folder>/people.json, or an empty list."""
    path = Path(folder) / "people.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("people") or []


def _wall_from_runs(run_id: str) -> float | None:
    """wall_s for this run from outputs/runs.csv, or None while the run is still open."""
    path = Path(os.environ.get("RUNS_CSV_PATH", "").strip() or ROOT / "outputs" / "runs.csv")
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("run_id") == run_id:
                return _as_float(row.get("wall_s", ""))
    return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m tools.costs <run_id>")
        sys.exit(1)
    summarise(sys.argv[1])
