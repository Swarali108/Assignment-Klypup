"""Run one pipeline step, or all of them, for one event file.

    python run.py --event events/<id>.json --step locate|extract|people|rank|brief|report
    python run.py --event events/<id>.json --step all
    python run.py --event events/<id>.json --step check    (documents only, no model call)

--step all runs locate -> extract -> people -> rank -> brief -> report inside one
run scope and prints a timeline. A structured event (block_deal, insider_sale: exchange
records, no document) runs people -> rank -> brief -> report only; locate, extract and
check do not apply to it. Lines starting "STEP " are flushed as they
happen, so the web app can show progress. A step whose input file is missing
runs the step before it first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.brief import BRIEF_PROMPT_VERSION, ask_model, write_briefs
from agents.extract import extract_event, report_sections
from agents.locate import locate
from agents.people import build_people
from agents.rank import rank_people
from agents.report import build_report
from agents import rules_structured
from agents.spec import load_event_spec
from config import budget
from config.event_types import event_config
from tools.costs import run_rows, write_cost_json
from tools.fetch import FetchError, fetch
from tools.pdf import pdf_to_pages
from tools.doc_check import check_event, format_check
from tools.people_index import link_event
from tools import llm as _llm
from tools.llm import LLMError
from tools import trace
from tools.runlog import current_run_id, run_scope, snapshot_ranked

ROOT = Path(__file__).resolve().parent
STEPS = ("locate", "extract", "people", "rank", "brief", "report")
# Documents fetched and parsed once per --step all run (locate and extract both need them).
_LOADED: dict[str, tuple[list[dict], list[dict]]] = {}
# A structured event has no document to fetch, locate or extract.
STRUCTURED_STEPS = ("people", "rank", "brief", "report")
DOCUMENT_ONLY_STEPS = ("locate", "extract", "check")


def main(argv: list[str] | None = None) -> int:
    """Run one step, or --step all, for one event file."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Run a pipeline step for one event file.")
    parser.add_argument("--event", required=True, help="Path to events/<event_id>.json")
    parser.add_argument("--step", required=True, choices=list(STEPS) + ["all", "check"])
    parser.add_argument("--person", help="With --step brief: write the brief of this person_id only, keeping the others.")
    args = parser.parse_args(argv)
    spec = load_event_spec(Path(args.event))
    if _structured(spec) and args.step in DOCUMENT_ONLY_STEPS:
        print(f"--step {args.step} does not apply to a {spec.event_type} event: it is built from exchange records, "
              "not documents. Use --step people|rank|brief|report|all.")
        return 0
    if args.step == "locate":
        _run_locate(spec)
        return 0
    if args.step == "check":
        _run_check(spec)
        return 0
    run_id = _resolve_run_id(spec.event_id)
    with run_scope(run_id, spec.event_id):
        if args.step == "all":
            _run_all(spec)
        elif args.step == "brief" and args.person:
            _run_brief(spec, only_person=args.person)
        else:
            _step_functions()[args.step](spec)
    snapshot_ranked(run_id, ROOT / "outputs" / spec.event_id)
    return 0


def _step_functions() -> dict:
    """Step name -> function(spec)."""
    return {
        "locate": _run_locate,
        "extract": _run_extract,
        "people": _run_people,
        "rank": _run_rank,
        "brief": _run_brief,
        "report": _run_report,
    }


def _structured(spec) -> bool:
    """True for an event built from exchange records (config "structured")."""
    return bool(event_config(spec.event_type).get("structured"))


