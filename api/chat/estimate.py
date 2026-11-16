"""Cost and time estimates for anything that spends money, from measured history. Code only.

Pipeline steps (processing an event): cost_log.csv grouped by run and step kind. An event that was processed
before reruns from the model cache, so its low end is $0 and its high end is what its own fresh run cost. A new
event uses the spread of every fresh run so far (median to max). Seconds come from outputs/runs.csv the same way.
Chat steps: once MIN_MEASURED_CALLS real calls of that step and model are logged, their min..max per call;
until then, the prompt's size in tokens (about 4 characters a token) times the model's price.
"""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict

from api import store
from config.chat import EST_OUTPUT_TOKENS, MIN_MEASURED_CALLS
from tools import costs

# Pipeline step kinds, in run order: (label in RM words, which logged agent names belong to it).
PIPELINE_STEPS = (
    ("Find the right pages", ()),
    ("Read the tables", ("extract_",)),
    ("Match people and families", ("identity",)),
    ("Rank who to call", ()),
    ("Write call briefs", ("brief",)),
    ("Assemble the call list", ()),
)
PROPOSE_AGENT = "add_event_propose"
CHARS_PER_TOKEN = 4

_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _rows() -> list[dict]:
    """Cost-log rows (re-read when the file changes)."""
    path = costs.cost_log_path()
    if not path.exists():
        return []
    mtime = path.stat().st_mtime
    hit = _CACHE.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    _CACHE[str(path)] = (mtime, rows)
    return rows


def _cost(row: dict) -> float:
    for key in ("charged_usd", "cost_usd"):
        try:
            if (row.get(key) or "").strip():
                return float(row[key])
        except ValueError:
            continue
    return 0.0


def _kind(agent: str) -> int | None:
    """Index into PIPELINE_STEPS for a logged agent name, or None."""
    for index, (_label, prefixes) in enumerate(PIPELINE_STEPS):
        if any(agent.startswith(prefix) for prefix in prefixes):
            return index
    return None


def _event_of(run_id: str) -> str:
    """The event id inside a run id ('<event>-<stamp>', 'discover-<event>-<stamp>' or 'auto-<event>-<stamp>')."""
    base = next((run_id[len(p):] for p in ("discover-", "auto-") if run_id.startswith(p)), run_id)
    return base.rsplit("-", 1)[0]


def pipeline_history() -> dict[str, dict[int, dict]]:
    """run_id -> step index -> {cost, calls (not cached), model} from the cost log."""
    runs: dict[str, dict[int, dict]] = defaultdict(dict)
    for row in _rows():
        run, kind = row.get("run_id") or "", _kind(row.get("agent_name") or "")
        if not run or kind is None:
            continue
        step = runs[run].setdefault(kind, {"cost": 0.0, "calls": 0, "model": row.get("model")})
        step["cost"] += _cost(row)
        step["calls"] += 0 if row.get("cached") == "true" else 1
    return runs


def _spread(values: list[float]) -> tuple[float, float]:
    """(median, max) of a list; (0, 0) when empty."""
    return (statistics.median(values), max(values)) if values else (0.0, 0.0)


