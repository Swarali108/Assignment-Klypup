"""Check extracted values against the page text. No model calls.

A field is kept only when its evidence quote is on the cited page and the
value is inside that quote. A name that fails takes the whole row out of the
kept list. Amounts are not left on a row with no verified name.

Before any check, a quote that is not on its cited page but is on exactly one
other page of the same call has its citation moved to that page and marked
citation_corrected.

Two second chances, both code only:
- An amount that fails row binding ("not in this person's row" or "value not in
  quote") is kept when a ruled table on its cited page of the cached PDF has one row
  with this exact name in one cell and the value in another (tools/tables.py). Its
  evidence is marked verified_by "table_row".
- A name not found on its cited page (an OCR-garbled spot) is kept when the exact
  name is printed on another page of the same document in this call. The name
  evidence moves there, marked citation_corrected (by "name").

One last block, also code only (config/columns.py): a holder number that passed
the text checks, or was kept by a table row, is rejected when the ruled table on
its cited page puts it under another field's column ("wrong column: <header>"),
or when its quote is a Total row while the holder's own row prints a different
number in that column ("total row, not this person's row"). With no ruled table,
no cached PDF, or a header that names neither field, nothing changes.
"""

from __future__ import annotations

import re
from decimal import Decimal

import hashlib
import os
from pathlib import Path

from agents.locate import normalise
from agents.names import clean_name
from config.columns import COLUMN_FIELDS, COLUMN_WORDS, OTHER_COLUMN_WORDS, TOTAL_WORD
from tools.tables import page_tables, row_confirms, total_conflict, value_headers