def _run_all(spec) -> list[dict]:
    """Every step in order, with a timeline row per step: seconds, model calls, cost."""
    started = time.perf_counter()
    timeline: list[dict] = []
    functions = _step_functions()
    _LOADED.clear()
    try:
        with trace.tracing(current_run_id(), spec.event_id) as tracer:
            for name in STRUCTURED_STEPS if _structured(spec) else STEPS:
                before = len(run_rows(current_run_id()))
                print(f"STEP {name} start", flush=True)
                step_started = time.perf_counter()
                with trace.step(name, why=_step_why(name, spec)):
                    if name == "report":
                        _run_report(spec, wall_s=time.perf_counter() - started)
                    else:
                        functions[name](spec)
                row = _timeline_row(name, step_started, run_rows(current_run_id())[before:])
                timeline.append(row)
                print(
                    f"STEP {name} done {row['seconds']:.1f}s calls={row['calls']} cached={row['cached']} "
                    f"cost=${row['cost_usd']:.6f}",
                    flush=True,
                )
            total_s = time.perf_counter() - started
            _print_timeline(timeline, total_s)
            _write_json(spec.event_id, "timeline.json", {"run_id": current_run_id(), "total_s": total_s, "steps": timeline})
            print(f"wrote {trace.write_trace(tracer, ROOT / 'outputs' / spec.event_id)}", flush=True)
    finally:
        _LOADED.clear()
    return timeline


def _step_why(name: str, spec) -> str:
    """What decided that this step runs, in plain words (for the agent trace)."""
    return {
        "locate": f"the event has {len(spec.documents)} document{'s' if len(spec.documents) != 1 else ''}",
        "extract": f"the {spec.event_type.upper()} rules name the tables to read",
        "people": "rows that passed verify name people and holdings",
        "rank": "every person needs a place in the call list",
        "brief": "each person to call gets a short checked brief",
        "report": "the call list and cost file are written last",
    }.get(name, "")


def _timeline_row(name: str, started: float, rows: list[dict]) -> dict:
    """One step's seconds, model calls, cached calls and cost."""
    cost = sum(float(row.get("cost_usd") or 0) for row in rows)
    cached = sum(1 for row in rows if (row.get("cached") or "").lower() == "true")
    seconds = time.perf_counter() - started
    return {"step": name, "seconds": seconds, "calls": len(rows), "cached": cached, "cost_usd": cost}


def _print_timeline(timeline: list[dict], total_s: float) -> None:
    """The step table, then the totals."""
    print(f"{'step':<10} {'seconds':>8} {'calls':>6} {'cached':>7} {'cost_usd':>10}")
    for row in timeline:
        print(
            f"{row['step']:<10} {row['seconds']:>8.1f} {row['calls']:>6} {row['cached']:>7} "
            f"{row['cost_usd']:>10.6f}"
        )
    calls = sum(row["calls"] for row in timeline)
    cached = sum(row["cached"] for row in timeline)
    cost = sum(row["cost_usd"] for row in timeline)
    print(f"{'total':<10} {total_s:>8.1f} {calls:>6} {cached:>7} {cost:>10.6f}")


def _run_check(spec) -> dict:
    """Fetch and read each document, then report what the pipeline would find. No model call."""
    started = time.perf_counter()
    documents, pages = load_document_pages(spec)
    report = check_event(spec, documents, pages)
    report["seconds"] = round(time.perf_counter() - started, 1)
    print(format_check(report))
    print(f"took {report['seconds']} s; wrote {_write_json(spec.event_id, 'check.json', report)}")
    return report


def _run_locate(spec) -> dict:
    """Rank pages per section and write locate.json."""
    result = locate_event(spec)
    _print_table(result["sections"])
    out = _write_json(spec.event_id, "locate.json", result)
    print(f"wrote {out}")
    return result


