"""Shared pieces of the NSE and BSE readers: date blocks, items, records and their rules.

Code only; the rules live in config/exchanges.py. No company or person is named here.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from config.discovery import CLASSES
from config.event_types import EVENT_TYPES as SUPPORTED_TYPES
from config.exchanges import (BUY_WORDS, CATEGORY_WORDS, EXCHANGE_CLASSES, MAX_DAYS, NON_CASH_MODES,
                              PAST_DAY_MAX_AGE_DAYS,
                              SELL_WORDS, SUBJECT_RULES, TEXT_RULES, TODAY_MAX_AGE_DAYS)
from tools.discover import new_item

IST = timezone(timedelta(hours=5, minutes=30))
# Blocks of 7 days start on Mondays counted from this Monday, so a finished block keeps one URL.
_BLOCK_EPOCH = date(2000, 1, 3)
# A finished day's list is trusted only when it was fetched this long after the day closed.
_SETTLE = timedelta(hours=2)
ALL_CLASSES = {**CLASSES, **EXCHANGE_CLASSES}


# ---------- dates ----------

def ist_today(now: datetime) -> date:
    """The exchange's calendar day at now."""
    return now.astimezone(IST).date()


def window_start(since_days: float, now: datetime) -> date:
    """The first IST day inside the window (at most MAX_DAYS back)."""
    days = min(max(since_days, 0.0), float(MAX_DAYS))
    return (now - timedelta(days=days)).astimezone(IST).date()


