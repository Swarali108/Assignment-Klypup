"""Deep dive: a reverse tree run. Start from one person and follow the leads that could mean more money.

Branch kinds (config/chat.py caps each one):
  same_person  the same name in another processed event (normalised names; unsure matches flagged)
  family       household members printed in the same filing (agents.identity family groups), and their own
               appearances in other events (depth 2)
  filing       related filings in the discovery index, matched on the person's companies (or the person's own
               name, when the holder is a company)
  process      a related filing that is not processed yet: processing it is estimated on its own and runs only
               when the confirmed deep dive included it and the budget still covers its high end

Most promising first: a priority queue on value (₹ crore, 1 when unknown) × recency (halves every
RECENCY_HALF_LIFE_DAYS). A visited set stops loops; each stop is reported as a step in plain words.
plan() runs the free branches without emitting anything, so the estimate is sized on the real tree.
"""

from __future__ import annotations

import heapq
import itertools
import re
from datetime import date

from agents.identity import identity_tokens
from api import store, views
from api.chat import actions, enrich_branch, tools
from api.chat import estimate as est
from config.chat import (DEEP_DIVE_BUDGET_USD, DEEP_DIVE_CAPS, DEEP_DIVE_MAX_DEPTH, RECENCY_HALF_LIFE_DAYS)

KIND_WORDS = {"same_person": "same person in other events", "family": "family members", "filing": "related filings",
              "process": "new events to process"}


def _recency(iso: str | None) -> float:
    """1.0 today, 0.5 after RECENCY_HALF_LIFE_DAYS (either side), 0.25 when there is no date."""
    if not iso:
        return 0.25
    try:
        days = abs((views.as_of() - date.fromisoformat(iso[:10])).days)
    except ValueError:
        return 0.25
    return 0.5 ** (days / RECENCY_HALF_LIFE_DAYS)


def _score(value_cr: float | None, iso: str | None) -> float:
    return round((value_cr if value_cr else 1.0) * _recency(iso), 6)


def _source_of(entry: dict) -> dict | None:
    """The first evidence link of a holder's name, else the event's first document."""
    event = entry["event"]
    card = views.person_card(event, entry["item"]["person"]["id"], None)
    for ref in (card or {}).get("name_evidence") or []:
        page = f", page {ref['printed_page']}" if ref.get("printed_page") else ""
        return {"label": f"{ref['doc_label']}{page}", "url": ref["url"], "source_url": ref["source_url"],
                "image_url": ref.get("image_url")}
    docs = views.documents_view(event)
    if docs:
        return {"label": docs[0]["label"], "url": docs[0]["url"], "source_url": docs[0]["source_url"], "image_url": None}
    return None


def _company_keys(entries: list[dict], name: str, holder_type: str) -> set[tuple[str, ...]]:
    """Identity tokens of the person's companies (and of the holder itself when it is an organisation)."""
    keys = {tuple(identity_tokens(e["event"]["spec"].company.lower())) for e in entries}
    if views.is_organisation(name, holder_type):
        keys.add(tuple(identity_tokens(name.lower())))
    return keys


class Tree:
    """The lineage being built: nodes, stop reasons, counts per kind, spend."""

    def __init__(self, budget: float):
        self.nodes: list[dict] = []
        self.stops: list[str] = []
        self.visited: set[str] = set()
        self.taken = {kind: 0 for kind in DEEP_DIVE_CAPS}
        self.capped: dict[str, int] = {}
        self.budget, self.spent = budget, 0.0
        self.process_candidates: list[dict] = []
        self.enrich_plan: list[dict] = []
        self.enrich_candidates: list[dict] = []  # Bright Data branches (api/chat/enrich_branch.py)

    def add(self, parent: str | None, kind: str, label: str, **fields) -> dict:
        node = {"id": f"n{len(self.nodes) + 1}", "parent": parent, "kind": kind, "label": label,
                "detail": fields.get("detail"), "amount": fields.get("amount"), "amount_cr": fields.get("amount_cr"),
                "date": fields.get("date"), "source": fields.get("source"), "status": fields.get("status", "followed"),
                "unsure": fields.get("unsure", False), "unsure_reason": fields.get("unsure_reason"),
                "event_id": fields.get("event_id"), "person_id": fields.get("person_id"), "score": fields.get("score"),
                "match": fields.get("match")}
        self.nodes.append(node)
        return node