def _run_people(spec) -> dict:
    """Build people.json from extract.json, or from the exchange records for a structured event."""
    if _structured(spec):
        records, meta = rules_structured.load_records(ROOT / spec.records_file, spec.records or [])
        meta["records_file"] = spec.records_file
        n_rows = len(records)
        with trace.agent("structured_people", label="Build people from exchange records",
                         why="a deal or insider sale is read straight from the exchange's own row",
                         given=f"{n_rows} records", doing="adding up each seller's rows; no document, no model call") as rec:
            result = rules_structured.build_people(spec, records, meta)
            rec["returns"] = {"people": result["counts"].get("people", 0), "sellers": result["counts"].get("sellers", 0)}
    else:
        extracted = _load_or_run(spec, "extract.json", _run_extract)
        n_rows = len(extracted.get("rows") or [])
        with trace.agent("match_people", label="Match people and families",
                         why=f"{n_rows} verified rows may name the same person twice",
                         given=f"{n_rows} rows", doing=f"comparing {n_rows * (n_rows - 1) // 2} name pairs; unsure pairs go to "
                         f"{_llm.LLM_MODEL_STRONG or 'the strong model'}") as rec:
            result = build_people(extracted, spec, ask=None if budget.strong_model_for_names() else _no_strong_model)
            counts = result["counts"]
            rec["returns"] = {"people": counts.get("people", 0), "merges": counts.get("identity_merges", 0),
                              "model_asks": counts.get("llm_asks", 0), "families": counts.get("family_groups", 0),
                              "sellers": counts.get("sellers", 0)}
    with trace.agent("link_index", label="Look up other events", why="a person may already be in another event's list",
                     given=f"{len(result['people'])} people", doing="checking the cross-event people index") as rec:
        link_event(result, spec, ROOT / "outputs" / "index.json")
        rec["returns"] = {"matches": result["counts"].get("follow_on_matches", 0)}
    out = _write_json(spec.event_id, "people.json", result)
    print(json.dumps(result["counts"], indent=2, ensure_ascii=False))
    print(f"wrote {out}")
    return result


def _no_strong_model(left: dict, right: dict, event_id: str) -> dict:
    """BUDGET_MODE=lean: an unsure name pair stays two people instead of asking the strong model."""
    return {"outcome": "unsure", "reason": "BUDGET_MODE=lean: strong model not asked", "method": "budget_lean"}


def _run_spend() -> float:
    """Dollars this run has spent so far (cost_log rows of the current run)."""
    return sum(float(row.get("cost_usd") or 0) for row in run_rows(current_run_id()))


def _run_rank(spec) -> dict:
    """Rank people.json into ranked.json."""
    people_doc = _load_or_run(spec, "people.json", _run_people)
    with trace.agent("rank", label="Rank who to call", why="money in hand ranks above money later, then by size and confidence",
                     given=f"{len(people_doc['people'])} people", doing=f"ranking {len(people_doc['people'])} people") as rec:
        ranked = {"event_id": spec.event_id, **rank_people(people_doc["people"], spec.event_type)}
        rec["returns"] = {"callable": len(ranked["callable"]), "entities": len(ranked["entities"])}
    out = _write_json(spec.event_id, "ranked.json", ranked)
    print(f"ranked {len(ranked['callable'])} callable, {len(ranked['entities'])} entities; wrote {out}")
    return ranked


def _run_brief(spec, only_person: str | None = None) -> dict:
    """One checked brief per callable person, written to briefs.json (only_person: rewrite that person's brief, keep the rest)."""
    people_doc = _load_or_run(spec, "people.json", _run_people)
    ranked = _load_or_run(spec, "ranked.json", _run_rank)
    if only_person:
        return _run_one_brief(spec, only_person, people_doc, ranked)
    total = len(ranked["callable"])
    seen: list[str] = []

    def call(fields, person_id, event_id, **retry):
        """ask_model, with a live "brief k of n" line; config/budget.py may send a person to the template."""
        if person_id not in seen:
            seen.append(person_id)
        refused = budget.model_brief_allowed(seen.index(person_id), _run_spend())
        if refused:
            raise LLMError(refused)  # brief_for catches it and writes the code template
        trace.progress("brief", f"writing brief {len(seen)} of {total}" + (" (retry after a failed check)" if retry else ""),
                       done=len(seen) - 1, total=total)
        return ask_model(fields, person_id, event_id, **retry)

    with trace.agent("brief", label="Write call briefs", why=f"{total} people to call",
                     given=f"{total} people, each with checked figures", runs_on=_llm.LLM_MODEL,
                     doing=f"writing {total} briefs; every number is checked against the figures") as rec:
        briefs = write_briefs(ranked, people_doc["people"], spec.event_id, call=call)
        sources = [brief["brief_source"] for brief in briefs]
        rec["returns"] = {"briefs": len(briefs), "model": sources.count("llm"), "template": sources.count("template")}
    result = {"event_id": spec.event_id, "prompt_version": BRIEF_PROMPT_VERSION, "briefs": briefs}
    out = _write_json(spec.event_id, "briefs.json", result)
    sources = [brief["brief_source"] for brief in briefs]
    print(f"briefs: {sources.count('llm')} llm, {sources.count('template')} template; wrote {out}")
    return result


