"""Human review queue and the decisions it stores.

A review item is something the pipeline was not sure about, found in files it already wrote:
  pair    identity_log pair the model decided, or a near-miss kept apart (same words, different numbers / first name)
  holder  a holder the pipeline could not call a person or an organisation (holder_type "unsure")
  low     a callable row whose confidence is low
Decisions go to the database (who, when) and to outputs/overrides.json. api/store.load_events() applies that file to
every event it loads, so every view (Today, events, person card, chat, exports) shows the decision at once:
  holder confirm / reject   relabel the holder as a person / an organisation (moves it to the right list)
  low reject                hide the row from the call lists
  pair merge                the second name is the same holder as the first: its row is hidden, the first stays
  pair confirm / reject     recorded; no data changes (a wrong merge is split at the next re-run of the event)
The pipeline's own files are never edited.
"""

from __future__ import annotations

import copy
import json
import re
import threading
from datetime import datetime, timezone

from api import db, store, views

FILE_NAME = "overrides.json"
_LOCK = threading.Lock()
NEAR_MISS_SCORE = 85.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def file_path():
    return store.OUTPUTS_DIR / FILE_NAME


def decisions() -> dict[str, dict]:
    """id -> decision, from outputs/overrides.json."""
    doc = store.read_json(file_path())
    items = doc.get("decisions") if isinstance(doc, dict) else None
    return {d["id"]: d for d in items or [] if isinstance(d, dict) and d.get("id")}


def _event_decisions(event_id: str) -> list[dict]:
    return [d for d in decisions().values() if d.get("event_id") == event_id]


# ---------- applying ----------

def apply(event_id: str, out: dict) -> dict:
    """The outputs of one event with this event's decisions applied (a copy; stored files are never changed)."""
    mine = _event_decisions(event_id)
    if not mine or not out.get("ranked"):
        return out
    hide: set[str] = set()
    relabel: dict[str, str] = {}
    for d in mine:
        if d["kind"] == "holder" and d["action"] in ("confirm", "reject") and d.get("value") in ("person", "entity"):
            relabel[d["person_ids"][0]] = d["value"]
        elif d["kind"] == "low" and d["action"] == "reject":
            hide.update(d["person_ids"])
        elif d["kind"] == "pair" and d["action"] == "merge" and len(d.get("person_ids") or []) == 2:
            hide.add(d["person_ids"][1])
    if not hide and not relabel:
        return out
    out = {**out}
    ranked = copy.deepcopy(out["ranked"])
    for group in ("callable", "entities", "context"):
        if group in ranked:
            ranked[group] = [e for e in ranked[group] if e.get("person_id") not in hide]
            for entry in ranked[group]:
                if entry.get("person_id") in relabel:
                    entry["holder_type"] = relabel[entry["person_id"]]
    out["ranked"] = ranked
    if out.get("people") and relabel:
        people = {**out["people"]}
        people["people"] = [({**p, "holder_type": relabel[p["person_id"]]} if p.get("person_id") in relabel else p)
                            for p in people.get("people") or []]
        out["people"] = people
    return out


LABELS = {("holder", "confirm"): "Confirmed as a person", ("holder", "reject"): "Marked as an organisation",
          ("low", "confirm"): "Checked, keeps its place", ("low", "reject"): "Removed from the call lists",
          ("pair", "confirm"): "Confirmed as the pipeline decided", ("pair", "reject"): "Marked as a wrong decision",
          ("pair", "merge"): "Merged: the same holder"}


def note_for(d: dict) -> dict:
    """{label, by, at, action} for the small 'Reviewed by' line."""
    return {"id": d["id"], "label": LABELS.get((d["kind"], d["action"]), d["action"]), "action": d["action"],
            "by": d.get("by_name") or d.get("by") or "", "at": d.get("at")}


def for_person(event_id: str, person_id: str) -> list[dict]:
    """Decisions that touch one person (for the call card's 'Reviewed by' note)."""
    return [note_for(d) for d in _event_decisions(event_id) if person_id in (d.get("person_ids") or [])]


# ---------- the queue ----------

def _find(people: list[dict], name: str) -> str | None:
    wanted = _norm(name)
    for p in people:
        if wanted and wanted in {_norm(n) for n in [p.get("name_as_printed")] + list(p.get("names_as_printed") or [])}:
            return p["person_id"]
    return None


