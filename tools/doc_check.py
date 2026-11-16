"""Pre-flight check for an event's documents. Code only: no model call, nothing logged as a run.

    python run.py --event events/<id>.json --step check

For each document: was it fetched, is it a PDF, how many pages, which pages have
almost no text (possibly scanned), and either which locate sections found a page
(ranked documents) or how many pages would be read whole (announcements, notices).
For an IPO it also says whether each lock-in rule's wording is in the pages.
"""

from __future__ import annotations

from agents.locate import locate
from agents.rule_sources import find_rule_sources
from config.event_types import event_config

# A page with fewer characters than this is probably a scan with no text layer.
LOW_TEXT_CHARS = 50


def check_event(spec, documents: list[dict], pages: list[dict]) -> dict:
    """The check result for every document, plus the lock-in wording for an IPO."""
    config = event_config(spec.event_type)
    whole = config["whole_document"]
    report = {"event_id": spec.event_id, "event_type": spec.event_type, "documents": []}
    lock_in_hits: list[dict] = []
    for document in documents:
        mine = [page for page in pages if page.get("source_url") == document["url"]]
        entry = _document_entry(document, mine)
        if mine and document["doc_type"] in whole["doc_types"]:
            entry["read_whole"] = f"{min(len(mine), whole['max_pages'])} of {len(mine)} pages sent to {', '.join(whole['sections'])}"
        elif mine:
            found = locate(mine, spec.event_type)
            entry["sections_found"] = {section: _page(hits[0]) for section, hits in found.items() if hits}
            entry["sections_missing"] = [section for section, hits in found.items() if not hits]
            lock_in_hits += [{**hit, "source_url": document["url"]} for hit in found.get("lock_in", [])]
        report["documents"].append(entry)
    if config.get("rule_sources"):
        report["lock_in_wording"] = _rule_summary(find_rule_sources(pages, lock_in_hits))
    return report


def format_check(report: dict) -> str:
    """The check as plain lines for the terminal."""
    lines = [f"check {report['event_id']} ({report['event_type']})"]
    for entry in report["documents"]:
        lines.append(f"- {entry['doc_type']}: {entry['url']}")
        lines.append(f"  fetched: {entry['fetched']}")
        if entry.get("pages") is None:
            continue
        low = entry["low_text_pages"]
        lines.append(f"  pages: {entry['pages']}; almost no text: {len(low)}" + (f" (pdf {', '.join(map(str, low[:15]))})" if low else ""))
        if "read_whole" in entry:
            lines.append(f"  read whole: {entry['read_whole']}")
        if "sections_found" in entry:
            found = ", ".join(f"{name} {page}" for name, page in entry["sections_found"].items()) or "none"
            lines.append(f"  sections with a page: {found}")
            if entry["sections_missing"]:
                lines.append(f"  sections with no page: {', '.join(entry['sections_missing'])}")
    for rule, found in (report.get("lock_in_wording") or {}).items():
        lines.append(f"- lock-in wording {rule}: {found}")
    return "\n".join(lines)


def _document_entry(document: dict, pages: list[dict]) -> dict:
    """Fetch status, page count and low-text pages for one document."""
    entry = {"url": document["url"], "doc_type": document["doc_type"]}
    if document.get("error"):
        return {**entry, "fetched": f"no: {document['error']}", "pages": None}
    if document.get("skipped"):
        return {**entry, "fetched": f"yes, but {document['skipped']}", "pages": None}
    low = [page["pdf_index"] for page in pages if len((page.get("text") or "").strip()) < LOW_TEXT_CHARS]
    return {**entry, "fetched": "yes", "pages": len(pages), "low_text_pages": low}


def _page(hit: dict) -> str:
    """"p. 128" when the printed page is known, else "pdf 1"."""
    return f"p. {hit['printed_page']}" if hit.get("printed_page") else f"pdf {hit.get('pdf_index')}"


def _rule_summary(sources: dict) -> dict:
    """rule -> "found on p. N" or "not found", per lock-in period and for proceeds at listing."""
    summary = {}
    for rule, found in sources.items():
        items = found["periods"].items() if "periods" in found else [("", found)]
        for label, source in items:
            name = f"{rule}: {label}" if label else rule
            page = source.get("printed_page") or f"pdf {source.get('pdf_index')}"
            summary[name] = f"found on p. {page}" if source.get("found") else "not found"
    return summary