def _run_one_brief(spec, person_id: str, people_doc: dict, ranked: dict) -> dict:
    """Write one person's brief into briefs.json at their place in the rank order; the other briefs stay as they were."""
    entries = [entry for entry in ranked["callable"] if entry["person_id"] == person_id]
    if not entries:
        raise SystemExit(f"error: {person_id} is not on the call list of {spec.event_id}")
    with trace.agent("brief", label="Write call briefs", why="one brief was asked for again", given="1 person, with checked figures",
                     runs_on=_llm.LLM_MODEL, doing="writing 1 brief; every number is checked against the figures") as rec:
        new = write_briefs({"callable": entries}, people_doc["people"], spec.event_id,
                           call=lambda fields, pid, eid, **retry: ask_model(fields, pid, eid, **retry))[0]
        rec["returns"] = {"briefs": 1, "model": int(new["brief_source"] == "llm"), "template": int(new["brief_source"] == "template")}
    path = ROOT / "outputs" / spec.event_id / "briefs.json"
    existing = _read_json(path) if path.is_file() else {"event_id": spec.event_id, "prompt_version": BRIEF_PROMPT_VERSION, "briefs": []}
    by_id = {brief["person_id"]: brief for brief in existing["briefs"]}
    by_id[person_id] = new
    order = [entry["person_id"] for entry in ranked["callable"]]
    existing["briefs"] = [by_id[pid] for pid in order if pid in by_id]
    existing["prompt_version"] = BRIEF_PROMPT_VERSION
    out = _write_json(spec.event_id, "briefs.json", existing)
    print(f"brief for {person_id}: {new['brief_source']}; wrote {out}")
    return existing


def _run_report(spec, wall_s: float | None = None) -> Path:
    """Write cost.json, then report.md from the outputs on disk."""
    folder = ROOT / "outputs" / spec.event_id
    briefs = _load_or_run(spec, "briefs.json", _run_brief)
    with trace.agent("report", label="Assemble the call list", why="the last step: the call list and its cost",
                     given="the checked rows, people, ranking and briefs", doing="writing report.md and cost.json") as rec:
        rec["returns"] = {"people_in_report": len(briefs["briefs"])}
        return _write_report(spec, folder, briefs, wall_s)


def _write_report(spec, folder: Path, briefs: dict, wall_s: float | None) -> Path:
    """Write cost.json, then report.md."""
    cost_path = write_cost_json(spec.event_id, folder, wall_s=wall_s)
    report = build_report(
        spec,
        {} if _structured(spec) else _read_json(folder / "extract.json"),
        _read_json(folder / "people.json"),
        _read_json(folder / "ranked.json"),
        briefs["briefs"],
        _read_json(cost_path),
    )
    out = folder / "report.md"
    out.write_text(report, encoding="utf-8")
    print(f"wrote {cost_path}")
    print(f"wrote {out}")
    return out


def _load_or_run(spec, name: str, step) -> dict:
    """Read outputs/<event_id>/<name>, or run the step that writes it."""
    path = ROOT / "outputs" / spec.event_id / name
    if path.is_file():
        return _read_json(path)
    return step(spec)