def _appearance_node(tree: Tree, parent: str | None, entry: dict, kind: str, identity: dict, score: float) -> dict:
    item = entry["item"]
    return tree.add(parent, kind, f"{item['event']['company']} · {item['event']['type_label']}",
                    detail=f"{item['person']['role'] or 'Holder'}; {item['tier_label']}; {(item.get('timing') or {}).get('label') or ''}".strip("; "),
                    amount=item["amount"]["display"], amount_cr=item["amount"]["value_cr"],
                    date=views.money_date(entry["event"])["date_iso"], source=_source_of(entry),
                    unsure=identity["unsure"], unsure_reason=identity["unsure_reason"],
                    event_id=item["event"]["id"], person_id=item["person"]["id"], score=score)


def _plain_reason(reason: str) -> str:
    """The household rule's words in plain English: "'A B C' contains 'B C'" -> "shares the name B C"."""
    return re.sub(r"'[^']+' contains '([^']+)'", r"shares the name \1", views.clean(reason))


def _family_members(entry: dict) -> list[tuple[str, str]]:
    """(member name, reason) of the household groups this holder belongs to in this event."""
    doc = entry["event"]["out"]["people"] or {}
    found = []
    for group in doc.get("family_groups") or []:
        members = group.get("members") or []
        if entry["name"] in members:
            reason = "; ".join(group.get("reasons") or []) or "Printed as one family"
            found.extend((m, reason) for m in members if m != entry["name"])
    return found


def _related_filings(keys: set[tuple[str, ...]], known_events: set[str]) -> list[dict]:
    """Discovery items whose company matches one of the keys, newest first."""
    items = (store.discovery() or {}).get("items") or []
    found = []
    for item in items:
        if tuple(identity_tokens(str(item.get("company") or "").lower())) in keys:
            found.append(item)
    return sorted(found, key=lambda i: i.get("published_iso") or "", reverse=True)


