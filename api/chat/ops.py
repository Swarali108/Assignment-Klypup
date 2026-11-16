"""Token economics of the chat for /api/ops/tokens. Code only, read from the cost log and the stored messages.

cache_hit_rate is provider prompt-cache tokens read / prompt tokens sent, over real provider calls only (a local
disk-cache hit sends nothing and is counted apart as local_cache_hits). saved_usd_by_cache nets the cache-write
premium (tools.llm.saved_by_cache), so it can be lower than the gross discount.
"""

from __future__ import annotations

import csv

from api.chat import history
from tools import costs
from tools.llm import saved_by_cache


def _int(value: object) -> int:
    try:
        return int(str(value or "0").strip() or 0)
    except ValueError:
        return 0


def _float(value: object) -> float:
    try:
        return float(str(value or "0").strip() or 0)
    except ValueError:
        return 0.0


def chat_rows() -> list[dict]:
    """Cost-log rows written by chat steps (agent_name chat:*)."""
    path = costs.cost_log_path()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if (row.get("agent_name") or "").startswith("chat:")]


def tokens_report() -> dict:
    """{questions, avg_cost_usd, cache_hit_rate, cached_tokens, saved_usd_by_cache, compressions,
    tokens_saved_by_compression, by_model: [...], ...}."""
    rows = chat_rows()
    by_model: dict[str, dict] = {}
    local_hits = 0
    turns: set[str] = set()
    for row in rows:
        if row.get("cached") == "true":
            local_hits += 1
            continue
        if (row.get("status") or "ok") != "ok":
            continue
        model = row.get("model") or "unknown"
        turns.add(row.get("event_id") or "")
        mine = by_model.setdefault(model, {"model": model, "calls": 0, "input_tokens": 0, "output_tokens": 0,
                                           "cached_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0,
                                           "saved_usd_by_cache": 0.0})
        cached, written = _int(row.get("cached_input_tokens")), _int(row.get("cache_write_tokens"))
        mine["calls"] += 1
        mine["input_tokens"] += _int(row.get("input_tokens"))
        mine["output_tokens"] += _int(row.get("output_tokens"))
        mine["cached_tokens"] += cached
        mine["cache_write_tokens"] += written
        mine["cost_usd"] = round(mine["cost_usd"] + (_float(row.get("charged_usd")) or _float(row.get("cost_usd"))), 6)
        mine["saved_usd_by_cache"] = round(mine["saved_usd_by_cache"] + saved_by_cache(model, cached, written), 6)
    for mine in by_model.values():
        mine["cache_hit_rate"] = round(mine["cached_tokens"] / mine["input_tokens"], 4) if mine["input_tokens"] else 0.0
    sent = sum(m["input_tokens"] for m in by_model.values())
    cached = sum(m["cached_tokens"] for m in by_model.values())
    answers = history.all_meta()
    # One cost total: the cost log's, the same figures the per-model rows above are made of (stored answers keep
    # only their own total, and an answer that was deleted still cost money). Questions: the larger of the stored
    # answers and the distinct turns that made a paid call, so the average is never inflated by deleted history.
    total_cost = round(sum(m["cost_usd"] for m in by_model.values()), 6)
    questions = max(len(answers), len(turns - {""}))
    compressions = [c for state in history.all_states() for c in state.get("compressions") or []]
    return {"questions": questions, "avg_cost_usd": round(total_cost / questions, 6) if questions else 0.0,
            "total_cost_usd": total_cost,
            "cache_hit_rate": round(cached / sent, 4) if sent else 0.0, "cached_tokens": cached, "input_tokens": sent,
            "saved_usd_by_cache": round(sum(m["saved_usd_by_cache"] for m in by_model.values()), 6),
            "compressions": len(compressions),
            "tokens_saved_by_compression": sum(int(c.get("tokens_saved") or 0) for c in compressions),
            "provider_calls": sum(m["calls"] for m in by_model.values()), "local_cache_hits": local_hits,
            "by_model": sorted(by_model.values(), key=lambda m: -m["cost_usd"])}
