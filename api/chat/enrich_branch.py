"""Deep-dive branches for public enrichment: a LinkedIn profile and web mentions (Bright Data).

Both are paid steps measured in Bright Data requests (no dollars on the free tier), so they follow the same
estimate -> confirm flow as processing an event: the estimate card lists them with a worst-case request count, and
they run only when the confirmed target names them. Results are written to the same per-person store the person
page reads (api/enrichment.py), so a lookup made here shows there for free.

Rules (owner, 2026-11-15/16): LinkedIn is on by default (LINKEDIN_ENRICHMENT=off stops it); public professional
fields only; every LinkedIn match carries its level and the reason; an unconfirmed match is never merged into the
person's facts; web results are leads labelled "from web search, not verified".
"""

from __future__ import annotations

from api import enrichment
from config import enrichment as cfg
from tools import brightdata as bd

NODE_CAP = {"linkedin": 3, "web": 5}
MATCH_WORDS = {"likely": "Likely match", "unconfirmed": "Unconfirmed match"}
PARENT_LABEL = {"linkedin": "Public LinkedIn profile (Bright Data)", "web": "Mentions on the web (Bright Data)"}


def plan(identity: dict) -> list[dict]:
    """The enrichment branches that could run for this person: [{kind, event_id, person_id, requests, cached}].
    Empty when Bright Data is not connected, the holder is an organisation, or the switches are off."""
    entries = identity.get("entries") or []
    if not entries or not enrichment.token_configured():
        return []
    event_id = entries[0]["event"]["spec"].event_id
    person_id = entries[0]["item"]["person"]["id"]
    try:
        found = enrichment.estimate(event_id, person_id, enrichment.KINDS)
    except KeyError:
        return []
    return [{"kind": kind, "event_id": event_id, "person_id": person_id, "requests": info["requests"],
             "cached": info["cached"], "worst_case": info["worst_case"]}
            for kind, info in found["kinds"].items() if info["allowed"]]


def estimate_rows(candidates: list[dict]) -> list[dict]:
    """Breakdown rows for the estimate card: calls = Bright Data requests (worst case), $0 on the free tier."""
    rows = []
    for c in candidates:
        label = "LinkedIn profile search by name (Bright Data)" if c["kind"] == "linkedin" else "Web mentions search (Bright Data)"
        rows.append({"step": label + (" (saved copy, no request)" if c["cached"] else ""), "model": None,
                     "calls": c["requests"], "cost_usd": 0.0, "brightdata_requests": c["requests"],
                     "cached": c["cached"], "kind": c["kind"]})
    return rows


def basis(candidates: list[dict]) -> str:
    """One sentence for the estimate card's basis line."""
    if not candidates:
        return ""
    total = sum(c["requests"] for c in candidates)
    try:
        left = bd.usage_summary()["remaining"]
        cap = f" {left:,} of this month's Bright Data requests are left."
    except bd.BrightDataError:
        cap = ""
    return (f"Public lookups use up to {total} Bright Data requests (counted, not dollars, on the free allowance); "
            f"a saved copy costs none.{cap}")


def over_cap(candidates: list[dict]) -> str | None:
    """A plain reason when the worst case could cross the monthly cap, else None."""
    total = sum(c["requests"] for c in candidates)
    try:
        usage = bd.usage_summary()
    except bd.BrightDataError as exc:
        return str(exc)
    if total > usage["remaining"]:
        return f"Bright Data lookups could need {total} requests but only {usage['remaining']} are left this month."
    return None


def add_nodes(tree, root_id: str, candidates: list[dict]) -> None:
    """Candidate nodes under the root so the lineage shows them (status 'candidate' until they run or are skipped)."""
    for c in candidates:
        node = tree.add(root_id, c["kind"], PARENT_LABEL[c["kind"]],
                        detail=("Saved copy, no new request" if c["cached"] else f"Up to {c['requests']} requests, only when confirmed"),
                        status="candidate")
        tree.enrich_candidates.append({**c, "node": node})


def _candidate_nodes(tree, parent: dict, record: dict, kind: str) -> None:
    block = record.get(kind) or {}
    if kind == "linkedin":
        found = block.get("candidates") or []
        parent["label"] = (f"Public LinkedIn profile: {len(found)} with this name" if len(found) != 1 else "Public LinkedIn profile: 1 with this name") if found else "Public LinkedIn profile: none found"
        parent["detail"] = "Public professional fields only. Nothing here is added to the person's facts."
        for cand in found[: NODE_CAP["linkedin"]]:
            # The card draws the level as a badge, so the detail line carries only the reason and the profile's context.
            match = cand.get("match") if cand.get("match") in MATCH_WORDS else "unconfirmed"
            sub = " · ".join(x for x in [cand.get("headline"), cand.get("city")] if x)
            tree.add(parent["id"], "linkedin", cand.get("name") or "LinkedIn profile",
                     detail=" ".join(x for x in [cand.get("reason"), sub] if x) or None,
                     date=(cand.get("fetched_at") or "")[:10] or None, match=match,
                     source={"label": "LinkedIn profile (public)", "url": cand.get("profile_url"), "source_url": cand.get("profile_url"), "image_url": None},
                     status="followed")
    else:
        rows = block.get("rows") or []
        parent["label"] = f"Mentions on the web: {len(rows)} found" if rows else "Mentions on the web: none found"
        parent["detail"] = cfg.SEARCH_LABEL
        for row in rows[: NODE_CAP["web"]]:
            tree.add(parent["id"], "web", row.get("title") or "Web result",
                     detail=row.get("date") or None,  # the source is the link label; the caveat is on the parent
                     date=None, match=None,
                     source={"label": row.get("source") or "Web result", "url": row.get("url"), "source_url": row.get("url"), "image_url": None},
                     status="followed")


def run(turn, tree, approved: list[str]):
    """Generator: run the approved lookups (one step each), fill the lineage nodes, mark the rest skipped."""
    for c in tree.enrich_candidates:
        node, kind = c["node"], c["kind"]
        if kind not in approved:
            node["status"] = "skipped"
            node["detail"] = "Not in the confirmed estimate"
            continue
        word = "public LinkedIn profile" if kind == "linkedin" else "mentions on the web"
        step = yield from turn.begin(f"Looking up the {word}", detail="Bright Data")
        try:
            record = enrichment.run(c["event_id"], c["person_id"], [kind], refresh=False)
        except (bd.BrightDataError, KeyError) as exc:
            node["status"], node["detail"] = "failed", str(exc)
            yield from turn.end(step, "failed", str(exc))
            continue
        block = record.get(kind) or {}
        if block.get("error") and block.get("state") not in ("found", "none"):
            node["status"], node["detail"] = "failed", block["error"]
            yield from turn.end(step, "failed", block["error"])
            continue
        node["status"] = "processed"
        _candidate_nodes(tree, node, record, kind)
        found = len(block.get("candidates") or block.get("rows") or [])
        yield from turn.end(step, detail=f"{found} found, {block.get('requests') or 0} requests used")
