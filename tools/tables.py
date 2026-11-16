"""Ruled-table rows from a cached PDF page, used as a second check on a holder's number.

Flattened page text loses the row a wrapped name belongs to ("Example Family Trust
(represented ... Private" / "Limited" on two lines, with the numbers between). The
ruled-line table finder in pdfplumber returns the whole cell instead, so a row reads
as [serial, name, shares, percent, ...].

row_confirms is deliberately strict, because a wrong match would put a number on
the wrong person:
- one cell of the row must be this name exactly (same words after footnote marks,
  a leading title and a leading serial number are dropped; "&" equals "and");
- a cell to the right of the name cell in the same row must print the value's one
  number (so a serial number to the left never confirms a value).

value_headers and total_conflict answer the opposite question, used to block a
value: which column header does this holder's value sit under, and does a Total
row print it while the holder's own row prints another number in that column.
They work on cells with their left and right edges, so a heading merged across
two columns ("Pre-Offer") counts for both.
No model call. Nothing is written to disk; rows are kept in memory per page.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

# A leading serial number printed in the name cell: "2.", "(ii)", "3)".
_SERIAL = re.compile(r"^\s*\(?(?:\d+|[ivxlc]+)[.)]\s+", re.IGNORECASE)
_GROUPING_COMMA = re.compile(r"(?<=\d),(?=\d)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# A holder figure, not a heading: digit grouping ("1,935,000") or five or more digits.
# Headings print small numbers only ("of ₹10 each", "March 31, 2026").
_DATA_NUMBER = re.compile(r"\d,\d{2,3}|\d{5,}")

# One table cell as read from the page: its text and its left and right edges.
Cell = tuple[str, float, float]


def row_confirms(pdf_path: str, pdf_index: int, name: str, value: str) -> bool:
    """True when one ruled-table row on this page has a cell that is the name and another cell with the value.

    pdf_index starts at 1. A missing file, a page out of range or a parse error gives False.
    """
    try:
        rows = page_rows(str(pdf_path), int(pdf_index))
    except Exception:
        return False
    return rows_confirm(rows, name, value)


def rows_confirm(rows: list[list[str | None]], name: str, value: str) -> bool:
    """The row test on rows already read: a name cell equal to the name, and the value in a cell to its right."""
    wanted = _numbers(value)
    key = _name_key(name)
    if len(wanted) != 1 or not key:
        return False
    number = wanted[0]
    for row in rows:
        cells = [cell or "" for cell in row]
        name_cells = [index for index, cell in enumerate(cells) if _name_key(cell) == key]
        for at in name_cells:
            if any(number in _numbers(cell) for cell in cells[at + 1:]):
                return True
    return False


def page_rows(pdf_path: str, pdf_index: int) -> list[list[str | None]]:
    """Every row of every ruled table pdfplumber finds on one page (1-based), as cell texts."""
    return [[cell[0] if cell else None for cell in row] for table in page_tables(pdf_path, pdf_index) for row in table]


@lru_cache(maxsize=256)
def page_tables(pdf_path: str, pdf_index: int) -> list[list[list[Cell | None]]]:
    """Every ruled table on one page (1-based): rows of cells, each (text, left, right) or None.

    None is a position covered by a merged cell, as pdfplumber reports it.
    """
    import pdfplumber

    path = Path(pdf_path)
    if not path.is_file():
        return []
    with pdfplumber.open(path) as pdf:
        if pdf_index < 1 or pdf_index > len(pdf.pages):
            return []
        tables = []
        for table in pdf.pages[pdf_index - 1].find_tables():
            rows = []
            for row, texts in zip(table.rows, table.extract()):
                rows.append([None if box is None else (text or "", box[0], box[2]) for box, text in zip(row.cells, texts)])
            tables.append(rows)
        return tables


def value_headers(tables: list[list[list[Cell | None]]], name: str, value: str) -> list[str]:
    """Headers of the cells in this holder's own row that print this value and no other number.

    Empty when there is no such cell, or when a table has no heading rows (a table
    continued from the page before). Headers are lowercased, spaces collapsed.
    """
    wanted = _numbers(value)
    key = _name_key(name)
    if len(wanted) != 1 or not key:
        return []
    headers: list[str] = []
    for table in tables:
        heading = _heading_cells(table)
        for row in _holder_rows(table, key):
            for cell in _value_cells(row, wanted[0]):
                text = _header_over(heading, cell)
                if text:
                    headers.append(text)
    return headers


def total_conflict(tables: list[list[list[Cell | None]]], name: str, value: str) -> bool:
    """True when a Total row prints this value, and this holder's own row in the same table prints another number below that heading.

    A holder whose own row is blank in that column (a share-history table that
    closes each holder with "Total (E)") is no conflict: that total is theirs.
    """
    wanted = _numbers(value)
    key = _name_key(name)
    if len(wanted) != 1 or not key:
        return False
    for table in tables:
        own_rows = _holder_rows(table, key)
        for row in table:
            if not _is_total_row(row):
                continue
            for total_cell in _value_cells(row, wanted[0]):
                for own in own_rows:
                    printed = [_numbers(cell[0]) for cell in own[1:] if cell and _overlaps(cell, total_cell)]
                    if any(numbers and wanted[0] not in numbers for numbers in printed):
                        return True
    return False


def _holder_rows(table: list[list[Cell | None]], key: tuple[str, ...]) -> list[list[Cell | None]]:
    """Rows of the table with a cell that is this name, each cut to start at that name cell."""
    found = []
    for row in table:
        for at, cell in enumerate(row):
            if cell and _name_key(cell[0]) == key:
                found.append(row[at:])
                break
    return found


def _value_cells(row: list[Cell | None], number: Decimal) -> list[Cell]:
    """Cells after the first one whose only number is this number."""
    return [cell for cell in row[1:] if cell and _numbers(cell[0]) == [number]]


def _is_total_row(row: list[Cell | None]) -> bool:
    """True when the row's first printed cell starts with "Total"."""
    from config.columns import TOTAL_WORD

    for cell in row:
        if cell and cell[0].strip():
            return cell[0].strip().lower().startswith(TOTAL_WORD)
    return False