def explore(identity: dict, budget: float = DEEP_DIVE_BUDGET_USD) -> Tree:
    """Run every free branch most-promising-first; collect the paid ones (processing) as candidates."""
    tree = Tree(budget)
    entries = identity["entries"]
    root = tree.add(None, "person", identity["name"], detail=identity.get("unsure_reason"),
                    amount=entries[0]["item"]["amount"]["display"], amount_cr=identity.get("best_cr"),
                    unsure=identity["unsure"], unsure_reason=identity["unsure_reason"])
    tree.enrich_plan = enrich_branch.plan(identity)
    enrich_branch.add_nodes(tree, root["id"], tree.enrich_plan)
    heap: list = []
    seq = itertools.count()

    def push(kind: str, key: str, score: float, parent: str, depth: int, payload: dict) -> None:
        heapq.heappush(heap, (-score, next(seq), kind, key, parent, depth, payload))

    for entry in entries:
        key = f"appearance:{entry['event']['spec'].event_id}/{entry['item']['person']['id']}"
        push("same_person", key, _score(entry["item"]["amount"]["value_cr"], views.money_date(entry["event"])["date_iso"]),
             root["id"], 1, {"entry": entry, "identity": identity})
    known_events = {e["event"]["spec"].event_id for e in entries}
    for item in _related_filings(_company_keys(entries, identity["name"], identity["holder_type"]), known_events):
        push("filing", f"filing:{item.get('id')}", _score(None, item.get("published_iso")) * 0.5, root["id"], 1, {"item": item})

    while heap:
        neg, _n, kind, key, parent, depth, payload = heapq.heappop(heap)
        if key in tree.visited:
            continue
        if tree.taken[kind] >= DEEP_DIVE_CAPS[kind]:
            tree.capped[kind] = tree.capped.get(kind, 0) + 1
            continue
        tree.visited.add(key)
        tree.taken[kind] += 1
        if kind in ("same_person",):
            node = _appearance_node(tree, parent, payload["entry"], kind, payload["identity"], -neg)
            if depth < DEEP_DIVE_MAX_DEPTH:
                for member, reason in _family_members(payload["entry"]):
                    found = tools.reverse_lookup(member)["identities"]
                    if found and found[0]["entries"] and found[0]["name"] != identity["name"]:
                        push("family", f"family:{member.lower()}", _score(found[0]["best_cr"], node["date"]), node["id"],
                             depth + 1, {"identity": found[0], "reason": reason,
                                         "event_id": payload["entry"]["event"]["spec"].event_id})
        elif kind == "family":
            member = payload["identity"]
            home = next((e for e in member["entries"] if e["event"]["spec"].event_id == payload["event_id"]), member["entries"][0])
            node = tree.add(parent, "family", member["name"], detail=f"Household link: {_plain_reason(payload['reason'])}",
                            amount=home["item"]["amount"]["display"], amount_cr=home["item"]["amount"]["value_cr"],
                            date=views.money_date(home["event"])["date_iso"], source=_source_of(home),
                            unsure=True, unsure_reason="family link read from the printed names; confirm with the client",
                            event_id=home["event"]["spec"].event_id, person_id=home["item"]["person"]["id"], score=-neg)
            for other in member["entries"]:
                if other is home:
                    continue
                key2 = f"appearance:{other['event']['spec'].event_id}/{other['item']['person']['id']}"
                push("same_person", key2, _score(other["item"]["amount"]["value_cr"], views.money_date(other["event"])["date_iso"]),
                     node["id"], depth + 1, {"entry": other, "identity": member})
        elif kind == "filing":
            item = payload["item"]
            event = store.find_event(item["event_id"]) if item.get("event_id") else None
            if not item.get("supported"):
                status_word = "not a supported event type"
            elif event is None:
                status_word = "an earlier or related filing, not linked to an event of its own"
            else:
                status_word = "already in the call lists" if event["processed"] else "not processed yet"
            node = tree.add(parent, "filing", views.clean(item.get("title")) or "Related filing",
                            detail=f"{views.clean(item.get('label')) or 'Filing'}, published {views.nice_date(item.get('published_iso'))}; {status_word}",
                            date=item.get("published_iso"), source={"label": item.get("source_name") or "Filing",
                                                                     "url": item.get("link"), "source_url": item.get("link"),
                                                                     "image_url": None}, score=-neg,
                            event_id=item.get("event_id"))
            if event and not event["processed"] and item.get("supported") and event["spec"].event_type in store.SUPPORTED_TYPES:
                push("process", f"process:{event['spec'].event_id}", -neg * 0.9, node["id"], depth + 1,
                     {"event": event})
        elif kind == "process":
            event = payload["event"]
            guess = actions.estimate({"kind": "event", "event_id": event["spec"].event_id, "title": event["spec"].company})
            node = tree.add(parent, "process", f"Process {event['spec'].company} · {views.type_label(event['spec'].event_type)}",
                            detail=f"Estimated ${guess['low']:.4f}–${guess['high']:.4f}, {guess['seconds_low']}–{guess['seconds_high']} s",
                            status="candidate", event_id=event["spec"].event_id, score=-neg)
            tree.process_candidates.append({"node": node, "event_id": event["spec"].event_id,
                                            "company": event["spec"].company, "estimate": guess})
    for kind, skipped in tree.capped.items():
        tree.stops.append(f"Stopped: cap of {DEEP_DIVE_CAPS[kind]} {KIND_WORDS[kind]} reached ({skipped} more not followed)")
    if not tree.capped:
        tree.stops.append("Stopped: nothing left to follow")
    return tree


def lineage_card(tree: Tree, title: str, home: tuple[str, str] | None = None) -> dict:
    """The tree as a 'lineage' card: items are nodes with parent ids (root first).

    The person's own appearance in the starting event (home) is not a second copy of the same money: it is folded
    into the root as its detail and link, and its children move up to the root. The tree itself is not changed.
    """
    nodes = tree.nodes
    drop = home_node(tree, home)
    if drop:
        root = {**nodes[0]}
        where = f"{drop['label']}: {drop['detail']}" if drop.get("detail") else drop["label"]
        root["detail"] = "; ".join(x for x in (where, root.get("detail")) if x)
        for field in ("event_id", "person_id", "source", "date"):
            root[field] = root.get(field) or drop.get(field)
        nodes = [root] + [{**n, "parent": root["id"]} if n["parent"] == drop["id"] else n for n in nodes[1:] if n is not drop]
    return {"kind": "lineage", "title": title, "items": nodes, "total": len(nodes),
            "stops": tree.stops, "budget_usd": tree.budget, "spent_usd": round(tree.spent, 6)}


THIRD_PARTY_KINDS = {"linkedin": "LinkedIn profile candidate", "web": "Web mention"}