def _read_json(path: Path) -> dict:
    """Read one JSON output file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def locate_event(spec) -> dict:
    """Fetch each document, parse PDFs, and keep the top five pages per section.

    A failed download or a non-PDF is recorded and the other documents continue.
    locate() itself does not see the URL. source_url is added here.
    """
    documents, pages = load_document_pages(spec)
    config = event_config(spec.event_type)
    whole_types = config["whole_document"]["doc_types"]
    sections = {name: [] for name in config["locate_sections"]}
    by_url: dict[str, list[dict]] = {}
    for page in pages:
        by_url.setdefault(page.get("source_url") or "", []).append(page)
    for document in documents:
        # A document read whole (an announcement, an OFS notice) is not ranked here.
        if "page_count" not in document or document["doc_type"] in whole_types:
            continue
        url = document["url"]
        mine = by_url.get(url, [])
        with trace.agent(f"locate_{document['doc_type']}", label=f"Find pages: {trace.doc_words(document['doc_type'])}",
                         why=f"the {spec.event_type.upper()} rules list {len(config['locate_sections'])} sections to find",
                         given=f"{len(mine)} pages", doing=f"scoring {len(mine)} pages for {len(config['locate_sections'])} sections") as rec:
            found = locate(mine, spec.event_type)
            rec["returns"] = {"sections_found": sum(1 for hits in found.values() if hits),
                              "sections": len(config["locate_sections"]), "candidate_pages": sum(len(h) for h in found.values())}
        for name, hits in found.items():
            for hit in hits:
                sections[name].append({**hit, "source_url": url})
    for name, hits in sections.items():
        hits.sort(key=lambda item: (-item["score"], item["pdf_index"] or 0, item.get("source_url") or ""))
        sections[name] = hits[:5]
    return {
        "event_id": spec.event_id,
        "event_type": spec.event_type,
        "documents": documents,
        "sections": sections,
    }


def load_document_pages(spec) -> tuple[list[dict], list[dict]]:
    """Fetch each document and parse its PDF. Failures are recorded and skipped.

    Each page dict gains source_url so a later step can tell two filings apart. Inside one
    --step all run the result is kept, so locate and extract fetch and parse once.
    """
    if spec.event_id in _LOADED and trace.active() is not None:
        documents, pages = _LOADED[spec.event_id]
        return [dict(d) for d in documents], list(pages)
    documents: list[dict] = []
    pages: list[dict] = []
    for document in spec.documents:
        try:
            path, meta = _traced_fetch(document)
        except FetchError as exc:
            documents.append({"url": document.url, "doc_type": document.doc_type, "error": str(exc)})
            continue
        if not _is_pdf(path, meta):
            documents.append(
                {
                    "url": document.url,
                    "doc_type": document.doc_type,
                    "path": _repo_path(path),
                    "skipped": "not a pdf",
                }
            )
            continue
        try:
            parsed = _traced_parse(document, path)
        except Exception as exc:
            documents.append(
                {
                    "url": document.url,
                    "doc_type": document.doc_type,
                    "path": _repo_path(path),
                    "error": f"PDF parse failed: {exc}",
                }
            )
            continue
        for page in parsed:
            pages.append({**page, "source_url": document.url})
        documents.append(
            {
                "url": document.url,
                "doc_type": document.doc_type,
                "path": _repo_path(path),
                "page_count": len(parsed),
            }
        )
    if trace.active() is not None:
        _LOADED[spec.event_id] = (documents, pages)
    return documents, pages


def _traced_fetch(document) -> tuple[Path, dict]:
    """fetch() inside a trace span: bytes and whether the copy on disk was reused."""
    host = document.url.split("/")[2] if "//" in document.url else document.url
    words = trace.doc_words(document.doc_type)
    with trace.agent(f"fetch_{document.doc_type}", label=f"Download: {words}",
                     why="one of the event's documents", given=host, doing=f"downloading the {words} from {host}") as rec:
        asked = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path, meta = fetch(document.url)
        rec["returns"] = {"bytes": path.stat().st_size, "reused_copy": (meta.get("fetched_at") or "") < asked}
    return path, meta


def _traced_parse(document, path: Path) -> list[dict]:
    """pdf_to_pages() inside a trace span."""
    words = trace.doc_words(document.doc_type)
    with trace.agent(f"read_pdf_{document.doc_type}", label=f"Read PDF: {words}",
                     why="the download is a PDF", given=f"{path.stat().st_size // 1024:,} KB",
                     doing=f"turning the {words} into page text") as rec:
        parsed = pdf_to_pages(path)
        rec["returns"] = {"pages": len(parsed), "printed_page_numbers": sum(1 for p in parsed if p.get("printed_page"))}
    return parsed


def _run_extract(spec) -> dict:
    """Locate if needed, then extract, verify, and write extract.json."""
    locate_path = ROOT / "outputs" / spec.event_id / "locate.json"
    located = json.loads(locate_path.read_text(encoding="utf-8")) if locate_path.is_file() else None
    if located is None or not _same_documents(located, spec):
        located = locate_event(spec)
        _write_json(spec.event_id, "locate.json", located)
    _documents, pages = load_document_pages(spec)
    whole_types = event_config(spec.event_type)["whole_document"]["doc_types"]
    whole_urls = [doc.url for doc in spec.documents if doc.doc_type in whole_types]
    result = extract_event(spec.event_id, located, pages, whole_urls, spec.event_type)
    out = _write_json(spec.event_id, "extract.json", result)
    _print_counts(result["counts"], len(result["rejections"]), report_sections(spec.event_type))
    print(f"wrote {out}")
    return result


def _same_documents(located: dict, spec) -> bool:
    """True when locate.json was built from exactly the documents the event file lists now."""
    built = {document.get("url") for document in located.get("documents") or []}
    return built == {document.url for document in spec.documents}


def _resolve_run_id(event_id: str) -> str:
    """Use RUN_ID when it is set. Otherwise build an id from the event and the time."""
    chosen = os.environ.get("RUN_ID", "").strip()
    if chosen:
        return chosen
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{event_id}-{stamp}"


def _repo_path(path: Path) -> str:
    """A document's path from the repo root, so outputs never carry this machine's folder names."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).name