def _heading_cells(table: list[list[Cell | None]]) -> list[Cell]:
    """Cells of the rows above the first row that prints a holder figure."""
    cells: list[Cell] = []
    for row in table:
        if any(cell and _DATA_NUMBER.search(cell[0]) for cell in row):
            return cells
        cells.extend(cell for cell in row if cell and cell[0].strip())
    return []


def _header_over(heading: list[Cell], cell: Cell) -> str:
    """The heading texts above this cell, top to bottom, lowercased with spaces collapsed."""
    parts = [" ".join(head[0].split()) for head in heading if _overlaps(head, cell)]
    return " ".join(part for part in parts if part).lower()


def _overlaps(left: Cell, right: Cell) -> bool:
    """True when two cells share more than half of the narrower one's width."""
    shared = min(left[2], right[2]) - max(left[1], right[1])
    narrower = min(left[2] - left[1], right[2] - right[1])
    return narrower > 0 and shared > narrower / 2


def _name_key(text: str) -> tuple[str, ...]:
    """A name's words for an exact comparison: marks, one title and a serial number dropped."""
    from agents.names import name_tokens

    cleaned = _SERIAL.sub("", " ".join(str(text or "").split()))
    tokens = ["and" if token == "&" else token.replace("&", "and") for token in name_tokens(cleaned)]
    return tuple(token for token in tokens if token)


def _numbers(text: str) -> list[Decimal]:
    """Numbers in a cell, grouping commas ignored: 19,35,000 is 1935000."""
    found: list[Decimal] = []
    for token in _NUMBER.findall(_GROUPING_COMMA.sub("", str(text or ""))):
        try:
            found.append(Decimal(token))
        except InvalidOperation:
            continue
    return found
