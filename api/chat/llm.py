"""Model calls for the chat agent: tools.llm.llm_call, plus the real cost of each call read back from cost_log.csv.

llm_call returns only the parsed JSON, so this module notes where the cost log ends before the call and sums
the rows appended for this turn afterwards (charged_usd when OpenRouter sent it, else our estimate; retries and
cache hits included). Agent names are "chat:<step>".

v2: each call also adds its tokens (input, output, cached input, cache writes) and the USD the provider's
prompt cache saved to a per-turn tally (usage_for(turn_id)), so a turn's meta and the `done` event carry them.
Local disk-cache hits log 0 tokens and are counted as calls avoided, never as provider cache hits.
"""

from __future__ import annotations

import csv
import io
import threading

from pydantic import BaseModel

from tools import costs


def _log_size() -> int:
    """Bytes in the cost log now (0 when it does not exist yet)."""
    path = costs.cost_log_path()
    return path.stat().st_size if path.exists() else 0


def rows_after(offset: int) -> list[dict]:
    """Cost-log rows appended after a byte offset."""
    path = costs.cost_log_path()
    if not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(offset)
        tail = handle.read().decode("utf-8", errors="replace")
    if not tail.strip():
        return []
    return list(csv.DictReader(io.StringIO(tail), fieldnames=costs.COLUMNS))


def row_cost(row: dict) -> float:
    """What one logged call cost in USD (charged when known, else estimated, else 0)."""
    for key in ("charged_usd", "cost_usd"):
        value = (row.get(key) or "").strip()
        if value:
            try:
                return float(value)
            except ValueError:
                continue
    return 0.0


_USAGE: dict[str, dict] = {}
_LOCK = threading.Lock()


def _int(row: dict, key: str) -> int:
    try:
        return int((row.get(key) or "0").strip() or 0)
    except ValueError:
        return 0


def record(turn_id: str, rows: list[dict]) -> None:
    """Add these cost-log rows to the turn's token tally."""
    from tools.llm import saved_by_cache

    with _LOCK:
        tally = _USAGE.setdefault(turn_id, {"input": 0, "output": 0, "cached_input": 0, "cache_write": 0,
                                            "saved_usd": 0.0, "provider_calls": 0, "local_hits": 0, "by_step": {}})
        for row in rows:
            if row.get("cached") == "true":
                tally["local_hits"] += 1
                continue
            cached, written = _int(row, "cached_input_tokens"), _int(row, "cache_write_tokens")
            tally["input"] += _int(row, "input_tokens")
            tally["output"] += _int(row, "output_tokens")
            tally["cached_input"] += cached
            tally["cache_write"] += written
            tally["saved_usd"] = round(tally["saved_usd"] + saved_by_cache(row.get("model") or "", cached, written), 8)
            tally["provider_calls"] += 1
            step = (row.get("agent_name") or "").removeprefix("chat:")
            mine = tally["by_step"].setdefault(step, {"input": 0, "cached_input": 0, "calls": 0})
            mine["input"] += _int(row, "input_tokens")
            mine["cached_input"] += cached
            mine["calls"] += 1


def usage_for(turn_id: str, pop: bool = False) -> dict:
    """{input, output, cached_input, cache_write, saved_usd, provider_calls, local_hits, by_step} for a turn."""
    with _LOCK:
        found = _USAGE.pop(turn_id, None) if pop else _USAGE.get(turn_id)
    return found or {"input": 0, "output": 0, "cached_input": 0, "cache_write": 0, "saved_usd": 0.0,
                     "provider_calls": 0, "local_hits": 0, "by_step": {}}


def call(step: str, model: str, messages: list[dict], schema: type[BaseModel], prompt_version: str,
         turn_id: str) -> tuple[dict, float, int]:
    """(parsed JSON, cost USD, calls made) for one chat step. Raises tools.llm.LLMError on failure."""
    from tools.llm import llm_call, register_schema

    register_schema(schema.__name__, schema)
    offset = _log_size()
    agent, event = f"chat:{step}", f"chat-{turn_id}"

    def tally() -> tuple[float, int]:
        mine = [row for row in rows_after(offset) if row.get("agent_name") == agent and row.get("event_id") == event]
        record(turn_id, mine)
        return round(sum(row_cost(row) for row in mine), 6), sum(1 for row in mine if row.get("cached") != "true")

    try:
        parsed = llm_call(agent, messages, schema.__name__, prompt_version, event_id=event, model=model)
    except Exception as exc:
        exc.chat_cost = tally()  # type: ignore[attr-defined]  # what the failed attempts still cost
        raise
    spent, calls = tally()
    return parsed, spent, calls


class Stream:
    """A streamed plain-text call: iterate for text deltas; afterwards .cost and .calls hold what it cost.

    Raises tools.llm.LLMError while iterating on failure (with .chat_cost set like call()).
    """

    def __init__(self, step: str, model: str, messages: list[dict], prompt_version: str, turn_id: str,
                 max_tokens: int | None = None):
        self.step, self.model, self.messages = step, model, messages
        self.prompt_version, self.turn_id, self.max_tokens = prompt_version, turn_id, max_tokens
        self.cost, self.calls = 0.0, 0

    def _tally(self, offset: int) -> tuple[float, int]:
        agent, event = f"chat:{self.step}", f"chat-{self.turn_id}"
        mine = [row for row in rows_after(offset) if row.get("agent_name") == agent and row.get("event_id") == event]
        record(self.turn_id, mine)
        return round(sum(row_cost(row) for row in mine), 6), sum(1 for row in mine if row.get("cached") != "true")

    def __iter__(self):
        from tools.llm import llm_stream

        offset = _log_size()
        try:
            yield from llm_stream(f"chat:{self.step}", self.messages, self.prompt_version, f"chat-{self.turn_id}",
                                  model=self.model, max_tokens=self.max_tokens)
        except Exception as exc:
            exc.chat_cost = self._tally(offset)  # type: ignore[attr-defined]
            raise
        self.cost, self.calls = self._tally(offset)
