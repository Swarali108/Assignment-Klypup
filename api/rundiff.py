"""Per-run snapshots of ranked.json and the difference between two of them.

run.py writes outputs/<event>/runs/<run_id>.json when a run finishes (tools/runlog.snapshot_ranked). The diff names
the people added or removed in the call list and the people whose amount, tier or rank changed.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from api import store

GROUPS = ("callable", "entities", "context")


def snapshots(event_id: str) -> list[str]:
    """Run ids that have a stored snapshot, oldest first (run ids end in a UTC timestamp)."""
    folder = store.OUTPUTS_DIR / event_id / "runs"
    return sorted(path.stem for path in folder.glob("*.json")) if folder.is_dir() else []


def _load(event_id: str, run_id: str) -> dict | None:
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        return None
    try:
        return json.loads((store.OUTPUTS_DIR / event_id / "runs" / f"{run_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _people(snapshot: dict) -> dict[str, dict]:
    found = {}
    for group in GROUPS:
        for entry in snapshot.get(group) or []:
            found[entry["person_id"]] = {"person_id": entry["person_id"], "name": entry.get("name_as_printed"), "group": group,
                                         "tier": entry.get("call_tier_label") or entry.get("tier"),
                                         "amount": entry.get("amount_display"), "money_crore": entry.get("money_now_crore"),
                                         "rank": entry.get("rank")}
    return found


def _same_money(a: str | None, b: str | None) -> bool:
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return a == b


def diff(event_id: str, older: str | None = None, newer: str | None = None) -> dict:
    """{older, newer, added, removed, changed, unchanged}; the last two snapshots when no run ids are given."""
    ids = snapshots(event_id)
    newer = newer or (ids[-1] if ids else None)
    if older is None and newer in ids and ids.index(newer) > 0:
        older = ids[ids.index(newer) - 1]
    base = {"event_id": event_id, "runs_with_snapshot": ids, "older": older, "newer": newer}
    before = _load(event_id, older) if older else None
    after = _load(event_id, newer) if newer else None
    if before is None or after is None:
        return {**base, "available": False, "added": [], "removed": [], "changed": [], "unchanged": 0}
    old, new = _people(before), _people(after)
    added = [new[k] for k in new if k not in old]
    removed = [old[k] for k in old if k not in new]
    changed = []
    for key in new.keys() & old.keys():
        what = []
        if not _same_money(old[key]["money_crore"], new[key]["money_crore"]):
            what.append({"field": "amount", "before": old[key]["amount"], "after": new[key]["amount"]})
        if old[key]["tier"] != new[key]["tier"]:
            what.append({"field": "tier", "before": old[key]["tier"], "after": new[key]["tier"]})
        if old[key]["group"] != new[key]["group"]:
            what.append({"field": "list", "before": old[key]["group"], "after": new[key]["group"]})
        if old[key]["rank"] != new[key]["rank"]:
            what.append({"field": "rank", "before": old[key]["rank"], "after": new[key]["rank"]})
        if what:
            changed.append({"person_id": key, "name": new[key]["name"], "changes": what})
    unchanged = len(new.keys() & old.keys()) - len(changed)
    return {**base, "available": True, "added": added, "removed": removed, "changed": changed, "unchanged": unchanged}
