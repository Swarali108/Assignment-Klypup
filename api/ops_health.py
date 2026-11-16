"""System health for /ops/health: scheduler, sources, caches, today's spend against its caps, failed runs.

Everything is read from files the pipeline already writes (cost_log.csv, outputs/runs.csv, outputs/discovery.json,
the cache folders). The scheduler and the Bright Data counter belong to other parts of the platform: they are looked up
with guarded imports, and when that part is not installed the section says so instead of failing.
"""

from __future__ import annotations

import importlib
import time
from datetime import datetime, timezone

from api import jobs, store
from api.chat import ops as chat_ops
from config import budget
from config import ops as ops_config
from tools import costs


def _dir_size(path) -> tuple[int, int]:
    """(files, bytes) of a folder, not following links."""
    files, size = 0, 0
    if path.is_dir():
        for item in path.iterdir():
            try:
                if item.is_file():
                    files += 1
                    size += item.stat().st_size
            except OSError:
                continue
    return files, size


def caches() -> list[dict]:
    """Size of each cache folder: documents fetched, pages parsed, model answers."""
    rows = []
    for key, label, path in (("fetch", "Downloaded documents", store.FETCH_DIR), ("pages", "Parsed pages", store.PAGES_DIR),
                             ("llm", "Model answers", store.ROOT / "cache" / "llm")):
        files, size = _dir_size(path)
        rows.append({"key": key, "label": label, "files": files, "bytes": size})
    return rows


def _float(value: object) -> float:
    try:
        return float(str(value or "0").strip() or 0)
    except ValueError:
        return 0.0


def spend() -> dict:
    """Model calls and dollars today (UTC) and over all time, the share answered from the cache, and the limits."""
    rows = costs._read_rows()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mine = [r for r in rows if (r.get("agent_name") or "") != "ping"]
    day = [r for r in mine if (r.get("timestamp") or "").startswith(today)]

    def figures(group: list[dict]) -> dict:
        calls = len(group)
        cached = sum(1 for r in group if (r.get("cached") or "").lower() == "true")
        usd = sum(_float(r.get("charged_usd")) or _float(r.get("cost_usd")) for r in group if (r.get("cached") or "").lower() != "true")
        return {"calls": calls, "cached_calls": cached, "paid_calls": calls - cached, "cost_usd": round(usd, 6),
                "cache_hit_rate": round(cached / calls, 4) if calls else None}

    cap = ops_config.model_daily_cap_usd()
    today_figures = figures(day)
    return {"today": today_figures, "all_time": figures(mine), "date": today,
            "daily_cap_usd": cap, "daily_cap_used": round(today_figures["cost_usd"] / cap, 4) if cap else None,
            "event_budget_usd": budget.event_budget_usd(), "budget_mode": budget.budget_mode(),
            "provider_cache": {"hit_rate": chat_ops.tokens_report().get("cache_hit_rate")}}


def scheduler() -> dict:
    """The background scheduler's status, when api/scheduler exists (merged separately); else {available: False}."""
    try:
        module = importlib.import_module("api.scheduler")
    except ImportError:
        return {"available": False, "reason": "The scheduler is not part of this build."}
    # The status lives on the SCHEDULER singleton (SCHEDULER.status()); older builds may expose a
    # module-level function instead. Try the object first, then the function names.
    candidates = []
    singleton = getattr(module, "SCHEDULER", None)
    if singleton is not None and callable(getattr(singleton, "status", None)):
        candidates.append(singleton.status)
    candidates += [fn for name in ("status", "get_status", "snapshot")
                   if callable(fn := getattr(module, name, None))]
    for fn in candidates:
        try:
            found = fn()
            return {"available": True, **(found if isinstance(found, dict) else {"detail": str(found)})}
        except Exception as exc:  # a broken scheduler must not take the health page down
            return {"available": True, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return {"available": True, "error": "The scheduler has no status function."}


def brightdata() -> dict:
    """Bright Data requests this month against the cap (the same counter the Sources page shows)."""
    cap = ops_config.brightdata_monthly_cap()
    try:
        from tools import brightdata as bd
    except ImportError:
        return {"available": False, "reason": "Bright Data is not part of this build.", "cap": cap}
    try:
        usage = bd.usage_summary()
    except Exception as exc:  # a broken counter file must not take the health page down
        return {"available": True, "error": f"{type(exc).__name__}: {str(exc)[:160]}", "cap": cap}
    used, limit = usage.get("used"), usage.get("cap") or cap
    return {"available": True, "requests": used, "cap": limit, "month": usage.get("month"),
            "used_share": round(used / limit, 4) if limit and used is not None else None}


def sources() -> dict:
    """Each discovery source's last status (ok, blocked, failed, disabled) and when discovery last ran."""
    found = store.discovery() or {}
    return {"refreshed_at": found.get("refreshed_at"),
            "sources": [{"id": s.get("id"), "name": s.get("name"), "status": s.get("status"), "items": s.get("items"), "records": s.get("records"),
                         "reason": s.get("reason") or s.get("note") or None, "url": s.get("url")}
                        for s in found.get("sources") or []]}


def failed_runs(limit: int = 20) -> list[dict]:
    """Events whose latest run failed (outputs/runs.csv status error, or a job that failed since the API started)."""
    last: dict[str, dict] = {}
    for row in store.runs():
        if row.get("event_id"):
            last[row["event_id"]] = row
    known = {e["spec"].event_id: e["spec"].company for e in store.load_events()}
    running = jobs.running_events()
    found = []
    for event_id, row in last.items():
        if row.get("status") == "error" and event_id in known:
            found.append({"event_id": event_id, "company": known[event_id], "run_id": row.get("run_id"),
                          "at": row.get("ended_at"), "reason": (row.get("error") or "model call failed")[:240],
                          "running": event_id in running})
    seen = {f["event_id"] for f in found}
    for job in jobs.recent(50):
        if job["state"] == "failed" and job["event_id"] in known and job["event_id"] not in seen:
            at = datetime.fromtimestamp(job["started_at"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            found.append({"event_id": job["event_id"], "company": known[job["event_id"]], "run_id": job["job_id"], "at": at,
                          "reason": (job.get("reason") or "Processing failed")[:240], "running": job["event_id"] in running})
            seen.add(job["event_id"])
    return sorted(found, key=lambda f: f.get("at") or "", reverse=True)[:limit]


def health() -> dict:
    """Everything on the health page."""
    return {"checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "scheduler": scheduler(),
            "sources": sources(), "caches": caches(), "spend": spend(), "brightdata": brightdata(),
            "failed_runs": failed_runs(), "stale_after_days": ops_config.stale_after_days(),
            "running": sorted(jobs.running_events())}
