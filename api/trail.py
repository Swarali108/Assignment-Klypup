"""GET /api/people/{event}/{person}/trail: "How we found them", assembled from files the pipeline already wrote.

Sources (all under outputs/<event>/): locate.json (pages scored), extract.json (rows, quotes, rejections, chosen
pages), people.json (merged people, identity decisions, families, money and timing rules), ranked.json (tier and
score parts), briefs.json (brief, placeholders, attempts), cost.json (per-person spend), trace.json (which model
ran which step, cached or fresh), plus the stored enrichment result (api/enrichment.py). Nothing here calls a model
or the network, and nothing is invented: a step with no data says so.

Response: {event, person, steps: [{key, title, summary, status, ...step data}], generated_from: [file names]}.
status is "ok" (all good), "warn" (something was rejected or is unsure), "info" or "none" (nothing to show).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from api import auth, enrichment, rm_state, store, views
from config.ranking import UNKNOWN_SPLIT_WEIGHT

router = APIRouter()

PLAIN_PAGE_CHOICE = {"top pages": "The highest-scoring pages for this table"}
CHECKS_APPLIED = [
    "The quote is on the page it cites",
    "The value is inside the quote",
    "The name sits in the same table row as the value",
    "A role heading sits above the name, with no other heading between",
]
MATCH_WORDS = {"same_tokens": "same words in a different spelling", "different_first_name": "different first name",
               "below_threshold": "names too different", "llm": "settled by a stronger model"}


def _fold(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _read(event: dict, key: str) -> dict:
    """An output file of the event (loaded by api.store when it is one of OUTPUT_FILES, else read directly)."""
    if key in event["out"]:
        return event["out"].get(key) or {}
    found = store.read_json(store.OUTPUTS_DIR / event["spec"].event_id / f"{key}.json")
    return found if isinstance(found, dict) else {}


def _trace(event_id: str) -> dict:
    """trace.json (or one rebuilt from logs); {} when neither exists."""
    try:
        from tools.trace import load_trace

        return load_trace(event_id, store.OUTPUTS_DIR / event_id) or {}
    except Exception:  # a damaged trace must not hide the rest of the trail
        return {}


def _agents(trace: dict) -> dict[str, dict]:
    return {a.get("name"): a for a in trace.get("agents") or []}


def _section_label(section: str) -> str:
    return views.SECTION_LABELS.get(section, section.replace("_", " ").capitalize())


def _field_label(field: str) -> str:
    return views.FIELD_LABELS.get(field, field.replace("_", " ").capitalize())


def _page_choice_words(text: str | None) -> str:
    if not text:
        return "The highest-scoring pages for this table"
    if text in PLAIN_PAGE_CHOICE:
        return PLAIN_PAGE_CHOICE[text]
    match = re.match(r"must_contain matched: (.+)", text)
    return f"Pages that contain “{match.group(1)}”" if match else views.clean(text)


# ---------- steps ----------

def documents_step(event: dict, locate: dict) -> dict:
    labels = views.doc_labels(event)
    counts = {d.get("url"): d.get("page_count") for d in locate.get("documents") or []}
    docs = []
    for doc in event["spec"].documents:
        sha = store.url_sha(doc.url)
        cached = store.pdf_path(sha) is not None
        docs.append({"label": labels.get(doc.url, "Source document"), "url": f"/api/docs/{sha}.pdf" if cached else doc.url,
                     "source_url": doc.url, "cached": cached, "pages": counts.get(doc.url)})
    pages = sum(d["pages"] or 0 for d in docs)
    return {"key": "documents", "title": "The documents we started from", "status": "ok" if docs else "none",
            "summary": (f"{len(docs)} source document{'s' if len(docs) != 1 else ''}" + (f", {pages:,} pages in all" if pages else "")
                        if docs else "No source documents are listed for this event."),
            "documents": docs}


def pages_step(person: dict, labels: dict, locate: dict, extract: dict, agents: dict) -> dict:
    """For each table this person was read from: the pages the locator chose, their score and why."""
    sections: dict[str, set] = {}
    for ref in person.get("evidence") or []:
        if ref.get("field_kept", True) and ref.get("section"):
            sections.setdefault(ref["section"], set()).add(ref.get("pdf_index"))
    out = []
    for section, used in sections.items():
        scored = {h.get("pdf_index"): h for h in (locate.get("sections") or {}).get(section) or []}
        chosen = (extract.get("chosen_pages") or {}).get(section) or []
        pages = []
        for item in chosen:
            hit = scored.get(item.get("pdf_index")) or {}
            pages.append({"pdf_index": item.get("pdf_index"), "printed_page": item.get("printed_page"),
                          "score": hit.get("score"), "terms": [views.clean(t) for t in hit.get("matched_terms") or []][:4],
                          "used": item.get("pdf_index") in used,
                          "doc_label": labels.get(hit.get("source_url") or "", None)})
        out.append({"section": section, "label": _section_label(section),
                    "why": _page_choice_words((extract.get("page_choice") or {}).get(section)), "pages": pages})
    used_count = sum(1 for s in out for p in s["pages"] if p["used"])
    return {"key": "pages", "title": "Pages the locator chose", "status": "ok" if out else "none",
            "summary": (f"{len(out)} tables read; {used_count} pages carried this person" if out else "No table pages are recorded for this person."),
            "sections": out}


def quotes_step(person: dict, labels: dict, agents: dict, extract: dict) -> dict:
    """Every quote kept for this person, grouped by table, with the model that read it and whether it was cached."""
    groups: dict[str, dict] = {}
    for ref in person.get("evidence") or []:
        if not ref.get("field_kept", True):
            continue
        section = ref.get("section") or "other"
        shown = views.evidence_ref(ref, labels)
        if shown is None:
            continue
        agent = agents.get(f"extract_{section}") or {}
        group = groups.setdefault(section, {
            "section": section, "label": _section_label(section),
            "model": agent.get("runs_on") if agent.get("runs_on") not in (None, "code") else None,
            "cached": (agent.get("calls") and agent.get("cached_calls") == agent.get("calls")) if agent else None,
            "calls": agent.get("calls"), "prompt_version": None, "rows": []})
        field = ref.get("field") or ""
        value = person.get(field)
        group["rows"].append({"field": field, "label": _field_label(field), "value": views.clean(value) if isinstance(value, str) else None,
                              "quote": ref.get("quote"), "evidence": shown, "page_corrected": bool(ref.get("citation_corrected"))})
    total = sum(len(g["rows"]) for g in groups.values())
    models = sorted({g["model"] for g in groups.values() if g["model"]})
    return {"key": "quotes", "title": "What the filings say about them", "status": "ok" if total else "none",
            "summary": (f"{total} quotes from {len(groups)} tables" + (f", read by {', '.join(models)}" if models else "")) if total else "No quotes are stored for this person.",
            "prompt_version": None, "groups": list(groups.values())}


def checks_step(person: dict, extract: dict, labels: dict) -> dict:
    """Checks that passed and the fields that were rejected, with plain reasons."""
    mine = {_fold(n) for n in [person.get("name_as_printed"), *(person.get("names_as_printed") or [])] if n}
    rejected = [{"field": r.get("field"), "label": _field_label(r.get("field") or ""), "value": views.clean(r.get("value")),
                 "section": _section_label(r.get("section") or ""),
                 "reason": views.REJECTION_WORDS.get(r.get("reason"), views.clean(r.get("reason")))}
                for r in extract.get("rejections") or [] if _fold(r.get("row")) in mine]
    kept = [r for r in person.get("evidence") or [] if r.get("field_kept", True)]
    corrected = sum(1 for r in kept if r.get("citation_corrected"))
    passed = [{"label": _field_label(r.get("field") or ""), "section": _section_label(r.get("section") or ""),
               "page": r.get("printed_page") or r.get("pdf_index"), "corrected": bool(r.get("citation_corrected"))} for r in kept]
    conflicts = [{"field": _field_label(k), "detail": views.clean(str(v))} for k, v in (person.get("conflicts") or {}).items()]
    return {"key": "checks", "title": "Checks every quote had to pass", "status": "warn" if rejected or conflicts else "ok",
            "summary": f"{len(passed)} checked facts kept" + (f"; {len(rejected)} rejected" if rejected else "; none rejected")
                       + (f"; {corrected} page references corrected" if corrected else ""),
            "applied": CHECKS_APPLIED, "passed": passed, "rejected": rejected, "conflicts": conflicts}


def identity_step(person: dict, people_doc: dict, event_id: str) -> dict:
    """Name merges, strong-model checks and family links."""
    names = person.get("names_as_printed") or [person.get("name_as_printed")]
    mine = {_fold(n) for n in names if n}
    merges, asks = [], 0
    for row in people_doc.get("identity_log") or []:
        pair = row.get("pair") or []
        if not any(_fold(n) in mine for n in pair) or row.get("method") == "below_threshold":
            continue
        if row.get("method") == "llm":
            asks += 1
        merges.append({"pair": pair, "score": row.get("score"), "outcome": row.get("outcome"),
                       "method": MATCH_WORDS.get(row.get("method"), views.clean(row.get("method")))})
    family = None
    for group in people_doc.get("family_groups") or []:
        if person.get("name_as_printed") in (group.get("members") or []) or any(_fold(m) in mine for m in group.get("members") or []):
            family = {"members": [m for m in group.get("members") or [] if _fold(m) not in mine],
                      "reasons": [views.clean(r) for r in group.get("reasons") or []]}
    other = 0
    try:
        from api.chat import tools

        for found in tools.reverse_lookup(person.get("name_as_printed") or "")["identities"]:
            other += sum(1 for e in found["entries"] if e["event"]["spec"].event_id != event_id)
    except Exception:
        other = 0
    merged = [m for m in merges if m["outcome"] == "merge"]
    bits = [f"{len(names)} spelling{'s' if len(names) != 1 else ''} joined" if len(names) > 1 else "one spelling",
            f"family link to {len(family['members'])} other" + ("s" if len(family["members"]) != 1 else "") if family and family["members"] else None,
            "borderline pairs settled by a stronger model" if asks else None]
    return {"key": "identity", "title": "Same person? Family?", "status": "warn" if person.get("holder_type") == "unsure" else "ok",
            "summary": "; ".join(b for b in bits if b),
            "names": names, "holder_type": person.get("holder_type"), "holder_type_reason": views.clean(person.get("holder_type_reason")) or None,
            "merges": merges, "merged": len(merged), "family": family, "strong_model_checks": asks, "other_filings": other}


def money_step(card: dict) -> dict:
    """The rupee formulas with source pages and the lock-in rule, reused from the call card."""
    amounts = card.get("amounts") or []
    timing = card.get("timing_detail") or []
    return {"key": "money", "title": "How the rupees and dates were worked out", "status": "ok" if amounts else "none",
            "summary": (f"{len(amounts)} amount{'s' if len(amounts) != 1 else ''} worked out from printed values"
                        + (f"; {len(timing)} date rule{'s' if len(timing) != 1 else ''}" if timing else "")) if amounts else "No amount could be worked out from the filings.",
            "amounts": amounts, "timing": timing}


def rank_step(entry: dict, group: str, swaps: dict | None = None) -> dict:
    """Tier, rank and the parts of the score."""
    if not entry:
        return {"key": "rank", "title": "Why they sit where they do", "status": "none", "summary": "This person was not ranked.", "parts": []}
    trig = entry.get("trigger") or {}
    parts = []

    def part(label: str, value, note: str):
        if value not in (None, ""):
            parts.append({"label": label, "value": str(value), "note": note})

    # The factors agents/rank.py multiplied for the score shown: the chosen trigger's, or with no trigger the
    # later score (value of shares kept × confidence × timing of the shares kept).
    if trig:
        by_holding = trig.get("rank_value_crore")
        part("Money counted", f"₹{by_holding or trig.get('money_crore')} Cr",
             ("the whole holding; " if by_holding else "") + (trig.get("label") or ""))
        if by_holding:
            part("Unlocked share", UNKNOWN_SPLIT_WEIGHT[0], UNKNOWN_SPLIT_WEIGHT[1])
        part("Confidence", entry.get("confidence_weight"), f"{entry.get('confidence')} confidence")
        part("Timing", trig.get("timing_weight"), (trig.get("timing_status") or "").replace("_", " "))
        part("Recency", trig.get("recency_weight"), f"{trig.get('days_since')} days ago" if trig.get("days_since") is not None else "")
    else:
        part("Money counted", f"₹{entry.get('later_value_crore')} Cr", "value of the shares they keep")
        part("Confidence", entry.get("confidence_weight"), f"{entry.get('confidence')} confidence")
        part("Timing", entry.get("timing_weight"), (entry.get("timing_status") or "").replace("_", " "))
    # With a trigger, the later score is only a tie-breaker; without one it is the score itself (shown above).
    later = {"value_cr": entry.get("later_value_crore"), "score": entry.get("later_score")} if trig and entry.get("later_score") else None
    return {"key": "rank", "title": "Why they sit where they do", "status": "ok",
            "summary": (f"Rank {entry.get('rank')} · {entry.get('call_tier_label') or entry.get('tier')}"
                        + (f" · score {float(entry['score']):.2f}" if entry.get("score") else "")),
            "group": group, "rank": entry.get("rank"), "tier": entry.get("call_tier_label") or entry.get("tier"),
            "score": entry.get("score"),
            # day counts the pipeline stored on the day it ran are recounted to today, as on the call card
            "parts": [{**p, "note": views.with_fresh_ages(p.get("note") or "", swaps or {}) or p.get("note")} for p in parts],
            "later": later,
            "reasons": [views.with_fresh_ages(r, swaps or {}) for r in views.rank_reason_words(entry.get("rank_reasons") or [])]}


def brief_step(brief: dict, briefs_doc: dict, agents: dict, person: dict, swaps: dict | None = None) -> dict:
    if not brief:
        return {"key": "brief", "title": "The call brief", "status": "none", "summary": "No brief was written for this person."}
    agent = agents.get("brief") or {}
    attempts = [{"n": i + 1, "problem": views.clean(a.get("problem")) or None} for i, a in enumerate(brief.get("attempts") or [])]
    llm = brief.get("brief_source") == "llm"
    placeholders = [{"key": k, "value": views.clean(v)} for k, v in (brief.get("placeholders") or {}).items()]
    template = None
    if llm and brief.get("attempts"):
        template = (brief["attempts"][-1].get("raw_lines") or None)
    fallback = views.clean(brief.get("fallback_reason")) or None
    return {"key": "brief", "title": "The call brief", "status": "warn" if fallback else "ok",
            "summary": ("Written by the assistant from a fixed template" if llm else "Written from a template (the assistant's draft was not used)")
                       + (f" · {len(attempts)} attempt{'s' if len(attempts) != 1 else ''}" if len(attempts) > 1 else ""),
            "written_by": "assistant" if llm else "template", "model": agent.get("runs_on") if llm and agent.get("runs_on") != "code" else None,
            "prompt_version": briefs_doc.get("prompt_version"), "attempts": attempts, "fallback_reason": fallback,
            "placeholders": placeholders, "template_lines": template,
            "lines": views.tidy_lines(views.fresh_brief_lines(brief, swaps or {}), person)}


def enrichment_step(event_id: str, person_id: str) -> dict:
    record = enrichment.load(event_id, person_id)
    if not record:
        return {"key": "enrichment", "title": "Public profile and web mentions", "status": "none",
                "summary": "Not looked up yet. This is a paid step and runs only when you confirm it.", "linkedin": None, "web": None}
    li, web = record.get("linkedin"), record.get("web")
    parts = []
    if li:
        best = (li.get("candidates") or [None])[0]
        parts.append(("LinkedIn: " + (f"{best['match']} match" if best else "no public profile found")) if li.get("state") in ("found", "none") else "LinkedIn: not looked up")
    if web:
        parts.append(f"{len(web.get('rows') or [])} web mentions" if web.get("state") in ("found", "none") else "web: not looked up")
    requests = sum((record.get(k) or {}).get("requests") or 0 for k in ("linkedin", "web"))
    return {"key": "enrichment", "title": "Public profile and web mentions", "status": "info", "summary": "; ".join(parts) or "Looked up.",
            "linkedin": li, "web": web, "requests": requests, "updated_at": record.get("updated_at")}


def cost_step(person: dict, cost: dict, trace: dict, record: dict | None) -> dict:
    mine = next((p for p in cost.get("per_person") or [] if p.get("person_id") == person.get("person_id")), None)
    totals = cost.get("totals") or {}
    people = len(cost.get("per_person") or []) or None
    seconds = (trace.get("total_ms") or (totals.get("wall_s") or 0) * 1000) / 1000 if (trace.get("total_ms") or totals.get("wall_s")) else None
    each = round(seconds / people, 2) if seconds is not None and people else None
    requests = sum((record or {}).get(k, {}).get("requests") or 0 for k in ("linkedin", "web")) if record else 0
    if not mine and each is None:
        return {"key": "cost", "title": "What this person cost", "status": "none", "summary": "No cost record for this run."}
    return {"key": "cost", "title": "What this person cost", "status": "info",
            "summary": (f"${mine['fresh_usd']:.4f} if read fresh, ${mine['cost_usd']:.4f} charged in the last run" if mine else "Time only")
                       + (f" · about {each:g} s of the run" if each is not None else ""),
            "cost_usd": mine.get("cost_usd") if mine else None, "fresh_usd": mine.get("fresh_usd") if mine else None,
            "calls": mine.get("calls") if mine else None, "seconds": each,
            "run": {"run_id": cost.get("run_id"), "people": people, "seconds": round(seconds, 2) if seconds is not None else None,
                    "cost_usd": totals.get("cost_usd"), "fresh_usd": totals.get("fresh_usd"), "calls": totals.get("calls"),
                    "cached_calls": totals.get("cached_calls"), "cached_share": totals.get("cached_share")},
            "enrichment_requests": requests}


# ---------- route ----------

def build(event: dict, person_id: str) -> dict:
    """The trail for one person of one processed event."""
    event_id = event["spec"].event_id
    person = views.people_by_id(event).get(person_id)
    if person is None:
        raise HTTPException(404, "No such person in this event")
    rm = rm_state.all_states()
    card = views.person_card(event, person_id, rm.get((event_id, person_id)), rm) or {}
    labels = views.doc_labels(event)
    locate, extract, people_doc = _read(event, "locate"), _read(event, "extract"), _read(event, "people")
    briefs_doc, cost, ranked = _read(event, "briefs"), _read(event, "cost"), _read(event, "ranked")
    trace = _trace(event_id)
    agents = _agents(trace)
    entry, group = {}, card.get("list") or "callable"
    for g in ("callable", "entities", "context"):
        found = next((e for e in ranked.get(g) or [] if e.get("person_id") == person_id), None)
        if found:
            entry, group = found, g
            break
    record = enrichment.load(event_id, person_id)
    swaps = views.age_swaps(event, entry, person) if entry else {}
    steps = [documents_step(event, locate), pages_step(person, labels, locate, extract, agents),
             quotes_step(person, labels, agents, extract), checks_step(person, extract, labels),
             identity_step(person, people_doc, event_id), money_step(card), rank_step(entry, group, swaps),
             brief_step(views.briefs_by_id(event).get(person_id) or {}, briefs_doc, agents, person, swaps),
             enrichment_step(event_id, person_id), cost_step(person, cost, trace, record)]
    return {"event": views.event_ref(event), "person": {"id": person_id, "name": person.get("name_as_printed")},
            "run_id": cost.get("run_id") or trace.get("run_id"), "steps": steps,
            "generated_from": [k for k, v in {"locate": locate, "extract": extract, "people": people_doc, "ranked": ranked,
                                              "briefs": briefs_doc, "cost": cost, "trace": trace}.items() if v]}


@router.get("/api/people/{event_id}/{person_id}/trail", dependencies=[auth.VIEW])
def person_trail(event_id: str, person_id: str) -> dict:
    """How we found them: documents to cost, for one person."""
    event = store.find_event(event_id)
    if event is None:
        raise HTTPException(404, "No such event")
    if not event["processed"]:
        raise HTTPException(404, "This event has no people yet")
    return build(event, person_id)
