"""Rank pages by section. No files, no network, no model calls."""

from __future__ import annotations

import re

from agents.spec import EVENT_TYPES
from config.event_types import event_config
from config.sections import (
    HEADING_BONUS,
    HEADING_LINES,
    SECTIONS,
    STRUCTURE,
    STRUCTURE_BONUS,
    TABLE_BONUS,
    TABLE_MIN_NUMBERS,
)

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PATTERNS: dict[str, re.Pattern[str]] = {}
# A defined term repeated down a page should not outrank one real table.
MAX_TERM_HITS = 3
_FOLDS = str.maketrans(
    {
        "\u2018": "'",  # ‘
        "\u2019": "'",  # ’
        "\u201c": '"',  # “
        "\u201d": '"',  # ”
        "\u2010": "-",  # ‐
        "\u2011": "-",  # ‑
        "\u2012": "-",  # ‒
        "\u2013": "-",  # –
        "\u2014": "-",  # —
    }
)


def locate(pages: list[dict], event_type: str) -> dict[str, list[dict]]:
    """Return the top five pages for each section this event type locates.

    Each hit is {pdf_index, printed_page, score, matched_terms}. A page that
    scores zero is left out. config/event_types.py lists the sections per type.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type {event_type!r}. Expected one of {EVENT_TYPES}.")
    ranked: dict[str, list[dict]] = {}
    for section in event_config(event_type)["locate_sections"]:
        terms = SECTIONS[section]
        hits: list[dict] = []
        structure = STRUCTURE.get(section, ())
        for page in pages:
            score, matched = score_page(page.get("text") or "", terms, structure)
            if score <= 0:
                continue
            hits.append(
                {
                    "pdf_index": page.get("pdf_index"),
                    "printed_page": page.get("printed_page"),
                    "score": score,
                    "matched_terms": matched,
                }
            )
        hits.sort(key=lambda item: (-item["score"], item["pdf_index"] or 0))
        ranked[section] = hits[:5]
    return ranked


def normalise(text: str) -> str:
    """Lowercase, straighten quotes and hyphens, and collapse whitespace.

    Newlines become spaces, so a phrase that wraps across lines still matches.
    Curly quotes become ' or ". The unicode hyphens ‐ ‑ ‒ – — become "-".
    """
    folded = text.translate(_FOLDS).lower()
    return re.sub(r"\s+", " ", folded).strip()


def score_page(
    text: str,
    terms: tuple[tuple[str, int], ...],
    structure: tuple[str, ...] = (),
) -> tuple[int, list[str]]:
    """Score one page against one section.

    Terms are counted on the normalised page, at most three times each.
    A shorter term inside a longer term's match is not counted. A surviving
    term in the first five non-empty lines adds HEADING_BONUS once. A surviving
    term on a line with three or more numbers adds TABLE_BONUS once. Each
    structure phrase found adds STRUCTURE_BONUS once. matched_terms is highest
    contribution first.
    """
    page = normalise(text)
    lines = _lines(text)
    weights = {term: weight for term, weight in terms}
    counts = _counts(_drop_contained(_spans(page, weights)))
    contributions: dict[str, int] = {}
    for term, hits in counts.items():
        score = weights[term] * min(hits, MAX_TERM_HITS)
        if weights[term] < 0:  # a counter-term: it lowers the page and earns no bonus
            contributions[term] = score
            continue
        if _line_has(lines[:HEADING_LINES], term):
            score += HEADING_BONUS
        if _table_line(lines, term):
            score += TABLE_BONUS
        contributions[term] = score
    for phrase in structure:
        if _pattern(phrase).search(page) is None:
            continue
        contributions[phrase] = contributions.get(phrase, 0) + STRUCTURE_BONUS
    if not contributions:
        return 0, []
    matched = sorted((t for t in contributions if contributions[t] > 0), key=lambda term: (-contributions[term], term))
    return sum(contributions.values()), matched


def _lines(text: str) -> list[str]:
    """Normalise each non-empty line. Line breaks stay, for heading and table checks."""
    return [normalise(line) for line in text.splitlines() if line.strip()]


def _spans(page: str, weights: dict[str, int]) -> list[tuple[int, int, str]]:
    """Return (start, end, term) for every term match on the normalised page."""
    found: list[tuple[int, int, str]] = []
    for term in weights:
        for match in _pattern(term).finditer(page):
            found.append((match.start(), match.end(), term))
    return found


def _drop_contained(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Drop a match that sits inside a strictly longer match."""
    return [span for span in spans if not _inside_longer(span, spans)]


def _inside_longer(span: tuple[int, int, str], spans: list[tuple[int, int, str]]) -> bool:
    """True when some other span covers this one and is longer."""
    start, end, _term = span
    width = end - start
    for other_start, other_end, _other in spans:
        if other_end - other_start <= width:
            continue
        if other_start <= start and other_end >= end:
            return True
    return False


def _counts(spans: list[tuple[int, int, str]]) -> dict[str, int]:
    """Count kept matches per term."""
    counts: dict[str, int] = {}
    for _start, _end, term in spans:
        counts[term] = counts.get(term, 0) + 1
    return counts


def _line_has(lines: list[str], term: str) -> bool:
    """True when the term matches one of these lines."""
    pattern = _pattern(term)
    return any(pattern.search(line) for line in lines)


def _table_line(lines: list[str], term: str) -> bool:
    """True when the term shares a line with at least TABLE_MIN_NUMBERS numbers."""
    pattern = _pattern(term)
    return any(pattern.search(line) and _number_count(line) >= TABLE_MIN_NUMBERS for line in lines)


def _pattern(term: str) -> re.Pattern[str]:
    """Match the phrase with a word boundary on each end.

    The page text is already normalised, so the phrase is a run of single spaces.
    """
    cached = _PATTERNS.get(term)
    if cached is not None:
        return cached
    parts = [re.escape(part) for part in normalise(term).split()]
    compiled = re.compile(r"\b" + r" ".join(parts) + r"\b")
    _PATTERNS[term] = compiled
    return compiled


def _number_count(line: str) -> int:
    """Count numeric tokens. A decimal such as 45.5 is one number."""
    return len(_NUMBER.findall(line))