def pipeline_estimate(event_id: str | None) -> dict:
    """{low, high, seconds_low, seconds_high, breakdown, basis} for processing one event."""
    history = pipeline_history()
    own = {run: steps for run, steps in history.items() if event_id and _event_of(run) == event_id}
    own_fresh = {run: steps for run, steps in own.items() if any(s["calls"] for s in steps.values())}
    fresh = {run: steps for run, steps in history.items() if any(s["calls"] for s in steps.values())}
    rerun = bool(own_fresh)
    breakdown, low, high = [], 0.0, 0.0
    for index, (label, prefixes) in enumerate(PIPELINE_STEPS):
        if not prefixes:
            breakdown.append({"step": label, "model": None, "calls": 0, "cost_usd": 0.0, "cost_usd_low": 0.0,
                              "cost_usd_high": 0.0})
            continue
        source = own_fresh if rerun else fresh
        costs_seen = [steps[index]["cost"] for steps in source.values() if index in steps]
        calls_seen = [steps[index]["calls"] for steps in source.values() if index in steps]
        models = [steps[index]["model"] for steps in source.values() if index in steps and steps[index]["model"]]
        mid, top = _spread(costs_seen)
        step_low = 0.0 if rerun else mid
        breakdown.append({"step": label, "model": models[-1] if models else None,
                          "calls": max(calls_seen) if calls_seen else 0,
                          "cost_usd": round(top, 6), "cost_usd_low": round(step_low, 6), "cost_usd_high": round(top, 6)})
        low += step_low
        high += top
    seconds_low, seconds_high = _seconds(event_id if rerun else None)
    if rerun:
        runs_word = "run" if len(own_fresh) == 1 else "runs"
        basis = (f"This event was processed before ({len(own_fresh)} measured {runs_word}). A repeat reads from the cache, "
                 "so it usually costs $0; the high end is what its first run cost.")
    else:
        basis = (f"Measured on {len(fresh)} earlier runs of new events: low is the median run, high the costliest. "
                 "Per-step cost from cost_log.csv, time from runs.csv.")
    return {"low": round(low, 6), "high": round(high, 6), "seconds_low": seconds_low, "seconds_high": seconds_high,
            "breakdown": breakdown, "basis": basis, "rerun": rerun}


def _seconds(event_id: str | None) -> tuple[int, int]:
    """(low, high) wall seconds: this event's runs when given, else fresh runs of any event."""
    rows = store.runs()
    if event_id:
        times = [float(r["wall_s"]) for r in rows if r.get("event_id") == event_id and r.get("status") == "ok" and r.get("wall_s")]
    else:
        times = [float(r["wall_s"]) for r in rows if r.get("status") == "ok" and r.get("wall_s")
                 and int(r.get("n_llm_calls") or 0) > int(r.get("n_cached_calls") or 0)]
    if not times:
        return 5, 180
    return max(1, int(min(times))), max(2, int(round(max(times))))


def propose_estimate() -> dict:
    """Reading a new link's first pages: rules first, one cheap-model call only when they fail."""
    seen = [_cost(r) for r in _rows() if r.get("agent_name") == PROPOSE_AGENT and r.get("cached") != "true"]
    top = max(seen) if seen else 0.001
    return {"step": "Read the first pages of the link", "model": "rules, then the cheap model if needed",
            "calls": 1, "cost_usd": round(top, 6), "cost_usd_low": 0.0, "cost_usd_high": round(top, 6)}


def tokens_of(text: str) -> int:
    """About how many tokens a prompt is."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def chat_step(step: str, label: str, model: str, prompt_chars: int) -> dict:
    """One chat step's breakdown row: measured per-call range when there is enough history, else tokens × price."""
    from tools.llm import PRICES

    measured = [_cost(r) for r in _rows() if r.get("agent_name") == f"chat:{step}" and r.get("model") == model
                and r.get("cached") != "true" and (r.get("status") or "ok") == "ok"]
    rate_in, rate_out = PRICES.get(model, (None, None))
    tokens_in, tokens_out = max(1, prompt_chars // CHARS_PER_TOKEN), EST_OUTPUT_TOKENS.get(step, 250)
    by_tokens = (tokens_in * (rate_in or 0) + tokens_out * (rate_out or 0)) / 1_000_000
    if len(measured) >= MIN_MEASURED_CALLS:
        low, high = min(measured), max(max(measured), by_tokens)
        how = f"measured on {len(measured)} calls"
    else:
        low, high = by_tokens * 0.6, by_tokens * 2.0  # a schema retry doubles it
        how = f"about {tokens_in:,} tokens in, {tokens_out} out"
    return {"step": label, "model": model, "calls": 1, "cost_usd": round(high, 6), "cost_usd_low": round(low, 6),
            "cost_usd_high": round(high, 6), "how": how}


def total(breakdown: list[dict]) -> tuple[float, float]:
    """(low, high) USD of a breakdown."""
    return (round(sum(r.get("cost_usd_low", r["cost_usd"]) for r in breakdown), 6),
            round(sum(r.get("cost_usd_high", r["cost_usd"]) for r in breakdown), 6))
