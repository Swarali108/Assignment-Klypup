"""Accuracy dashboard data: eval.check_people against the hand-read gold, cached on disk.

Running it makes no model call (it reads outputs/<event>/ranked.json and people.json), so the re-run button is free.
The last result is kept at outputs/eval_people.json; each miss carries a link to the gold's evidence page.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from api import store

RESULT_PATH = store.OUTPUTS_DIR / "eval_people.json"
_LOCK = threading.Lock()
FIELD_LABEL = {"name": "Name", "role": "Role", "shares_offered": "Shares offered", "shares_held_pre_offer": "Shares held before",
               "price": "Price", "amount": "Amount", "timing": "Timing"}
MISS = ("wrong", "missing", "invented")


def _page_links(gold_person: dict, field: str, sources: dict) -> list[dict]:
    """Where the gold read this field: [{label, url}] pointing at the cached PDF page."""
    item = gold_person.get(field) or {}
    links = []
    for ev in item.get("evidence") or []:
        source = sources.get(ev.get("source")) or {}
        sha = source.get("fetch_key") or (store.url_sha(source["url"]) if source.get("url") else None)
        if not sha or not ev.get("pdf_index"):
            continue
        links.append({"label": f"Page {ev.get('printed_page') or ev['pdf_index']}", "url": f"/api/docs/{sha}.pdf#page={ev['pdf_index']}",
                      "cached": store.pdf_path(sha) is not None, "quote": ev.get("quote")})
    return links


def run() -> dict:
    """Score every gold person now, store and return the result."""
    from eval import check_people

    with _LOCK:
        gold = check_people.load_gold()
        result = check_people.evaluate(gold)
        by_id = {p["id"]: p for p in gold["people"]}
        misses = []
        for person in result["people"]:
            for field, outcome in person["fields"].items():
                if outcome["outcome"] in MISS:
                    misses.append({"person_id": person["id"], "event_id": person["event_id"], "name": person["name"],
                                   "field": field, "label": FIELD_LABEL.get(field, field), "outcome": outcome["outcome"],
                                   "gold": outcome["gold"], "pipeline": outcome["pipeline"],
                                   "pages": _page_links(by_id.get(person["id"], {}), field, gold.get("sources") or {})})
        tally = result["tally"]
        fields = []
        for field in check_people.FIELDS:
            c = tally["per_field"][field]
            n = c["hit"] + c["wrong"] + c["missing"]
            fields.append({"field": field, "label": FIELD_LABEL.get(field, field), "value_fields": n, "hit": c["hit"],
                           "wrong": c["wrong"], "missing": c["missing"], "blank_ok": c["blank_ok"], "invented": c["invented"],
                           "hit_rate": round(c["hit"] / n, 4) if n else None})
        events = [{"event_id": eid, "people": c["people"], "value_fields": c["value_fields"], "hits": c["hits"],
                   "hit_rate": round(c["hits"] / c["value_fields"], 4) if c["value_fields"] else None}
                  for eid, c in tally["per_event"].items()]
        payload = {"ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "overall": {"people": tally["people"], "fully_right": tally["fully_right"], "value_fields": tally["value_fields"],
                               "hits": tally["hits"], "wrong": tally["wrong"], "missing": tally["missing"], "invented": tally["invented"],
                               "hit_rate": round(tally["hits"] / tally["value_fields"], 4) if tally["value_fields"] else None},
                   "fields": fields, "events": events, "events_missing": result["events_missing"], "misses": misses}
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return payload


def cached() -> dict | None:
    """The last stored result, or None when the check has not run yet."""
    try:
        return json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