def date_blocks(since_days: float, now: datetime) -> list[tuple[date, date, float]]:
    """(first day, last day, max_age_days) for 7-day blocks covering the window, oldest first.

    A finished block has a fixed URL and is cached until it was fetched after the block closed;
    the block holding today ends today and is read again after TODAY_MAX_AGE_DAYS.
    """
    today, start = ist_today(now), window_start(since_days, now)
    blocks, first = [], _BLOCK_EPOCH + timedelta(days=((start - _BLOCK_EPOCH).days // 7) * 7)
    while first <= today:
        last = first + timedelta(days=6)
        blocks.append((first, min(last, today), _max_age(min(last, today), today, now)))
        first = last + timedelta(days=1)
    return blocks


def day_ages(since_days: float, now: datetime) -> list[tuple[date, date, float]]:
    """(day, day, max_age_days) for each IST day in the window, oldest first (same rule as date_blocks)."""
    today, day, days = ist_today(now), window_start(since_days, now), []
    while day <= today:
        days.append((day, day, _max_age(day, today, now)))
        day += timedelta(days=1)
    return days


def _max_age(last: date, today: date, now: datetime) -> float:
    """How old a cached list ending on last may be: fetched after last closed, or TODAY_MAX_AGE_DAYS for today."""
    if last >= today:
        return TODAY_MAX_AGE_DAYS
    closed = datetime.combine(last + timedelta(days=1), datetime.min.time(), IST) + _SETTLE
    return min(max((now - closed).total_seconds() / 86400, TODAY_MAX_AGE_DAYS), PAST_DAY_MAX_AGE_DAYS)


def parse_day(text: object) -> str | None:
    """An exchange-printed date as YYYY-MM-DD: "09-NOV-2026", "14-Nov-2026 22:33", "13/11/2026",
    "2026-11-13T22:26:21.697" or "2026-11-13". None when it fits none of these."""
    raw = str(text or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    head = raw.split(" ")[0]
    for pattern in ("%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(head.title() if "%b" in pattern else head, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def in_window(day: str | None, start: date) -> bool:
    """True when the YYYY-MM-DD day is on or after start."""
    return bool(day) and day >= start.isoformat()


# ---------- items ----------

def classify_subject(subject: str, text: str = "") -> str | None:
    """The class for an announcement subject (SUBJECT_RULES), else from its text (TEXT_RULES); None: not kept."""
    for rules, words in ((SUBJECT_RULES, subject), (TEXT_RULES, text)):
        lowered = f" {str(words or '').lower()} "
        for item_class, all_of, none_of in rules:
            if all(any(w in lowered for w in group) for group in all_of) and not any(w in lowered for w in none_of):
                return item_class
    return None


def make_item(source: dict, company: str, subject: str, published: str | None, link: str, item_class: str,
              documents: list[str] | None = None, summary: str = "", label: str = "") -> dict:
    """A discovery item in tools/discover.new_item's schema, already classified by the exchange's subject.

    company is set from the exchange's own field (not split from the title). summary is the
    exchange's one-line text, kept beside the title.
    """
    item = new_item(source, f"{company} - {subject}", published, link)
    meta = ALL_CLASSES[item_class]
    item.update(company=company, documents=list(documents or []), summary=summary, exchange=source["exchange"],
                **{"class": item_class}, label=label or meta["label"], classified_by="exchange subject",
                event_type=meta["event_type"], supported=meta["event_type"] in SUPPORTED_TYPES)
    return item


# ---------- records ----------

def money(value: object) -> str | None:
    """A printed amount as a plain decimal string ("264.74", "2858200.00"); None when blank or not a number."""
    raw = str(value if value is not None else "").replace(",", "").strip()
    if not raw or raw in ("-", "NA", "null", "None"):
        return None
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return format(number, "f") if number.is_finite() else None


def quantity(value: object) -> int | None:
    """A printed share count as int; None when it is not a whole number."""
    raw = str(value if value is not None else "").replace(",", "").strip()
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    return int(number) if number.is_finite() and number == number.to_integral_value() else None


def side_of(printed: object) -> str | None:
    """"sell" or "buy" from a printed transaction type ("S", "SELL", "Disposal", "Market Purchase"); else None."""
    lowered = str(printed or "").strip().lower()
    if lowered in ("s",) or any(word in lowered for word in SELL_WORDS):
        return "sell"
    if lowered in ("b",) or any(word in lowered for word in BUY_WORDS):
        return "buy"
    return None


def cash_sale(mode: object) -> bool:
    """False when the printed mode pays no cash (a gift, an inter-se transfer, a pledge); True otherwise."""
    lowered = str(mode or "").lower()
    return not any(word in lowered for word in NON_CASH_MODES)


def twin_key(record: dict) -> tuple:
    """What one insider disclosure filed on both exchanges shares: name, trade date, count and value."""
    value = format(Decimal(record["value_inr"]).normalize(), "f") if record["value_inr"] else ""
    return (" ".join(record["name_as_printed"].upper().split()), record["trade_date"], record["quantity"], value)


def category_of(printed: object) -> str | None:
    """promoter / promoter_group / director / kmp / other from a printed category; None when blank."""
    lowered = str(printed or "").strip().lower()
    if not lowered:
        return None
    for category, words in CATEGORY_WORDS:
        if any(word in lowered for word in words):
            return category
    return "other"


def record_id(kind: str, exchange: str, symbol: str, trade_date: str, name: str, side: str, qty: int,
              price: str | None, value: str | None) -> str:
    """A stable id from the row's own content (never from when it was fetched).

    Amounts are compared as numbers ("39.50" in a CSV and 39.5 in JSON are one row).
    """
    amounts = [format(Decimal(amount).normalize(), "f") if amount else "" for amount in (price, value)]
    key = "|".join(str(part) for part in (kind, exchange, symbol.upper(), trade_date, " ".join(name.upper().split()),
                                          side, qty, *amounts))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def make_record(*, kind: str, exchange: str, symbol: str, company: str, trade_date: str, name: str,
                category: str | None, side: str, qty: int, price: str | None, value: str | None,
                mode: str | None, link: str, row_ref: str, fetched_at: str) -> dict:
    """One structured record in the shared schema (outputs/signals/<kind>.json)."""
    name = " ".join(str(name).split())
    return {"id": record_id(kind, exchange, symbol, trade_date, name, side, qty, price, value), "kind": kind,
            "exchange": exchange, "symbol": symbol, "company": " ".join(str(company).split()),
            "trade_date": trade_date, "name_as_printed": name, "category": category, "side": side,
            "quantity": qty, "price_inr": price, "value_inr": value, "mode": mode or None, "link": link,
            "row_ref": row_ref, "fetched_at": fetched_at}


def deal_record(source: dict, kind: str, row: dict, fields: dict, link: str, fetched_at: str) -> dict | None:
    """A bulk or block deal row as a record; None when a needed field is missing or unreadable.

    fields maps date/symbol/company/name/side/qty/price/mode to the row's own keys. The price is
    the printed (weighted average) trade price; the value is left None because deal lists do not print it.
    """
    day = parse_day(row.get(fields["date"]))
    name = str(row.get(fields["name"]) or "").strip()
    side, qty = side_of(row.get(fields["side"])), quantity(row.get(fields["qty"]))
    symbol = str(row.get(fields["symbol"]) or "").strip()
    if not (day and name and side and qty and symbol):
        return None
    mode = str(row.get(fields["mode"]) or "").strip() if fields.get("mode") else ""
    return make_record(kind=kind, exchange=source["exchange"], symbol=symbol,
                       company=str(row.get(fields["company"]) or symbol), trade_date=day, name=name, category=None,
                       side=side, qty=qty, price=money(row.get(fields["price"])), value=None,
                       mode=None if mode in ("", "-") else mode, link=link,
                       row_ref=f"{row.get(fields['date'])} · {symbol} · {name} · {row.get(fields['side'])} · {qty}",
                       fetched_at=fetched_at)