def _writer_node(node: dict) -> dict:
    """A node as the writer model may see it. Third-party text (web titles, profile names and headlines) never
    reaches the model: it could carry instructions. The RM still sees that text in the lineage card."""
    fields = ("id", "parent", "kind", "label", "detail", "amount", "amount_cr", "date",
              "status", "unsure", "unsure_reason", "match")
    out = {k: node[k] for k in fields}
    if node["kind"] in THIRD_PARTY_KINDS:
        out.update(label=THIRD_PARTY_KINDS[node["kind"]], detail=None, date=None, unsure_reason=None)
    return out


def compact_tree(tree: Tree) -> dict:
    """The facts of the tree the writer may use (third-party text replaced by neutral labels; counts and match kept)."""
    return {"nodes": [_writer_node(n) for n in tree.nodes],
            "stops": tree.stops, "followed": len(tree.visited), "budget_usd": tree.budget, "spent_usd": round(tree.spent, 6)}


def run_processing(turn, tree: Tree, approved: list[str]):
    """Generator: process the approved candidates in order while the budget covers each one's high end."""
    for candidate in tree.process_candidates:
        node = candidate["node"]
        if candidate["event_id"] not in approved:
            node["status"] = "skipped"
            continue
        high = candidate["estimate"]["high"]
        if tree.spent + high > tree.budget:
            node["status"] = "stopped"
            tree.stops.append(f"Stopped: budget reached (${tree.spent:.4f} of ${tree.budget:.2f} used; "
                              f"processing {candidate['company']} could cost up to ${high:.4f})")
            yield from turn.note(tree.stops[-1], "skipped")
            continue
        before = turn.spent
        try:
            result = yield from actions.run(turn, {"kind": "event", "event_id": candidate["event_id"],
                                                    "title": candidate["company"]})
            node["status"] = "processed"
            node["detail"] = f"Processed: {result['data']['people_to_call']} people to call"
        except actions.TargetError as exc:
            node["status"] = "failed"
            node["detail"] = str(exc)
        tree.spent = round(tree.spent + (turn.spent - before), 6)


def estimate_rows(tree: Tree) -> list[dict]:
    """Breakdown rows for the deep dive's paid parts: each processing candidate (the writer is added by the agent)."""
    rows = []
    spent_high = 0.0
    for candidate in tree.process_candidates:
        guess = candidate["estimate"]
        if spent_high + guess["high"] > tree.budget:
            continue
        spent_high += guess["high"]
        rows.append({"step": f"Process {candidate['company']} (follow-on lead)", "model": "pipeline",
                     "calls": sum(r["calls"] for r in guess["breakdown"]), "cost_usd": guess["high"],
                     "cost_usd_low": guess["low"], "cost_usd_high": guess["high"], "event_id": candidate["event_id"]})
    return rows


def home_node(tree: Tree, home: tuple[str, str] | None) -> dict | None:
    """The person's own appearance in the event the deep dive started from (a same_person child of the root)."""
    if not home or not tree.nodes:
        return None
    root = tree.nodes[0]["id"]
    return next((n for n in tree.nodes if n["kind"] == "same_person" and n["parent"] == root
                 and (n["event_id"], n["person_id"]) == home), None)


def free_rows(tree: Tree, home: tuple[str, str] | None = None) -> list[dict]:
    """$0 breakdown rows for the code branches. home = (event_id, person_id) of the starting appearance, which is
    the person's own event and not "another event"."""
    count = lambda kind: sum(1 for n in tree.nodes if n["kind"] == kind)  # noqa: E731
    others = count("same_person") - (1 if home_node(tree, home) else 0)
    return [{"step": f"Same person in other events ({others})", "model": None, "calls": 0, "cost_usd": 0.0},
            {"step": f"Family and household ({count('family')})", "model": None, "calls": 0, "cost_usd": 0.0},
            {"step": f"Related filings in the discovery index ({count('filing')})", "model": None, "calls": 0,
             "cost_usd": 0.0}]


def total_estimate_seconds(tree: Tree, approved: list[str]) -> tuple[int, int]:
    """(low, high) seconds for the approved processing plus a few seconds of code and writing."""
    low, high = 3, 20
    for candidate in tree.process_candidates:
        if candidate["event_id"] in approved:
            low += candidate["estimate"]["seconds_low"]
            high += candidate["estimate"]["seconds_high"]
    return low, high


def budget_default() -> float:
    return DEEP_DIVE_BUDGET_USD


__all__ = ["explore", "lineage_card", "compact_tree", "run_processing", "estimate_rows", "free_rows", "est"]
