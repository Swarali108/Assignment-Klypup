"""Read printed dates and do calendar arithmetic. Code only.

A printed date is read only when it fits one of DATE_FORMATS after a leading
weekday and ordinal suffixes ("21st", "21 st") are dropped. Anything else is
None, never a guess. OCR damage such as "220d April" stays unread.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime

# Day-first numeric forms, as Indian filings print them.
DATE_FORMATS = (
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%d %B, %Y",
    "%d %b, %Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
)
_WEEKDAY = re.compile(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+", re.IGNORECASE)
_ORDINAL = re.compile(r"(\d)\s*(st|nd|rd|th)\b", re.IGNORECASE)
# A timetable qualifier printed before a date: "On or before Friday, November 06, 2026".
_QUALIFIER = re.compile(r"^(on\s+or\s+(before|about|after)|on|by)\s+", re.IGNORECASE)


def parse_printed_date(text: str) -> date | None:
    """"March 11, 2026", "Tuesday, June 9, 2026" or "21st April, 2026" as a date. Else None.

    A leading timetable qualifier ("On or before", "On or about") is dropped first.
    """
    cleaned = _QUALIFIER.sub("", " ".join(str(text or "").split()))
    cleaned = _WEEKDAY.sub("", cleaned)
    cleaned = _ORDINAL.sub(r"\1", cleaned)
    cleaned = " ".join(cleaned.replace(",", ", ").split()).replace(" ,", ",")
    for pattern in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            continue
    return None


def add_months(start: date, months: int) -> date:
    """start + months. A day past the new month's end becomes its last day (31 Aug + 6 = 28/29 Feb)."""
    year, month_index = divmod(start.month - 1 + months, 12)
    year += start.year
    month = month_index + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def months_between(earlier: date, later: date) -> int:
    """Whole calendar months from earlier to later. 11 Mar to 14 Nov is 8."""
    months = (later.year - earlier.year) * 12 + later.month - earlier.month
    if later.day < earlier.day:
        months -= 1
    return months


def fmt_date(value: date) -> str:
    """"9 Mar 2026"."""
    return f"{value.day} {value:%b} {value.year}"


def age_text(earlier: date, later: date) -> str:
    """How long ago, in words: "today", "12 days ago", "8 months ago"."""
    days = (later - earlier).days
    if days == 0:
        return "today"
    if days < 0:
        return f"in {-days} days"
    months = months_between(earlier, later)
    if months >= 2:
        return f"{months} months ago"
    return f"{days} days ago"
