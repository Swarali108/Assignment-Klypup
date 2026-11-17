"""Read events/, outputs/ and the document caches. Files are re-read when they change (mtime cache).

Nothing here computes an amount; it only finds and loads what the pipeline stored.
Paths can be moved with FINSIGHT_ROOT (tests and other checkouts).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

from agents.spec import EventSpec
from config.event_types import EVENT_TYPES as _PIPELINE_TYPES

ROOT = Path(os.environ.get("FINSIGHT_ROOT") or Path(__file__).resolve().parents[1])
EVENTS_DIR = ROOT / "events"
OUTPUTS_DIR = ROOT / "outputs"
FETCH_DIR = ROOT / "cache" / "fetch"
PAGES_DIR = ROOT / "cache" / "pages"
OUTPUT_FILES = ("extract", "people", "ranked", "briefs", "cost", "timeline", "check")
# Every type the pipeline has a config for (config/event_types.py), so a new type shows up without an edit here.
SUPPORTED_TYPES = tuple(_PIPELINE_TYPES)
# A page with fewer characters than this has no usable text layer.
LOW_TEXT_CHARS = 50
# A document is "scanned" when at least this share of its pages has no usable text.
SCANNED_SHARE = 0.8

_CACHE: dict[str, tuple[float, object]] = {}


def _production() -> bool:
    """APP_ENV=production (the same rule as api/auth.is_production, kept here so the store imports nothing from the API)."""
    return (os.environ.get("APP_ENV") or "").strip().lower() in ("production", "prod")


def read_json(path: Path) -> object | None:
    """Parsed JSON, re-read only when the file's mtime changes; None when missing or unreadable."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = str(path)
    hit = _CACHE.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    _CACHE[key] = (mtime, data)
    return data


def url_sha(url: str) -> str:
    """The fetch-cache key of a document link (sha256 of the URL)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def pdf_path(doc_sha: str) -> Path | None:
    """The cached PDF for a fetch key, or None."""
    if len(doc_sha) != 64 or any(ch not in "0123456789abcdef" for ch in doc_sha):
        return None
    path = FETCH_DIR / f"{doc_sha}.bin"
    if not path.is_file():
        return None
    # Only documents that are PDFs are ever served: by stored content type, or by the PDF signature.
    if "pdf" not in str(doc_meta(doc_sha).get("content_type") or "").lower():
        with path.open("rb") as handle:
            if not handle.read(5).startswith(b"%PDF"):
                return None
    return path


def doc_meta(doc_sha: str) -> dict:
    """The fetch sidecar (url, fetched_at, content sha256), or {}."""
    return read_json(FETCH_DIR / f"{doc_sha}.json") or {}


def doc_pages(doc_sha: str) -> list[dict] | None:
    """Parsed page text for a cached document ([{pdf_index, printed_page, text}]), or None."""
    content = doc_meta(doc_sha).get("sha256")
    if not content:
        return None
    for path in sorted(PAGES_DIR.glob(f"{content}.v*.json"), reverse=True):
        pages = read_json(path)
        if isinstance(pages, list):
            return pages
    return None


def load_event_files() -> list[dict]:
    """Hand-made events/*.json then events/auto/*.json: {spec, raw, path, auto}. Invalid files are skipped."""
    found, ids = [], set()
    for path in sorted(EVENTS_DIR.glob("*.json")) + sorted((EVENTS_DIR / "auto").glob("*.json")):
        raw = read_json(path)
        if not isinstance(raw, dict):
            continue
        try:
            spec = EventSpec.model_validate({k: v for k, v in raw.items() if k in EventSpec.model_fields})
        except ValueError:
            continue
        if spec.event_id in ids or path.stem.startswith("example"):
            continue
        if _production() and any(not doc.url.lower().startswith(("http://", "https://")) for doc in spec.documents):
            continue  # production lists only events whose documents are real web links (no sample or local files)
        ids.add(spec.event_id)
        found.append({"spec": spec, "raw": raw, "path": path, "auto": path.parent.name == "auto"})
    return found


def load_outputs(event_id: str) -> dict:
    """Every output file of one event; None for a file not written yet."""
    return {name: read_json(OUTPUTS_DIR / event_id / f"{name}.json") for name in OUTPUT_FILES}


def load_events() -> list[dict]:
    """Every event with its outputs: {spec, raw, path, auto, out, processed}."""
    events = []
    for event in load_event_files():
        out = load_outputs(event["spec"].event_id)
        from api import overrides  # lazy: overrides reads this module

        out = overrides.apply(event["spec"].event_id, out)
        events.append({**event, "out": out, "processed": out["people"] is not None and out["ranked"] is not None})
    return events


def find_event(event_id: str) -> dict | None:
    """One event by id, or None."""
    for event in load_events():
        if event["spec"].event_id == event_id:
            return event
    return None


def discovery() -> dict | None:
    """outputs/discovery.json, or None."""
    return read_json(OUTPUTS_DIR / "discovery.json")


def discovery_log() -> list[dict]:
    """outputs/discovery_log.json entries, oldest first."""
    return (read_json(OUTPUTS_DIR / "discovery_log.json") or {}).get("entries") or []


def runs() -> list[dict]:
    """outputs/runs.csv rows, oldest first."""
    path = OUTPUTS_DIR / "runs.csv"
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def scanned_state(doc_sha: str, check_doc: dict | None = None) -> dict:
    """{scanned, pages, low_text_pages, cached} from the parsed-page cache, else from check.json."""
    pages = doc_pages(doc_sha)
    if pages:
        low = [page.get("pdf_index") for page in pages if len((page.get("text") or "").strip()) < LOW_TEXT_CHARS]
        return {"scanned": len(low) >= SCANNED_SHARE * len(pages), "pages": len(pages), "low_text_pages": len(low),
                "cached": True}
    if check_doc and check_doc.get("pages"):
        low = check_doc.get("low_text_pages") or []
        return {"scanned": len(low) >= SCANNED_SHARE * check_doc["pages"], "pages": check_doc["pages"],
                "low_text_pages": len(low), "cached": pdf_path(doc_sha) is not None}
    return {"scanned": False, "pages": None, "low_text_pages": None, "cached": pdf_path(doc_sha) is not None}