def _write_json(event_id: str, name: str, payload: dict) -> Path:
    """Write outputs/<event_id>/<name> and return the path."""
    out = ROOT / "outputs" / event_id / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _print_counts(counts: dict, rejections: int, sections: tuple[str, ...]) -> None:
    """Print fields proposed, kept and rejected, rows unattributed, and citations corrected."""
    print(f"{'section':<24} {'proposed':<10} {'kept':<8} {'rejected':<10} {'unattrib':<10} corrected")
    for section in sections:
        row = counts.get(section) or {}
        print(
            f"{section:<24} {row.get('proposed', 0):<10} {row.get('kept', 0):<8} "
            f"{row.get('rejected', 0):<10} {row.get('unattributed', 0):<10} "
            f"{row.get('citations_corrected', 0)}"
        )
    print(f"rejections {rejections}")


def _is_pdf(path: Path, meta: dict) -> bool:
    """True when the content type or the file magic says this is a PDF."""
    content_type = (meta.get("content_type") or "").lower()
    if "pdf" in content_type:
        return True
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def _print_table(sections: dict) -> None:
    """Print section, document, printed page, pdf index, score, and the strongest terms."""
    print(f"{'section':<24} {'doc':<10} {'printed_page':<14} {'pdf_index':<10} {'score':<8} terms")
    for section, hits in sections.items():
        if not hits:
            print(f"{section:<24} {'-':<10} {'-':<14} {'-':<10} {'0':<8}")
            continue
        for hit in hits:
            printed = hit["printed_page"] if hit["printed_page"] else "-"
            terms = ", ".join(hit["matched_terms"][:3])
            doc = _doc_id(hit.get("source_url") or "")
            print(
                f"{section:<24} {doc:<10} {str(printed):<14} "
                f"{str(hit['pdf_index']):<10} {hit['score']:<8} {terms}"
            )


def _doc_id(url: str) -> str:
    """First 8 hex characters of sha256(url), so two filings are not confused."""
    if not url:
        return "-"
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


if __name__ == "__main__":
    raise SystemExit(main())
