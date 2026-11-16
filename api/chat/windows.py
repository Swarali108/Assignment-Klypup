"""Time windows in a question ("today", "this week", "last 10 days", "upcoming") applied to money dates. Code only.

A window filters people and calendar rows by the date their money arrives (an item's timing.date_iso: the
listing or payment date for cash in hand, the lock-in end for unlocked shares). When nothing falls inside it,
the answer says so plainly and shows the nearest rows instead, each with how many days ago (or ahead) it is,
so "this week" never claims a row from three weeks ago.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from api import views

_UNITS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10,
              "fourteen": 14, "fifteen": 15, "thirty": 30, "a": 1}
_N = r"(?P<n>\d{1,3}|one|two|three|four|five|six|seven|ten|fourteen|fifteen|thirty|a)"
# "today" is a window only when the question is about money moving today, not "who should I call today".
_TODAY_MONEY = re.compile(r"\b(?:came|come|coming|got|get|gets|paid|pays|payment|listed|listing|lists|unlock\w*|"
                          r"lock-?ins?|money|cash|dates?)\b[^?]*\btoday\b|\btoday'?s? (?:listings?|unlocks?|payments?)", re.I)


@dataclass(frozen=True)
class Window:
    """A closed date range [start, end] and how the RM said it."""

    start: date
    end: date
    words: str  # as typed, e.g. "this week"

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()

    def contains(self, iso: str | None) -> bool:
        """True when the ISO date falls inside the window."""
        return bool(iso) and self.start_iso <= str(iso)[:10] <= self.end_iso

    def span_text(self) -> str:
        """'9 Nov to 15 Nov 2026' / '15 Nov 2026'."""
        if self.start == self.end:
            return views.nice_date(self.start_iso)
        return f"{views.nice_date(self.start_iso)} to {views.nice_date(self.end_iso)}"

    def tense(self, today: date | None = None) -> str:
        """'past' (ends today or earlier), 'future' (starts after today) or 'mixed'."""
        today = today or views.as_of()
        return "past" if self.end <= today else ("future" if self.start > today else "mixed")

    def as_data(self) -> dict:
        return {"words": self.words, "from": self.start_iso, "to": self.end_iso, "span": self.span_text(),
                "tense": self.tense()}


def _count(text: str) -> int:
    return int(text) if text.isdigit() else _NUM_WORDS.get(text.lower(), 1)


def _month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


_PAST = re.compile(r"\b(?:came|got|received|was paid|were paid|cashed|has come|have come|sold)\b", re.I)


def parse(question: str, today: date | None = None) -> Window | None:
    """The window a question names, or None. Weeks run Monday to Sunday.

    A past-tense question ("who came into money this month") never reaches past today: a listing due later this
    month has not paid anyone yet, so it is not counted as having come in.
    """
    today = today or views.as_of()
    found = _parse(question, today)
    if found and _PAST.search(question or "") and found.end > today >= found.start:
        found = Window(found.start, today, found.words + " so far")
    return found


def _parse(question: str, today: date) -> Window | None:
    q = (question or "").lower()
    monday = today - timedelta(days=today.weekday())
    match = re.search(rf"\b(?:last|past|previous|in the last|over the last) {_N} (?P<unit>days?|weeks?|months?)\b", q)
    if match:
        span = _count(match.group("n")) * _UNITS[match.group("unit")]
        return Window(today - timedelta(days=span), today, match.group(0))
    match = re.search(rf"\b(?:next|coming|in the next|over the next) {_N} (?P<unit>days?|weeks?|months?)\b", q)
    if match:
        span = _count(match.group("n")) * _UNITS[match.group("unit")]
        return Window(today, today + timedelta(days=span), match.group(0))
    if re.search(r"\bthis week\b", q):
        return Window(monday, monday + timedelta(days=6), "this week")
    if re.search(r"\b(?:last|previous) week\b", q):
        return Window(monday - timedelta(days=7), monday - timedelta(days=1), "last week")
    if re.search(r"\bpast week\b", q):
        return Window(today - timedelta(days=7), today, "the past week")
    if re.search(r"\bnext week\b", q):
        return Window(monday + timedelta(days=7), monday + timedelta(days=13), "next week")
    if re.search(r"\bthis month\b", q):
        first = today.replace(day=1)
        return Window(first, _month_end(first), "this month")
    if re.search(r"\b(?:last|previous) month\b", q):
        first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        return Window(first, _month_end(first), "last month")
    if re.search(r"\bnext month\b", q):
        first = _month_end(today.replace(day=1)) + timedelta(days=1)
        return Window(first, _month_end(first), "next month")
    if re.search(r"\byesterday\b", q):
        return Window(today - timedelta(days=1), today - timedelta(days=1), "yesterday")
    if re.search(r"\b(?:upcoming|coming up|due soon|in the coming days)\b", q):
        from config.chat import UPCOMING_DAYS

        return Window(today, today + timedelta(days=UPCOMING_DAYS), "upcoming")
    if _TODAY_MONEY.search(q):
        return Window(today, today, "today")
    return None


def date_of(item: dict) -> str | None:
    """The money date of a call item (timing.date_iso), or None when it is not known."""
    return ((item.get("timing") or {}).get("date_iso") or None)


def split(items: list[dict], window: Window, date_key=date_of) -> tuple[list[dict], list[dict]]:
    """(items inside the window, dated items outside it)."""
    inside, outside = [], []
    for item in items:
        iso = date_key(item)
        if not iso:
            continue
        (inside if window.contains(iso) else outside).append(item)
    return inside, outside


def days_from(iso: str, today: date | None = None) -> int:
    """Days between today and the date: positive in the past ('12 days ago'), negative ahead."""
    today = today or views.as_of()
    return (today - date.fromisoformat(str(iso)[:10])).days


def nearest(outside: list[dict], window: Window, limit: int, date_key=date_of) -> list[dict]:
    """The rows closest to the window (by days to its nearer edge), then by their stored order."""
    def gap(item: dict) -> int:
        iso = str(date_key(item))[:10]
        return (window.start - date.fromisoformat(iso)).days if iso < window.start_iso else \
            (date.fromisoformat(iso) - window.end).days

    ranked = sorted(enumerate(outside), key=lambda pair: (gap(pair[1]), pair[0]))
    return [item for _i, item in ranked[:limit]]


def fallback_facts(rows: list[dict], window: Window, date_key=date_of) -> dict:
    """Facts for 'nothing in this window; the nearest are ...': the day counts so the verifier passes them."""
    days = [days_from(date_key(r)) for r in rows]
    past = sorted(d for d in days if d > 0)
    ahead = sorted(-d for d in days if d < 0)
    return {"in_window": 0, "window": window.as_data(), "nearest_count": len(rows),
            "nearest_days_ago": [past[0], past[-1]] if past else None,
            "nearest_days_ahead": [ahead[0], ahead[-1]] if ahead else None}


def days_phrase(facts: dict) -> str:
    """'12 to 25 days ago' / 'in 3 to 9 days' / '12 days ago and in 3 days' from fallback_facts."""
    parts = []
    ago, ahead = facts.get("nearest_days_ago"), facts.get("nearest_days_ahead")
    if ago:
        parts.append(f"{ago[0]} days ago" if ago[0] == ago[1] else f"{ago[0]} to {ago[1]} days ago")
    if ahead:
        parts.append(f"in {ahead[0]} days" if ahead[0] == ahead[1] else f"in {ahead[0]} to {ahead[1]} days")
    return " and ".join(parts)
