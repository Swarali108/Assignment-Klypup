"""How old each fact's source document is: fetched date from cache/fetch/<sha>.json, and a stale flag.

A document is "stale" once it was fetched more than config.ops.stale_after_days() days ago. Nothing here fetches
anything; a document with no stored fetch date has fetched_at None and is never called stale.
"""

from __future__ import annotations

from datetime import datetime, timezone

from api import store
from config import ops as ops_config


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def doc_freshness(doc_sha: str, now: datetime | None = None) -> dict:
    """{fetched_at, age_days, stale, stale_after_days} for one cached document."""
    fetched = store.doc_meta(doc_sha).get("fetched_at")
    when = _parse(fetched)
    limit = ops_config.stale_after_days()
    if when is None:
        return {"fetched_at": None, "age_days": None, "stale": False, "stale_after_days": limit}
    age = max(0, ((now or datetime.now(timezone.utc)) - when).days)
    return {"fetched_at": fetched, "age_days": age, "stale": age > limit, "stale_after_days": limit}


def summary(documents: list[dict]) -> dict:
    """Roll-up for a person or event: the oldest fetch, whether anything is stale, and each document's date.

    `documents` are dicts with doc_sha and a label.
    """
    seen, rows = set(), []
    for doc in documents:
        sha = doc.get("doc_sha")
        if not sha or sha in seen:
            continue
        seen.add(sha)
        rows.append({"doc_sha": sha, "label": doc.get("label") or doc.get("doc_label") or "Source document",
                     **doc_freshness(sha)})
    dated = [row["fetched_at"] for row in rows if row["fetched_at"]]
    return {"documents": rows, "oldest_fetched_at": min(dated) if dated else None,
            "newest_fetched_at": max(dated) if dated else None,
            "stale": any(row["stale"] for row in rows), "stale_after_days": ops_config.stale_after_days()}