# Commas that only group digits, as in 71,50,500 or 1,00,000.50.
_GROUPING_COMMA = re.compile(r"(?<=\d),(?=\d)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# A whole value that is only a filing blank, such as [●], [*] or [•].
_PLACEHOLDER = re.compile(r"\[[^\]\d]*[●•\*][^\]\d]*\]")
# How far the next name token may sit from the previous one, in normalised characters.
TOKEN_GAP = 120
# An amount quote must start within this many characters after the name.
ROW_WINDOW = 400
# A name must start within this many characters of its evidence quote's start.
NAME_NEAR_QUOTE = 200
# Footnote and reference marks printed beside figures and names ("1,150,000$", "Shares^").
# A quote usually leaves them out, so the last-resort matches ignore them on both sides.
_MARKS = frozenset("^*#†‡$@")
# Interleaved table cells: a wrapped neighbouring cell can put at most this many of its
# words between two words of one cell when the page is read line by line.
CELL_GAP_WORDS = 8
# A quote must have at least this many words before gaps between them are allowed.
CELL_MIN_WORDS = 4
# Where the text layer lost its spaces ("EQUITYSHARESOFFACEVALUE"), a name is matched
# without spaces, but only when this share or less of the surrounding text is whitespace.
MERGED_SPACE_SHARE = 0.05
MERGED_WINDOW = 40
# Failures of the text row check that a ruled-table row may still confirm.
TABLE_RESCUE_REASONS = ("not in this person's row", "value not in quote")
# An offer fact whose quote misses its value is kept when the value itself is printed on the page.
OFFER_RESCUE_REASONS = ("value not in quote", "quote not on page")
OFFER_RESCUE_MIN_CHARS = 8
# A role defined after the names ("BY A, B (TOGETHER, THE “PROMOTER SELLING SHAREHOLDERS”)")
# must start within this many normalised characters after the name.
DEFINED_AFTER_WINDOW = 2000
# Words that open such a definition. Spaces are ignored, since some text layers lost them.
_DEFINED_AFTER_MARKS = ("together", "collectively", "referredtoas")
# A quoted defined term about shareholders: another group's definition, so it ends the search.
_DEFINED_TERM = re.compile(r'"[^"]{0,80}shareholders?[^"]{0,10}"')
_FETCH_ROOT = Path(__file__).resolve().parents[1] / "cache" / "fetch"

HOLDER_FIELDS = (
    "name_as_printed",
    "role_as_printed",
    "shares_offered",
    "shares_held_pre_offer",
    "waca_per_share",
    "qualifier",
    "amount_as_printed",
)
OFFER_FIELDS = (
    "fresh_issue_size",
    "ofs_size",
    "price_band_low",
    "price_band_high",
    "offer_price",
    "face_value",
)
# A date's digits alone would let "11 April" pass on "March 11", so its printed text must match too.
DATE_FIELDS = (
    "listing_date", "allotment_date", "record_date", "opening_date", "closing_date", "payment_date",
    "sale_date", "sale_date_retail", "listing_date_scheduled",
)
# Group headings: printed above the rows they cover, so not used to place a row's quotes.
_HEADING_FIELDS = ("role_as_printed",)
# Holder numbers that must sit in this holder's own row.
_AMOUNT_FIELDS = (
    "shares_offered",
    "shares_held_pre_offer",
    "waca_per_share",
    "qualifier",
    "amount_as_printed",
    "shares_intended",
    "shares_accepted",
    "greenshoe_shares",
)


def verify(
    rows: list[dict],
    pages: list[dict],
    holder_fields: tuple[str, ...] = HOLDER_FIELDS,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (kept_rows, unattributed, rejections).

    A failed amount is null and the row stays. A failed name moves the whole
    row to unattributed, amounts included, so they are not kept.
    """
    kept: list[dict] = []
    unattributed: list[dict] = []
    rejections: list[dict] = []
    rows = [correct_citations(row, pages) for row in rows]
    for index, row in enumerate(rows):
        label = _row_label(row, index)
        name = row.get("name_as_printed")
        if _blank(name):
            unattributed.append({**row, "reason": "no evidence"})
            rejections.append(_rejection(label, "name_as_printed", "", "no evidence"))
            continue
        name_text = str(name)
        reason = _name_failure(name_text, row.get("evidence") or [], pages, rows)
        if reason == "name not on page":
            moved = name_on_other_page(row, pages, rows)
            if moved is not None:
                row, reason = moved, None
        if reason is not None:
            unattributed.append({**row, "reason": reason})
            rejections.append(_rejection(label, "name_as_printed", name_text, reason))
            continue
        fields = tuple(field for field in holder_fields if field != "name_as_printed")
        cleaned, rejected = verify_record(row, fields, pages, label, index, rows)
        kept.append(cleaned)
        rejections.extend(rejected)
    return kept, unattributed, rejections


def verify_offer(
    facts: dict,
    pages: list[dict],
    fields: tuple[str, ...] = OFFER_FIELDS,
) -> tuple[dict, list[dict]]:
    """Check one offer-facts object with the same quote rules as a holder row."""
    fixed = correct_citations(facts, pages)
    return verify_record(fixed, fields, pages, "offer_facts", None, [])


def correct_citations(record: dict, pages: list[dict]) -> dict:
    """Return a copy of record whose evidence points at the page that holds each quote.

    A quote already on its cited page is left alone. A quote on exactly one other
    page of this call is moved there and marked citation_corrected. A quote on
    several pages is moved only to a page that also holds every other non-heading
    quote of this record (a row's quotes sit together); when more than one page
    holds the whole row, the first in document order is cited and the others are
    kept in citation_alternatives. That is marked "row" in citation_corrected_by.
    Otherwise the quote is left as it is, so the later check rejects it. Every
    later check still runs against the page that is cited.
    """
    evidence = record.get("evidence") or []
    row_pages = _row_pages(evidence, pages)
    fixed = dict(record)
    fixed["evidence"] = [_correct_one(item, pages, row_pages) for item in evidence]
    return fixed


def _row_pages(evidence: list[dict], pages: list[dict]) -> set[object]:
    """pdf indexes that hold every non-heading quote of this record. Headings can sit on an earlier page."""
    found: set[object] | None = None
    for item in evidence:
        quote = str(item.get("quote") or "")
        if item.get("field") in _HEADING_FIELDS or not normalise(quote):
            continue
        holders = {page.get("pdf_index") for page in _pages_with_quote(quote, pages)}
        found = holders if found is None else found & holders
    return found or set()


def count_corrected(records: list[dict]) -> int:
    """Count evidence objects marked citation_corrected across these records."""
    return sum(
        1
        for record in records
        for item in record.get("evidence") or []
        if item.get("citation_corrected") is True
    )


def _correct_one(item: dict, pages: list[dict], row_pages: set[object] | None = None) -> dict:
    """Move one evidence object to the single page that holds its quote, when there is one."""
    quote = str(item.get("quote") or "")
    if not normalise(quote):
        return dict(item)
    cited = _page_text(pages, item.get("pdf_index"))
    if cited is not None and _quote_on_page(quote, cited):
        return dict(item)
    holders = _pages_with_quote(quote, pages)
    by = "quote"
    if len(holders) > 1 and item.get("field") not in _HEADING_FIELDS:
        holders = [page for page in holders if page.get("pdf_index") in (row_pages or set())]
        by = "row"
    if not holders or (len(holders) > 1 and by == "quote"):
        return dict(item)
    page = holders[0]
    printed = page.get("printed_page")
    moved = {
        **item,
        "pdf_index": page.get("pdf_index"),
        "printed_page": None if printed is None else str(printed),
        "citation_corrected": True,
    }
    if by == "row":
        moved["citation_corrected_by"] = "row"
        if len(holders) > 1:
            moved["citation_alternatives"] = [other.get("pdf_index") for other in holders[1:]]
    return moved


def _pages_with_quote(quote: str, pages: list[dict]) -> list[dict]:
    """One page per distinct pdf_index in this call whose text holds the quote."""
    found: dict[object, dict] = {}
    for page in pages:
        index = page.get("pdf_index")
        if index in found:
            continue
        text = _page_text(pages, index)
        if text is not None and _quote_on_page(quote, text):
            found[index] = page
    return list(found.values())


def verify_record(
    record: dict,
    fields: tuple[str, ...],
    pages: list[dict],
    row_label: str,
    row_index: int | None = None,
    rows: list[dict] | None = None,
) -> tuple[dict, list[dict]]:
    """Null each field in fields that the cited page does not support."""
    cleaned = dict(record)
    rejections: list[dict] = []
    others = rows or []
    for field in fields:
        value = cleaned.get(field)
        if _blank(value):
            cleaned[field] = None
            continue
        text = str(value)
        if _is_placeholder(text):
            cleaned[field] = None
            rejections.append(_rejection(row_label, field, text, "placeholder"))
            continue
        reason = _failure_reason(field, text, cleaned, pages, row_index, others)
        if reason is None:
            continue
        if reason in TABLE_RESCUE_REASONS and field in _AMOUNT_FIELDS and row_index is not None:
            confirmed = table_row_pages(cleaned, field, text, pages)
            blocked = [column_problem(cleaned, field, text, index, "", pages) for index in confirmed]
            if confirmed and any(blocked):
                reason = next(problem for problem in blocked if problem)
            elif confirmed:
                cleaned["evidence"] = _mark_table_row(cleaned.get("evidence") or [], field, confirmed)
                continue
        if row_index is None and reason in OFFER_RESCUE_REASONS:
            rescued = offer_value_evidence(field, text, cleaned.get("evidence") or [], pages)
            if rescued is not None:
                cleaned["evidence"] = rescued
                continue
        cleaned[field] = None
        rejections.append(_rejection(row_label, field, text, reason))
    return cleaned, rejections


def offer_value_evidence(field: str, value: str, evidence: list[dict], pages: list[dict]) -> list[dict] | None:
    """When an offer fact's quote misses its value, cite the value itself where it is printed.

    The value must be printed verbatim (after normalising) on the cited page or, failing
    that, on another page sent to the model. Short values are not rescued, since a bare
    number could be printed anywhere. Returns the evidence with this field's citations
    replaced, or None.
    """
    if len(value.strip()) < OFFER_RESCUE_MIN_CHARS or not any(ch.isdigit() for ch in value):
        return None
    cited = [item.get("pdf_index") for item in evidence if item.get("field") == field]
    ordered = [page for index in cited for page in pages if page.get("pdf_index") == index]
    ordered += [page for page in pages if page not in ordered]
    for page in ordered:
        if _quote_on_page(value, str(page.get("text") or "")):
            item = {"field": field, "pdf_index": page.get("pdf_index"), "printed_page": page.get("printed_page"),
                    "quote": value, "found_by": "code: value printed on this page"}
            return [other for other in evidence if other.get("field") != field] + [item]
    return None


def _failure_reason(
    field: str,
    value: str,
    record: dict,
    pages: list[dict],
    row_index: int | None,
    rows: list[dict],
) -> str | None:
    """Return why this value fails, or None when one citation supports it."""
    evidence = record.get("evidence") or []
    if field == "name_as_printed":
        return _name_failure(value, evidence, pages, rows)
    if field == "role_as_printed" and row_index is not None:
        return _role_failure(value, record, pages, rows, row_index)
    cited = [item for item in evidence if item.get("field") == field]
    if not cited:
        return "no evidence"
    saw_page = False
    saw_row = False
    saw_column: str | None = None
    for item in cited:
        page_text = _page_text(pages, item.get("pdf_index"))
        quote = str(item.get("quote") or "")
        if page_text is None or not _quote_on_page(quote, page_text):
            continue
        saw_page = True
        if not _value_in_quote(value, quote):
            continue
        if field in DATE_FIELDS and not _text_on_page(value, quote):
            continue
        if field in _AMOUNT_FIELDS and row_index is not None:
            if not _amount_in_row(record, quote, page_text, item.get("pdf_index"), row_index, rows, pages):
                saw_row = True
                continue
            problem = column_problem(record, field, value, item.get("pdf_index"), quote, pages)
            if problem:
                saw_column = problem
                continue
        return None
    if not saw_page:
        return "quote not on page"
    if saw_column:
        return saw_column
    if saw_row:
        return "not in this person's row"
    return "value not in quote"


def column_problem(record: dict, field: str, value: str, pdf_index: object, quote: str, pages: list[dict]) -> str | None:
    """Why the ruled table on this page says the value is not this holder's field, or None.

    Only blocks, never confirms. None when the field is not checked, the PDF is not
    cached, the page has no ruled table, or the table does not settle it.
    """
    if field not in COLUMN_FIELDS or not isinstance(pdf_index, int):
        return None
    name = str(record.get("name_as_printed") or "")
    for path in _cached_pdfs(pages, pdf_index):
        try:
            tables = page_tables(str(path), pdf_index)
        except Exception:
            continue
        headers = value_headers(tables, name, value)
        if headers and all(_names_other_field(header, field) for header in headers):
            return f"wrong column: {headers[0]}"
        if normalise(quote).startswith(TOTAL_WORD) and total_conflict(tables, name, value):
            return "total row, not this person's row"
    return None


def _names_other_field(header: str, field: str) -> bool:
    """True when the header names another field's column and not this field's."""
    if any(word in header for word in COLUMN_WORDS[field]):
        return False
    others = [word for other, words in COLUMN_WORDS.items() if other != field for word in words]
    return any(word in header for word in others + list(OTHER_COLUMN_WORDS))


def _name_failure(value: str, evidence: list[dict], pages: list[dict], rows: list[dict]) -> str | None:
    """None when a name quote is on its cited page and the name starts near that quote.

    The name may be found by its tokens and need not sit wholly inside the quote.
    With no name evidence, the name only has to be on one of the row's evidence pages.
    """
    cited = [item for item in evidence if item.get("field") == "name_as_printed"]
    if not cited:
        indexes = [item.get("pdf_index") for item in evidence]
        if not indexes:
            return "no evidence"
        for pdf_index in indexes:
            page_text = _page_text(pages, pdf_index)
            if page_text is not None and _locate_name(value, page_text, rows) is not None:
                return None
        return "name not on page"
    saw_page = False
    saw_name = False
    for item in cited:
        page_text = _page_text(pages, item.get("pdf_index"))
        if page_text is None:
            continue
        quote = str(item.get("quote") or "")
        quote_spans = _find_quote_spans(quote, normalise(page_text))
        if not quote_spans and clean_name(quote) == clean_name(value):
            # A quote that is only the name is found the way the name is: a name wrapped
            # in a table cell ("Reliance Industries 5,937,841,645 89.58 Limited") by its words.
            quote_spans = _locate_name_all(value, page_text, rows)
        if not quote_spans:
            continue
        saw_page = True
        name_spans = _locate_name_all(value, page_text, rows)
        saw_name = saw_name or bool(name_spans)
        if any(_name_near_quote(name, quote) for name in name_spans for quote in quote_spans):
            return None
    if not saw_page:
        return "quote not on page"
    if not saw_name:
        return "name not on page"
    return "name not near quote"


def table_row_pages(record: dict, field: str, value: str, pages: list[dict]) -> list[object]:
    """pdf indexes cited for this field whose ruled table has the holder's row with this value.

    The PDF is the cached copy of the document the cited page came from
    (cache/fetch/<sha256(url)>.bin, or FETCH_CACHE_DIR). No cached file means no rescue.
    """
    name = str(record.get("name_as_printed") or "")
    cited = []
    for item in record.get("evidence") or []:
        if item.get("field") == field and item.get("pdf_index") not in cited:
            cited.append(item.get("pdf_index"))
    confirmed: list[object] = []
    for pdf_index in cited:
        if not isinstance(pdf_index, int):
            continue
        for path in _cached_pdfs(pages, pdf_index):
            if row_confirms(str(path), pdf_index, name, value):
                confirmed.append(pdf_index)
                break
    return confirmed


def _cached_pdfs(pages: list[dict], pdf_index: object) -> list[Path]:
    """Cached PDF files of the documents in this call that supplied this pdf_index."""
    override = os.environ.get("FETCH_CACHE_DIR", "").strip()
    root = Path(override) if override else _FETCH_ROOT
    found: list[Path] = []
    for page in pages:
        url = page.get("source_url")
        if page.get("pdf_index") != pdf_index or not url:
            continue
        path = root / f"{hashlib.sha256(str(url).encode('utf-8')).hexdigest()}.bin"
        if path.is_file() and path not in found:
            found.append(path)
    return found


def _mark_table_row(evidence: list[dict], field: str, confirmed: list[object]) -> list[dict]:
    """Copies of the evidence, with this field's items on a confirmed page marked verified_by table_row."""
    marked: list[dict] = []
    for item in evidence:
        if item.get("field") == field and item.get("pdf_index") in confirmed:
            item = {**item, "verified_by": "table_row"}
        marked.append(item)
    return marked


def name_on_other_page(row: dict, pages: list[dict], rows: list[dict]) -> dict | None:
    """The row with its name evidence moved to another page of the same document that prints the exact name.

    Used when the cited page lacks the name (a garbled text layer). Pages the row's other
    quotes cite are tried first, then the rest of the document's pages in this call. The
    moved evidence quotes the name, keeps the old quote as quote_as_cited, and is marked
    citation_corrected by "name". None when no page prints the name exactly.
    """
    name = str(row.get("name_as_printed") or "")
    folded = normalise(name)
    evidence = row.get("evidence") or []
    name_items = [item for item in evidence if item.get("field") == "name_as_printed"]
    cited = [item.get("pdf_index") for item in (name_items or evidence)]
    urls = {page.get("source_url") for page in pages if page.get("pdf_index") in cited}
    others = [item.get("pdf_index") for item in evidence if item.get("pdf_index") not in cited]
    candidates = [page for page in pages if page.get("source_url") in urls and page.get("pdf_index") not in cited]
    candidates.sort(key=lambda page: (page.get("pdf_index") not in others, page.get("pdf_index") or 0))
    for page in candidates:
        text = page.get("text") or ""
        blockers = _longer_name_spans(name, text, rows)
        spans = [span for span in _exact_spans(normalise(text), folded) if not _inside_longer(span, blockers)]
        if spans:
            return {**row, "evidence": _move_name_evidence(evidence, name, page)}
    return None


def _move_name_evidence(evidence: list[dict], name: str, page: dict) -> list[dict]:
    """Point every name evidence item at page, quoting the name. Add one when the row had none."""
    printed = page.get("printed_page")
    target = {
        "pdf_index": page.get("pdf_index"),
        "printed_page": None if printed is None else str(printed),
        "quote": name,
        "citation_corrected": True,
        "citation_corrected_by": "name",
    }
    moved: list[dict] = []
    found = False
    for item in evidence:
        if item.get("field") == "name_as_printed":
            found = True
            item = {**item, **target, "quote_as_cited": item.get("quote")}
        moved.append(item)
    if not found:
        moved.append({"field": "name_as_printed", **target})
    return moved


def _name_near_quote(name_span: tuple[int, int], quote_span: tuple[int, int]) -> bool:
    """True when the name starts inside the quote, or within NAME_NEAR_QUOTE of its start."""
    name_start = name_span[0]
    quote_start, quote_end = quote_span
    if quote_start <= name_start <= quote_end:
        return True
    return abs(name_start - quote_start) <= NAME_NEAR_QUOTE


def _role_failure(
    value: str,
    record: dict,
    pages: list[dict],
    rows: list[dict],
    row_index: int | None = None,
) -> str | None:
    """A role passes as a group heading above the name, or as a cell in this person's own row.

    Heading: the quote holds the role and sits above one occurrence of the name, with
    no other heading between. Row cell: see _role_in_row. The reason names the first
    thing that failed: "quote not on page", "value not in quote", or "heading not above name".
    """
    evidence = record.get("evidence") or []
    cited = [item for item in evidence if item.get("field") == "role_as_printed"]
    if not cited:
        return "no evidence"
    anchors = _name_anchors(str(record.get("name_as_printed") or ""), evidence, pages, rows)
    other_roles = _other_roles(value, rows)
    on_page = holds_value = False
    for item in cited:
        quote = str(item.get("quote") or "")
        page_text = _page_text(pages, item.get("pdf_index"))
        if page_text is not None and _quote_on_page(quote, page_text):
            on_page = True
            if row_index is not None and _role_in_row(value, quote, page_text, item.get("pdf_index"), record, row_index, rows, pages):
                return None
        if not _value_in_quote(value, quote):
            continue
        holds_value = True
        if page_text is not None and _role_defined_after(quote, page_text, record, rows, other_roles):
            return None
        for anchor in anchors:
            place = _heading_place(quote, item.get("pdf_index"), pages, anchor, other_roles)
            if place == "ok":
                return None
            if place == "found":
                on_page = True
    if not on_page:
        return "quote not on page"
    if not holds_value:
        return "value not in quote"
    return "heading not above name"


def _role_in_row(
    value: str,
    quote: str,
    page_text: str,
    pdf_index: object,
    record: dict,
    row_index: int,
    rows: list[dict],
    pages: list[dict],
) -> bool:
    """True when the role is printed as a cell in this person's row, starting inside the quote.

    The role's words must chain on the page (other columns' text may sit between
    them when the cell wraps, as with names), the chain must start inside a span of
    the quote, and that start must be in this person's row: after one occurrence of
    the name and before the next other extracted name.
    """
    page = normalise(page_text)
    tokens = [token for token in normalise(value).split(" ") if token]
    if not tokens:
        return False
    quote_spans = _find_quote_spans(quote, page)
    chains = [span for span in _token_chain_spans(page, tokens) if any(start <= span[0] < end for start, end in quote_spans)]
    if not chains:
        return False
    name = str(record.get("name_as_printed") or "")
    others = _other_name_starts(rows, row_index, pages, pdf_index)
    names = _locate_name_all(name, page_text, rows)
    return any(_starts_in_row(name_span, [chain[0]], others) for name_span in names for chain in chains)


def _role_defined_after(
    quote: str,
    page_text: str,
    record: dict,
    rows: list[dict],
    other_roles: list[str],
) -> bool:
    """True when the role is defined after the names it covers, as cover pages print it.

    "... BY A, ... BY B (TOGETHER, THE “PROMOTER SELLING SHAREHOLDERS”)": the quote must
    open with together / collectively (referred to as), start after one occurrence of the
    name within DEFINED_AFTER_WINDOW, and nothing between may close another group: no other
    extracted role, no other together/collectively, no other quoted shareholder term.
    """
    page = normalise(page_text)
    if not any(mark in _squash_words(quote) for mark in _DEFINED_AFTER_MARKS):
        return False
    quote_starts = [start for start, _end in _find_quote_spans(quote, page)]
    names = _locate_name_all(str(record.get("name_as_printed") or ""), page_text, rows)
    roles = [_squash_words(role) for role in other_roles if role]
    for _name_start, name_end in names:
        for start in quote_starts:
            if start < name_end or start - name_end > DEFINED_AFTER_WINDOW:
                continue
            gap = page[name_end:start]
            squashed = _squash_words(gap)
            if any(role and role in squashed for role in roles):
                continue
            if any(mark in squashed for mark in _DEFINED_AFTER_MARKS) or _DEFINED_TERM.search(gap):
                continue
            return True
    return False


def _squash_words(text: str) -> str:
    """Lowercase letters and digits only, so "COLLECTIVELY REFERRED" and "COLLECTIVELYREFERRED" agree."""
    return re.sub(r"[^0-9a-z]", "", normalise(text))


def _heading_place(
    quote: str,
    cited_index: object,
    pages: list[dict],
    anchor: tuple[int, int, int],
    other_roles: list[str],
) -> str:
    """Return ok, found, or missing for this role quote against the name anchor."""
    name_pos, name_start = anchor[0], anchor[1]
    cited_pos = _page_pos(pages, cited_index)
    found = False
    nearest: tuple[int, int] | None = None
    for pos, page in enumerate(pages):
        if pos > name_pos:
            break
        if cited_pos is not None and pos > cited_pos:
            break
        spans = _find_quote_spans(quote, normalise(page.get("text") or ""))
        for _start, end in spans:
            found = True
            if pos > name_pos or (pos == name_pos and end > name_start):
                continue
            if nearest is None or (pos, end) > nearest:
                nearest = (pos, end)
    if nearest is None:
        return "found" if found else "missing"
    quote_pos, quote_end = nearest
    gap = _gap_text(pages, quote_pos, quote_end, name_pos, name_start)
    if any(role and role in gap for role in other_roles):
        return "found"
    return "ok"


def _gap_text(pages: list[dict], quote_pos: int, quote_end: int, name_pos: int, name_start: int) -> str:
    """Normalised text strictly between the role quote and the name."""
    if quote_pos == name_pos:
        text = normalise(pages[name_pos].get("text") or "")
        return text[quote_end:name_start]
    parts = [normalise(pages[quote_pos].get("text") or "")[quote_end:]]
    for pos in range(quote_pos + 1, name_pos):
        parts.append(normalise(pages[pos].get("text") or ""))
    parts.append(normalise(pages[name_pos].get("text") or "")[:name_start])
    return "\n".join(parts)


def _other_roles(value: str, rows: list[dict]) -> list[str]:
    """Other printed headings in this call. The same heading does not block itself."""
    own = normalise(value)
    found: list[str] = []
    for row in rows:
        role = row.get("role_as_printed")
        if _blank(role):
            continue
        folded = normalise(str(role))
        if folded and folded != own and folded not in found:
            found.append(folded)
    return found


def _name_anchors(
    name: str,
    evidence: list[dict],
    pages: list[dict],
    rows: list[dict],
) -> list[tuple[int, int, int]]:
    """Every (page position, name start, name end) of the name on its evidence pages.

    Occurrences inside a longer extracted name are left out. When the evidence
    pages hold no occurrence, every page of the call is tried.
    """
    indexes = _name_page_indexes(evidence)
    anchors = _anchors_on(name, pages, rows, indexes)
    if anchors:
        return anchors
    return _anchors_on(name, pages, rows, [])


def _anchors_on(
    name: str,
    pages: list[dict],
    rows: list[dict],
    indexes: list[object],
) -> list[tuple[int, int, int]]:
    """Occurrences of the name on pages whose pdf_index is in indexes. Empty indexes means all."""
    anchors: list[tuple[int, int, int]] = []
    for pos, page in enumerate(pages):
        if indexes and page.get("pdf_index") not in indexes:
            continue
        for start, end in _locate_name_all(name, page.get("text") or "", rows):
            anchors.append((pos, start, end))
    return anchors


def _name_page_indexes(evidence: list[dict]) -> list[object]:
    """Pages the name may be checked on. Other fields' pages are the fallback."""
    cited = [item.get("pdf_index") for item in evidence if item.get("field") == "name_as_printed"]
    if cited:
        return cited
    return [item.get("pdf_index") for item in evidence]


def _page_pos(pages: list[dict], pdf_index: object) -> int | None:
    """Index of pdf_index in this call, or None when that page was not supplied."""
    for pos, page in enumerate(pages):
        if page.get("pdf_index") == pdf_index:
            return pos
    return None


def _amount_in_row(
    record: dict,
    quote: str,
    page_text: str,
    pdf_index: object,
    row_index: int,
    rows: list[dict],
    pages: list[dict],
) -> bool:
    """True when the quote names this person, or starts in the row after any occurrence of the name.

    Every occurrence that is not inside a longer name is tried. A row ends
    ROW_WINDOW characters after the name, or at the next other extracted name.
    """
    name = str(record.get("name_as_printed") or "")
    if _locate_name(name, quote, rows) is not None:
        return True
    spans = _locate_name_all(name, page_text, rows)
    if not spans:
        return False
    others = _other_name_starts(rows, row_index, pages, pdf_index)
    quote_spans = _find_quote_spans(quote, normalise(page_text))
    quote_starts = [start for start, _end in quote_spans]
    if any(_starts_in_row(span, quote_starts, others) for span in spans):
        return True
    return any(_quote_holds_name(quote_span, span, others) for quote_span in quote_spans for span in spans)


def _quote_holds_name(quote_span: tuple[int, int], name_span: tuple[int, int], other_starts: list[int]) -> bool:
    """Interleaved cells: the quote's span on the page contains this name and no other name.

    "4,329,004 Equity Shares of face value of ₹1 2.35 <name> Shareholder each aggregating..."
    is one row read across its columns, so the amount belongs to the name inside it.
    """
    quote_start, quote_end = quote_span
    name_start, name_end = name_span
    inside = quote_start <= name_start and name_end <= quote_end
    return inside and not any(quote_start <= start < quote_end for start in other_starts)


def _starts_in_row(name_span: tuple[int, int], quote_starts: list[int], other_starts: list[int]) -> bool:
    """True when a quote starts inside the name or after it, before this row ends.

    A wrapped name is found by its tokens, so its own numbers can sit between its
    parts. The row ends ROW_WINDOW characters after the name, or at the next other name.
    """
    name_start, name_end = name_span
    limit = name_end + ROW_WINDOW
    for start in other_starts:
        if name_start < start < limit:
            limit = start
    return any(name_start <= start < limit for start in quote_starts)


def _other_name_starts(rows: list[dict], row_index: int, pages: list[dict], pdf_index: object) -> list[int]:
    """Start offsets of every occurrence of every other extracted name on this page.

    A row with the same cleaned name is the same person, not another row, so it is skipped.
    """
    page_text = _page_text(pages, pdf_index)
    if page_text is None:
        return []
    own = clean_name(str(rows[row_index].get("name_as_printed") or ""))
    starts: list[int] = []
    for index, row in enumerate(rows):
        name = row.get("name_as_printed")
        if index == row_index or _blank(name) or clean_name(str(name)) == own:
            continue
        starts.extend(start for start, _end in _locate_name_all(str(name), page_text, rows))
    return starts


def _locate_name(
    name: str,
    page_text: str,
    rows: list[dict] | None = None,
) -> tuple[int, int] | None:
    """Return the first (start, end) of the name that is not inside a longer name."""
    spans = _locate_name_all(name, page_text, rows)
    return spans[0] if spans else None


def _locate_name_all(
    name: str,
    page_text: str,
    rows: list[dict] | None = None,
) -> list[tuple[int, int]]:
    """Every (start, end) of the name in normalised page text, sorted by start.

    Exact hits are kept first. A token chain (the name split by other words) is
    added when it does not overlap a hit already kept; shorter chains win.
    A hit inside a longer extracted name from this call is left out.
    """
    page = normalise(page_text)
    if not page:
        return []
    blockers = _longer_name_spans(name, page_text, rows or [])
    kept = [span for span in _exact_spans(page, normalise(name)) if not _inside_longer(span, blockers)]
    tokens = [token for token in clean_name(name).split(" ") if token]
    chains = [span for span in _token_chain_spans(page, tokens) if not _inside_longer(span, blockers)]
    for span in sorted(chains, key=lambda item: (item[1] - item[0], item[0])):
        if not any(_overlaps(span, other) for other in kept):
            kept.append(span)
    for span in _merged_spans(page, tokens):
        if not _inside_longer(span, blockers) and not any(_overlaps(span, other) for other in kept):
            kept.append(span)
    return sorted(kept)


def _merged_spans(page: str, tokens: list[str]) -> list[tuple[int, int]]:
    """The name written without spaces, where the page's own text lost its spaces.

    "BYARVINDKONDANGILAKSHMIKUMAR," holds "Arvind Kondangi Lakshmikumar"; punctuation is
    ignored on both sides, so "CECILIAD’SOUZA" holds "Cecilia D'Souza". A hit counts
    only when the text around it is almost space-free (MERGED_SPACE_SHARE), so in normal
    text a short name is never found inside a longer word.
    """
    needle = "".join(re.sub(r"[^\w]", "", token) for token in tokens)
    if len(needle) < 6:
        return []
    kept = [(index, char) for index, char in enumerate(page) if char.isalnum() or char == "_"]
    squashed, indexes = "".join(char for _index, char in kept), [index for index, _char in kept]
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        at = squashed.find(needle, start)
        if at < 0:
            return spans
        span = (indexes[at], indexes[at + len(needle) - 1] + 1)
        window = page[max(0, span[0] - MERGED_WINDOW): span[1] + MERGED_WINDOW]
        if window and sum(char.isspace() for char in window) / len(window) <= MERGED_SPACE_SHARE:
            spans.append(span)
        start = at + 1


def _exact_spans(page: str, folded: str) -> list[tuple[int, int]]:
    """Every place the normalised name appears verbatim in the normalised page."""
    spans: list[tuple[int, int]] = []
    if not folded:
        return spans
    start = 0
    while True:
        at = page.find(folded, start)
        if at < 0:
            return spans
        spans.append((at, at + len(folded)))
        start = at + 1


def _token_chain_spans(page: str, tokens: list[str]) -> list[tuple[int, int]]:
    """A token chain from each occurrence of the first token. Chains that break are dropped."""
    spans: list[tuple[int, int]] = []
    if not tokens:
        return spans
    start = 0
    while True:
        found = _find_token(page, tokens[0], start, None)
        if found is None:
            return spans
        span = _chain_tokens(page, tokens, found[0], found[1])
        if span is not None:
            spans.append(span)
        start = found[0] + 1


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """True when two spans share at least one character."""
    return left[0] < right[1] and right[0] < left[1]


def _chain_tokens(page: str, tokens: list[str], first_start: int, first_end: int) -> tuple[int, int] | None:
    """Finish the token chain from one opening token. None when a gap is too wide."""
    cursor = first_end
    end = first_end
    for token in tokens[1:]:
        found = _find_token(page, token, cursor, TOKEN_GAP)
        if found is None:
            return None
        _token_start, token_end = found
        end = token_end
        cursor = token_end
    return first_start, end


def _longer_name_spans(name: str, page_text: str, rows: list[dict]) -> list[tuple[int, int]]:
    """Spans of different extracted names that have more tokens and contain this name."""
    mine = [token for token in clean_name(name).split(" ") if token]
    my_key = clean_name(name)
    spans: list[tuple[int, int]] = []
    seen: set[str] = set()
    for row in rows:
        other = str(row.get("name_as_printed") or "")
        key = clean_name(other)
        if not key or key == my_key or key in seen:
            continue
        other_tokens = [token for token in key.split(" ") if token]
        if len(other_tokens) <= len(mine) or not _tokens_cover(other_tokens, mine):
            continue
        seen.add(key)
        spans.extend(_locate_name_all(other, page_text, rows))
    return spans


def _tokens_cover(longer: list[str], shorter: list[str]) -> bool:
    """True when every shorter token appears in the longer list, in order."""
    index = 0
    for token in shorter:
        while index < len(longer) and longer[index] != token:
            index += 1
        if index == len(longer):
            return False
        index += 1
    return True


def _inside_longer(span: tuple[int, int], blockers: list[tuple[int, int]]) -> bool:
    """True when span sits inside a longer name and is not that name itself."""
    start, end = span
    for block_start, block_end in blockers:
        if block_start <= start and end <= block_end and (block_start, block_end) != (start, end):
            return True
    return False


def _find_token(page: str, token: str, start: int, max_gap: int | None) -> tuple[int, int] | None:
    """Find token as a whole word at or after start. max_gap limits the distance from start."""
    pattern = re.compile(r"(?<!\w)" + re.escape(token) + r"(?!\w)")
    match = pattern.search(page, start)
    if match is None:
        return None
    if max_gap is not None and match.start() - start > max_gap:
        return None
    return match.start(), match.end()


def _quote_on_page(quote: str, page_text: str) -> bool:
    """True when the quote sits on the page. Whitespace is ignored after normalise."""
    return bool(_find_quote_spans(quote, normalise(page_text)))


def _find_quote_spans(quote: str, page_norm: str) -> list[tuple[int, int]]:
    """Start and end of each quote hit in normalised page text.

    An exact hit is used when the spaces already agree. Otherwise the match
    ignores whitespace, so "₹ [●]" hits "₹[●]".
    """
    folded = normalise(quote)
    if not folded or not page_norm:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        at = page_norm.find(folded, start)
        if at < 0:
            break
        spans.append((at, at + len(folded)))
        start = at + 1
    if spans:
        return spans
    for drop in (frozenset(), _MARKS):
        spans = _squashed_spans(folded, page_norm, drop)
        if spans:
            return spans
    return _interleaved_spans(folded, page_norm)


def _squashed_spans(folded: str, page_norm: str, drop: frozenset) -> list[tuple[int, int]]:
    """Quote hits with whitespace (and the characters in drop) ignored on both sides.

    With drop=_MARKS, "1,150,000 EQUITY SHARES" hits "1,150,000$EQUITYSHARES".
    """
    needle, _ = _squash_map(folded, drop)
    if not needle:
        return []
    squashed, indexes = _squash_map(page_norm, drop)
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        at = squashed.find(needle, start)
        if at < 0:
            return spans
        spans.append((indexes[at], indexes[at + len(needle) - 1] + 1))
        start = at + 1


def _interleaved_spans(folded: str, page_norm: str) -> list[tuple[int, int]]:
    """Quote hits where a wrapped neighbouring cell's words sit between the quote's words.

    Every quote word must appear, in order, with at most CELL_GAP_WORDS other words
    before the next one; numbers must match exactly. Marks are ignored. Quotes shorter
    than CELL_MIN_WORDS words never match this way.
    """
    words = [word for word in (_strip_marks(word) for word in folded.split(" ")) if word]
    if len(words) < CELL_MIN_WORDS:
        return []
    found = list(re.finditer(r"\S+", page_norm))
    texts = [_strip_marks(match.group()) for match in found]
    spans: list[tuple[int, int]] = []
    for first, text in enumerate(texts):
        if text != words[0]:
            continue
        last = first
        for word in words[1:]:
            stop = min(len(texts), last + CELL_GAP_WORDS + 2)
            last = next((index for index in range(last + 1, stop) if texts[index] == word), -1)
            if last < 0:
                break
        if last >= 0:
            spans.append((found[first].start(), found[last].end()))
    return spans


def _strip_marks(word: str) -> str:
    """A word without footnote marks: "shares^" is "shares"."""
    return "".join(char for char in word if char not in _MARKS)


def _squash_map(text: str, drop: frozenset = frozenset()) -> tuple[str, list[int]]:
    """Return text with whitespace (and any character in drop) removed, and each kept character's index."""
    chars: list[str] = []
    indexes: list[int] = []
    for index, char in enumerate(text):
        if char.isspace() or char in drop:
            continue
        chars.append(char)
        indexes.append(index)
    return "".join(chars), indexes


def _value_in_quote(value: str, quote: str) -> bool:
    """True when the quote contains this value.

    Numbers match as whole tokens. Grouping commas are ignored, and decimals
    compare as Decimal, so 45.5 and 45.50 are the same number. Other text must
    appear in the quote after normalise().
    """
    wanted = _number_tokens(value)
    if wanted:
        found = _number_tokens(quote)
        return all(any(number == other for other in found) for number in wanted)
    return _text_on_page(value, quote)


def same_printed_value(left: str, right: str) -> bool:
    """True when both strings are the same number, or the same normalised text.

    71,50,500 and 7150500 are the same number. 45.5 and 45.50 are the same number.
    A text value with no digits matches only the same normalised text.
    """
    left_numbers = _number_tokens(left)
    right_numbers = _number_tokens(right)
    if left_numbers or right_numbers:
        return left_numbers == right_numbers
    return normalise(left) == normalise(right)


def number_tokens(text: object) -> list[Decimal]:
    """Every number in the text, as Decimal. Grouping commas are ignored: 71,50,500 is 7150500."""
    return _number_tokens(str(text or ""))


def printed_number(text: object) -> Decimal | None:
    """The one number in a printed value, as Decimal. None when there is no number or more than one.

    "₹1,250*" is 1250. "12,000" is 12000. "₹1,250 per share of ₹10" is None, because
    picking one of two numbers would be a guess.
    """
    if text is None:
        return None
    numbers = _number_tokens(str(text))
    return numbers[0] if len(numbers) == 1 else None


def _number_tokens(text: str) -> list[Decimal]:
    """Pull numbers out of text. 71,50,500 becomes Decimal('7150500')."""
    cleaned = _GROUPING_COMMA.sub("", text)
    return [Decimal(token) for token in _NUMBER.findall(cleaned)]


def _page_text(pages: list[dict], pdf_index: object) -> str | None:
    """Join every supplied page with this pdf_index. None when the index is absent."""
    matched = [page.get("text") or "" for page in pages if page.get("pdf_index") == pdf_index]
    if not matched:
        return None
    return "\n".join(matched)


def _text_on_page(value: str, page_text: str) -> bool:
    """True when the printed text appears on the page."""
    folded = normalise(value)
    if not folded:
        return False
    return folded in normalise(page_text)


def _is_placeholder(value: str) -> bool:
    """True when the value is a blank such as [●], [*] or [•], with no digits."""
    if re.search(r"\d", value):
        return False
    return _PLACEHOLDER.search(value) is not None


def _blank(value: object) -> bool:
    """True when the model left the field empty."""
    return value is None or (isinstance(value, str) and not value.strip())


def _row_label(row: dict, index: int) -> str:
    """Name the row in a rejection. Fall back to its position when the name is blank."""
    name = row.get("name_as_printed")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return f"#{index}"


def _rejection(row: str, field: str, value: str, reason: str) -> dict:
    """One failed field. The value is the text before it was cleared."""
    return {"row": row, "field": field, "value": value, "reason": reason}