def queue(events: list[dict]) -> list[dict]:
    """Every open and decided item, open first: [{id, kind, event, title, why, names, actions, decision|None}]."""
    done = decisions()
    items: list[dict] = []
    for event in events:
        if not event["processed"]:
            continue
        spec, doc = event["spec"], event["out"]["people"] or {}
        people = doc.get("people") or []
        ref = views.event_ref(event)
        for log in doc.get("identity_log") or []:
            near = log.get("method") in ("numbers_differ", "different_first_name") and (log.get("score") or 0) >= NEAR_MISS_SCORE
            if log.get("method") != "llm" and not near:
                continue
            a, b = log["pair"]
            merged = log.get("outcome") == "merge"
            ids = [x for x in (_find(people, a), _find(people, b)) if x]
            if merged and len(ids) == 2 and ids[0] == ids[1]:
                ids = ids[:1]
            iid = f"pair|{spec.event_id}|{_norm(a)}|{_norm(b)}"
            why = views.clean(log.get("llm_reason")) or (
                "The names are almost the same but the share numbers differ." if log.get("method") == "numbers_differ"
                else "The names are close but the first names differ.")
            actions = ([{"action": "confirm", "label": "Keep as one"}, {"action": "reject", "label": "They are different"}]
                       if merged else [{"action": "confirm", "label": "Keep apart"}]
                       + ([{"action": "merge", "label": "Same holder, merge"}] if len(ids) == 2 and ids[0] != ids[1] else []))
            items.append({"id": iid, "kind": "pair", "event": ref, "person_ids": ids, "names": [a, b],
                          "title": "Are these the same holder?", "why": why, "score": log.get("score"),
                          "pipeline": "Treated as one holder" if merged else "Treated as two holders",
                          "by": "the language model" if log.get("method") == "llm" else "name rules", "actions": actions})
        for person in people:
            if person.get("holder_type") == "unsure":
                items.append({"id": f"holder|{spec.event_id}|{person['person_id']}", "kind": "holder", "event": ref,
                              "person_ids": [person["person_id"]], "names": [person.get("name_as_printed")],
                              "title": "A person or an organisation?",
                              "why": views.clean(person.get("holder_type_reason")) or "The pipeline could not tell.",
                              "pipeline": "Left unsure", "by": "name rules",
                              "actions": [{"action": "confirm", "label": "A person", "value": "person"},
                                          {"action": "reject", "label": "An organisation", "value": "entity"}]})
        for item in views.event_lists(event, {})["callable"]:
            if item["confidence"]["level"] == "low":
                pid = item["person"]["id"]
                items.append({"id": f"low|{spec.event_id}|{pid}", "kind": "low", "event": ref, "person_ids": [pid],
                              "names": [item["person"]["name"]], "title": "Low-confidence call row",
                              "why": views.clean(item["confidence"].get("reason")) or "The pipeline marked this row low.",
                              "pipeline": f"Listed with {item['amount']['display']}", "by": "checks on the filing",
                              "link": f"/people/{spec.event_id}/{pid}",
                              "actions": [{"action": "confirm", "label": "Looks right"},
                                          {"action": "reject", "label": "Remove from call lists"}]})
    seen = {i["id"] for i in items}
    refs = {e["spec"].event_id: views.event_ref(e) for e in events}
    for d in done.values():  # a decided row can leave its list (hidden, relabelled): keep it here so it can be undone
        if d["id"] not in seen and d["event_id"] in refs:
            items.append({"id": d["id"], "kind": d["kind"], "event": refs[d["event_id"]], "person_ids": d.get("person_ids") or [],
                          "names": d.get("names") or [], "title": {"pair": "Are these the same holder?", "holder":
                          "A person or an organisation?", "low": "Low-confidence call row"}[d["kind"]],
                          "why": "Decided earlier; the row has left the lists it was in.", "pipeline": "", "by": "",
                          "actions": []})
    for item in items:
        d = done.get(item["id"])
        item["decision"] = note_for(d) if d else None
    items.sort(key=lambda i: (i["decision"] is not None, {"holder": 0, "pair": 1, "low": 2}[i["kind"]], i["id"]))
    return items


def _write(rows: list[dict], stamp: str) -> None:
    with _LOCK:
        file_path().parent.mkdir(parents=True, exist_ok=True)
        tmp = file_path().with_suffix(".tmp")
        tmp.write_text(json.dumps({"updated_at": stamp, "decisions": rows}, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(file_path())


def undo(item_id: str) -> bool:
    """Remove one decision (database and file). False when there was none."""
    with db.connect() as conn:
        had = bool(conn.query("SELECT id FROM review_decisions WHERE id = %s", (item_id,)))
        conn.execute("DELETE FROM review_decisions WHERE id = %s", (item_id,))
        rows = conn.query("SELECT payload FROM review_decisions ORDER BY decided_at")
    _write([json.loads(r["payload"]) for r in rows], _now())
    return had


def decide(events: list[dict], item_id: str, action: str, user: dict) -> dict:
    """Store one decision (database + outputs/overrides.json). ValueError for an unknown item or action."""
    found = next((i for i in queue(events) if i["id"] == item_id), None)
    if found is None:
        raise ValueError("That item is no longer in the queue")
    chosen = next((a for a in found["actions"] if a["action"] == action), None)
    if chosen is None:
        raise ValueError("That action does not apply to this item")
    record = {"id": item_id, "event_id": found["event"]["id"], "kind": found["kind"], "action": action,
              "value": chosen.get("value"), "person_ids": found["person_ids"], "names": found["names"],
              "by": user["email"], "by_name": user.get("name") or user["email"], "at": _now()}
    with db.connect() as conn:
        conn.execute("DELETE FROM review_decisions WHERE id = %s", (item_id,))
        conn.execute("""INSERT INTO review_decisions (id, event_id, kind, action, value, payload, decided_by,
                        decided_by_name, decided_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                     (item_id, record["event_id"], record["kind"], action, record["value"],
                      json.dumps(record, ensure_ascii=False), record["by"], record["by_name"], record["at"]))
        rows = conn.query("SELECT payload FROM review_decisions ORDER BY decided_at")
    _write([json.loads(r["payload"]) for r in rows], record["at"])
    return note_for(record)
