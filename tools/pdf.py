"""Turn a PDF into one text block per page, with the printed page number when it is visible.

Citations should use printed_page when it is not null, because that is the number
a reader sees. pdf_index is the 1-based page in the file and can differ.
A second call for the same bytes reads cache/pages/<sha256>.v<PARSER_VERSION>.json
and does not parse. Bump PARSER_VERSION when printed_page parsing changes so a
page cached under the old rules is parsed again.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("tools.pdf")
# Bump when printed_page parsing changes. Old page-cache files are then unused.
PARSER_VERSION = 1
# Files with at least this many pages are read by worker processes, at most max_workers().
PARALLEL_MIN_PAGES = 40
# Used when the MAX_WORKERS environment variable is unset. A small host can set it to 2.
DEFAULT_MAX_WORKERS = 8
# How many pages on each side vote on the printed-page offset.
NEIGHBOUR_RADIUS = 5
# A line that is only a page number or a roman numeral, optionally wrapped.
_STANDALONE_LABEL = re.compile(
    r"^[\s|\-–—\[\]\(\)]*([0-9]{1,4}|[ivxlcdmIVXLCDM]{1,12})[\s|\-–—\[\]\(\)]*$"
)
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_ROMAN_PAIRS = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)
_SHORT_TEXT = 50


def pdf_to_pages(path: Path | str) -> list[dict]:
    """Return [{pdf_index, printed_page, text}] for one PDF.

    printed_page is a string, or null when no standalone number is in the
    last three non-empty lines or the first two, or when a numeric label
    disagrees with the pages around it. Pages under 50 characters are logged
    as possibly scanned. They are not OCR'd.
    """
    pdf_path = Path(path)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cache_path = _page_cache_path(digest)
    started = time.perf_counter()
    if cache_path.is_file():
        pages = json.loads(cache_path.read_text(encoding="utf-8"))
        _log_pages(pages, time.perf_counter() - started, from_cache=True)
        return pages
    pages = _parse(pdf_path)
    _write_cache(cache_path, pages)
    _log_pages(pages, time.perf_counter() - started, from_cache=False)
    return pages


def printed_page_from_text(text: str) -> str | None:
    """Return a standalone page label from the footer, otherwise the header.

    The last three non-empty lines are checked from the bottom. If none is a
    bare number or roman numeral, the first two non-empty lines are checked.
    """
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(nonempty[-3:]):
        found = _standalone_label(line)
        if found is not None:
            return found
    for line in nonempty[:2]:
        found = _standalone_label(line)
        if found is not None:
            return found
    return None


def validate_printed_pages(pages: list[dict]) -> list[dict]:
    """Null a numeric printed_page whose offset disagrees with its neighbours.

    offset = int(printed_page) - pdf_index. A numeric label is kept only when
    that offset is a most common offset among the five pages on each side.
    Roman numerals and other non-numeric labels are left as found. pages are
    updated in place and also returned. The list is in file order.
    """
    for index, page in enumerate(pages):
        offset = _offset(page)
        if offset is None:
            continue
        modes = _modal_offsets(_neighbour_offsets(pages, index))
        if not modes or offset in modes:
            continue
        LOGGER.warning(
            "pdf_index %s printed_page %s offset %s is not the neighbour offset %s; set to null",
            page.get("pdf_index"),
            page.get("printed_page"),
            offset,
            sorted(modes),
        )
        page["printed_page"] = None
    return pages


def _parse(path: Path) -> list[dict]:
    """Extract text with pdfplumber. pdf_index starts at 1.

    Text is extracted page by page (in parallel for long files); printed pages are
    then read and checked across neighbours in one pass, so the result is the same
    either way.
    """
    pages = [
        {"pdf_index": index, "printed_page": printed_page_from_text(text), "text": text}
        for index, text in enumerate(_page_texts(path), start=1)
    ]
    return validate_printed_pages(pages)


def _page_texts(path: Path) -> list[str]:
    """Every page's text, in order. Files of PARALLEL_MIN_PAGES or more use worker processes."""
    with pdfplumber.open(path) as pdf:
        count = len(pdf.pages)
    if count < PARALLEL_MIN_PAGES:
        return extract_range(str(path), 0, count)
    workers = min(os.cpu_count() or 1, max_workers())
    size = max(1, -(-count // (workers * 2)))
    ranges = [(str(path), start, min(start + size, count)) for start in range(0, count, size)]
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            chunks = list(pool.map(_extract_chunk, ranges))
    except (BrokenProcessPool, OSError) as exc:
        LOGGER.warning("parallel parse failed (%s); parsing in one process", exc)
        return extract_range(str(path), 0, count)
    return [text for chunk in chunks for text in chunk]


def max_workers() -> int:
    """The MAX_WORKERS environment variable as a whole number of at least 1, else DEFAULT_MAX_WORKERS."""
    value = os.environ.get("MAX_WORKERS", "").strip()
    if not value:
        return DEFAULT_MAX_WORKERS
    if value.isdigit() and int(value) >= 1:
        return int(value)
    LOGGER.warning("MAX_WORKERS=%r is not a whole number of at least 1; using %d", value, DEFAULT_MAX_WORKERS)
    return DEFAULT_MAX_WORKERS


def extract_range(path: str, start: int, stop: int) -> list[str]:
    """The text of pages start..stop-1 (0-based), each "" when the page has no text layer."""
    with pdfplumber.open(path) as pdf:
        return [pdf.pages[index].extract_text() or "" for index in range(start, stop)]


def _extract_chunk(args: tuple[str, int, int]) -> list[str]:
    """extract_range for one worker process."""
    return extract_range(*args)


def _standalone_label(line: str) -> str | None:
    """Return a bare arabic number or a canonical roman numeral, as printed."""
    match = _STANDALONE_LABEL.fullmatch(line.strip())
    if match is None:
        return None
    token = match.group(1)
    if token.isdigit():
        return token
    # One letter (c, d, i, m) is too easy to confuse with a word. ii, iv, xii stay.
    if len(token) >= 2 and _is_roman(token):
        return token
    return None


def _is_roman(token: str) -> bool:
    """True when token is a canonical roman numeral, such as iv or XII."""
    lowered = token.lower()
    value = _roman_to_int(lowered)
    if value is None or value > 3999:
        return False
    return _int_to_roman(value) == lowered


def _roman_to_int(token: str) -> int | None:
    """Parse a roman numeral. Malformed tokens return None."""
    if not token:
        return None
    total = 0
    previous = 0
    for char in reversed(token):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    if total <= 0:
        return None
    return total


def _int_to_roman(number: int) -> str:
    """Write number as a lowercase roman numeral. number is from 1 to 3999."""
    parts: list[str] = []
    remaining = number
    for value, glyph in _ROMAN_PAIRS:
        while remaining >= value:
            parts.append(glyph)
            remaining -= value
    return "".join(parts)


def _offset(page: dict) -> int | None:
    """Return int(printed_page) - pdf_index, or None when the label is not numeric."""
    printed = page.get("printed_page")
    index = page.get("pdf_index")
    if printed is None or index is None:
        return None
    text = str(printed).strip()
    if not text.isdigit():
        return None
    return int(text) - int(index)


def _neighbour_offsets(pages: list[dict], index: int) -> list[int]:
    """Numeric offsets of up to five pages on each side. This page is excluded."""
    start = max(0, index - NEIGHBOUR_RADIUS)
    end = min(len(pages), index + NEIGHBOUR_RADIUS + 1)
    offsets: list[int] = []
    for other in range(start, end):
        if other == index:
            continue
        offset = _offset(pages[other])
        if offset is not None:
            offsets.append(offset)
    return offsets


def _modal_offsets(offsets: list[int]) -> set[int]:
    """Return every offset that ties for the highest count. Empty if there are none."""
    if not offsets:
        return set()
    counts: dict[int, int] = {}
    for offset in offsets:
        counts[offset] = counts.get(offset, 0) + 1
    best = max(counts.values())
    return {offset for offset, count in counts.items() if count == best}


def _log_pages(pages: list[dict], elapsed_s: float, from_cache: bool) -> None:
    """Log the page count, the parse time, and any page that looks unscanned-empty."""
    source = "cache" if from_cache else "parsed"
    LOGGER.info("%s %s pages in %.3fs", source, len(pages), elapsed_s)
    for page in pages:
        if len(page.get("text", "").strip()) < _SHORT_TEXT:
            LOGGER.warning(
                "pdf_index %s has %s characters of text; possibly scanned; not OCR'd",
                page.get("pdf_index"),
                len(page.get("text", "").strip()),
            )


def _page_cache_path(digest: str) -> Path:
    """Return the cache file for these bytes at the current parser version."""
    return _cache_dir() / f"{digest}.v{PARSER_VERSION}.json"


def _cache_dir() -> Path:
    """Return the page-text cache. Tests set PAGES_CACHE_DIR."""
    override = os.environ.get("PAGES_CACHE_DIR", "").strip()
    path = Path(override) if override else ROOT / "cache" / "pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_cache(path: Path, pages: list[dict]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
