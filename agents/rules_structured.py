"""Structured signal events: exchange deal reports and insider-trading disclosures. Code only, no model for facts.

A structured event (event_type block_deal or insider_sale) lists record ids from
outputs/signals/<kind>.json. Each record is one printed row of an exchange report:
name, side, quantity, price or value, trade date, link and row reference. Nothing
is read from a PDF and no model proposes a fact; this module turns the rows into
people.json in the same shape the document events write, so rank, brief, report
and the app read it unchanged.

  - One person per printed name (same name tokens) and side. Rows of the same name
    and trade date are added together; several dates in one event are added too.
  - Holder type: the document name rules (agents/names.holder_type), plus the
    exchange counterparty words in config/holder_types.EXCHANGE_ENTITY_TOKENS, so
    brokers and funds go to the entities list.
  - Amount: the printed value, else quantity × printed price, in Decimal. A row with
    neither makes the amount unknown; nothing is guessed.
  - Timing: the trade date plus T+1 equity cash-market settlement (weekends skipped,
    exchange holidays not checked; the label says so). Off-market insider transfers
    have no exchange settlement date, and gifts or pledges are not cash at all.
  - Buyers do not come into money: they are kept for context, never called.
  - Evidence: the exchange record itself (link + row reference), one per row.

group_records(records) turns a records file into event specs: one event per
company, record kind and ISO week.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from agents.dates import age_text, fmt_date
from agents.figures import computed_figure, crore, crore_range, rupees_from_printed, unknown
from agents.identity import family_groups, identity_tokens
from agents.names import clean_name, holder_type, name_tokens
from config.event_types import (
    INSIDER_NON_CASH_MODE_WORDS,
    INSIDER_OFF_MARKET_MODE_WORDS,
    SETTLEMENT_LABEL,
    SETTLEMENT_TRADING_DAYS,
    event_config,
)
from config.holder_types import EXCHANGE_ENTITY_SUFFIX_TOKENS, EXCHANGE_ENTITY_TOKENS
from config.ranking import FUND_LIKE_TOKENS

LOG = logging.getLogger(__name__)
SECTION = "exchange_record"
KIND_TO_EVENT_TYPE = {"block_deal": "block_deal", "bulk_deal": "block_deal", "insider_sale": "insider_sale"}
KIND_WORDS = {"block_deal": ("a block deal", "block deals"), "bulk_deal": ("a bulk deal", "bulk deals"),
              "insider_sale": ("an insider-trading disclosure", "insider-trading disclosures")}
CATEGORY_ROLES = {"promoter": "Promoter", "promoter_group": "Promoter group", "director": "Director",
                  "kmp": "Key managerial person"}
# A printed value further than this from quantity × price is flagged (the printed value is still used).
VALUE_TOLERANCE = Decimal("0.01")
BUYER_REASON = "Bought shares: buying is not coming into money, so listed for context, not to call."
_LAKH = Decimal(100_000)
_CRORE = Decimal(10_000_000)
_COMPANY_NOISE = {"limited", "ltd", "the", "co", "company", "corporation", "india"}


# ---------- reading the records file ----------

_REPO = Path(__file__).resolve().parents[1]


def _shown(path: Path) -> str:
    """The path from the repo root, so errors (which reach runs.csv) never carry this machine's folders."""
    try:
        return path.resolve().relative_to(_REPO).as_posix()
    except ValueError:
        return path.name


def load_records(records_path: Path, ids: list[str]) -> tuple[list[dict], dict]:
    """The records with these ids, in the spec's order, and what the file says about its sources.

    A missing id is reported in records_missing, never invented. A missing file is an error:
    the exchange source has not written it yet.
    """
    path = Path(records_path)
    if not path.is_file():
        raise FileNotFoundError(f"records file not found: {_shown(path)}. Run the exchange source first.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_id = {str(record.get("id")): record for record in payload.get("records") or []}
    found = [by_id[record_id] for record_id in ids if record_id in by_id]
    if ids and not found:
        # An empty call list must not replace a good one: fail, so the job keeps the previous outputs.
        raise LookupError(f"none of the event's {len(ids)} record ids are in {path}")
    meta = {
        "records_file": str(path),
        "refreshed_at": payload.get("refreshed_at"),
        "source_status": payload.get("source_status") or {},
        "records_used": len(found),
        "records_missing": [record_id for record_id in ids if record_id not in by_id],
    }
    return found, meta


# ---------- grouping records into events ----------

def group_records(records: list[dict], require_seller: bool = True) -> list[dict]:
    """One event spec per company + record kind + ISO week of the trade date.

    A group with no seller is skipped when require_seller is True: nobody in it came into money.
    Records without a kind, company (or symbol) or a readable trade date are skipped and logged.
    """
    groups: dict[tuple, list[dict]] = {}
    for record in records:
        kind = record.get("kind")
        traded = _trade_date(record)
        company = _company_key(record)
        if kind not in KIND_TO_EVENT_TYPE or traded is None or not company:
            LOG.warning("record %s skipped: kind, company or trade date missing", record.get("id"))
            continue
        year, week, _day = traded.isocalendar()
        groups.setdefault((company, kind, year, week), []).append(record)
    specs = []
    for (company, kind, year, week), members in groups.items():
        if require_seller and not any(side_of(item) == "sell" for item in members):
            continue
        printed = Counter(str(item.get("company") or item.get("symbol")) for item in members).most_common()
        name = sorted(printed, key=lambda pair: (-pair[1], pair[0]))[0][0]
        slug = re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")[:60].strip("_")
        specs.append({
            "event_id": f"{slug}_{kind}_{year}w{week:02d}",
            "event_type": KIND_TO_EVENT_TYPE[kind],
            "company": name,
            "documents": [],
            "records": sorted(str(item["id"]) for item in members),
            "records_file": f"outputs/signals/{kind}.json",
            "event_date": max(_trade_date(item) for item in members).isoformat(),
        })
    return sorted(specs, key=lambda spec: spec["event_id"])


def _company_key(record: dict) -> str:
    """The company's name words without legal-form noise, so "X Ltd" and "X Limited" group together."""
    tokens = [token for token in name_tokens(str(record.get("company") or "")) if token not in _COMPANY_NOISE]
    return " ".join(tokens) or str(record.get("symbol") or "").strip().lower()


# ---------- people ----------

def build_people(spec, records: list[dict], meta: dict, as_of: date | None = None) -> dict:
    """people.json for a structured event, in the shape agents/people.build_people writes."""
    as_of = as_of or date.today()
    config = event_config(spec.event_type)
    kinds = set(config["record_kinds"])
    usable = [record for record in records if record.get("kind") in kinds and side_of(record)]
    skipped = [str(record.get("id")) for record in records if record.get("kind") not in kinds]
    no_side = [str(record.get("id")) for record in records if record.get("kind") in kinds and not side_of(record)]
    groups: dict[tuple[str, str], list[dict]] = {}
    for record in usable:
        groups.setdefault((_name_key(record), side_of(record)), []).append(record)
    people = [_person(members, side, config, as_of) for (_key, side), members in groups.items()]
    _unique_ids(people)
    families = family_groups([{"name": p["name_as_printed"], "holder_type": p["holder_type"]} for p in people])
    _attach_families(people, families)
    people.sort(key=lambda person: (person["name_clean"], person["person_id"]))
    sellers = [record for record in usable if side_of(record) == "sell"]
    return {
        "event_id": spec.event_id,
        "event_type": spec.event_type,
        "structured": True,
        "as_of": as_of.isoformat(),
        "price_basis": _price_basis(sellers),
        "sale": _sale_summary(people),
        "records_source": {**meta, "records_skipped_wrong_kind": skipped, "records_skipped_unknown_side": no_side},
        "people": people,
        "identity_log": _identity_log(groups),
        "family_groups": families,
        "counts": _counts(people, groups, families),
    }


def side_of(record: dict) -> str | None:
    """"buy" or "sell" from the printed side ("BUY", "Sell ", "B", "S"); None when it is neither."""
    side = str(record.get("side") or "").strip().lower()
    return {"buy": "buy", "b": "buy", "sell": "sell", "s": "sell"}.get(side)


def _unique_ids(people: list[dict]) -> None:
    """Two names that clean to the same slug get _2, _3 ... so person_id stays a key."""
    seen: dict[str, int] = {}
    for person in sorted(people, key=lambda item: (item["person_id"], item["name_as_printed"])):
        count = seen.get(person["person_id"], 0) + 1
        seen[person["person_id"]] = count
        if count > 1:
            person["person_id"] = f"{person['person_id']}_{count}"


def _name_key(record: dict) -> str:
    """The same printed name across rows and exchanges: identity tokens, in order."""
    tokens = identity_tokens(str(record.get("name_as_printed") or ""))
    return " ".join(tokens) or str(record.get("name_as_printed") or "").strip().lower()


def _person(members: list[dict], side: str, config: dict, as_of: date) -> dict:
    """One person (or entity) from the rows that share a name and a side."""
    members = sorted(members, key=lambda item: (str(item.get("trade_date")), str(item.get("id"))))
    printed = Counter(str(item.get("name_as_printed")).strip() for item in members)
    name = sorted(printed, key=lambda text: (-printed[text], text))[0]
    kind, kind_reason = exchange_holder_type(name)
    cash, repeats = _once_per_disclosure([item for item in members if side == "sell" and settlement_kind(item) != "not_cash"])
    not_cash = [item for item in members if side == "sell" and settlement_kind(item) == "not_cash"]
    role = _role(members)
    slug = re.sub(r"[^a-z0-9]+", "_", clean_name(name)).strip("_") or "unnamed"
    person = {
        "person_id": f"p_{slug}" + ("_bought" if side == "buy" else ""),
        "name_as_printed": name,
        "names_as_printed": list(printed),
        "name_clean": clean_name(name),
        "holder_type": kind,
        "holder_type_reason": kind_reason,
        "role_as_printed": role,
        "role_by_section": {SECTION: role} if role else {},
        "side": side,
        "record_ids": [str(item.get("id")) for item in members],
        "trades": _trades(members),
        "conflicts": {},
        "flags": [],
        "family_group": None,
        "evidence": [record_evidence(item) for item in members],
    }
    if repeats:
        person["flags"].append(f"{len(repeats)} disclosure row(s) printed on more than one exchange counted once: "
                               + ", ".join(_row_label(item) for item in repeats))
    if cash:
        _seller(person, cash, as_of)
        unclear = [item for item in cash if settlement_kind(item) == "unknown"]
        if unclear:
            person["flags"].append("mode unsure: not printed as a market or off-market sale ("
                                   + ", ".join(sorted({_mode(item) for item in unclear})) + "); confirm it was for cash")
        if not_cash:
            person["flags"].append(f"{len(not_cash)} row(s) not counted as cash: "
                                   + ", ".join(sorted({_mode(item) for item in not_cash})))
    else:
        _no_money(person, members, side)
    person["confidence"] = confidence(person, config)
    return person


def _once_per_disclosure(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(rows to count, repeats). An insider disclosure is filed on every exchange the company lists on: a row with
    the same trade date and quantity as one already counted from another exchange is the same transaction.
    Deal rows are never dropped: a block deal is a trade on one exchange."""
    kept, repeats, seen = [], [], {}
    for row in rows:
        key = (row.get("trade_date"), _quantity(row))
        if row.get("kind") == "insider_sale" and key in seen and seen[key] != row.get("exchange"):
            repeats.append(row)
            continue
        seen.setdefault(key, row.get("exchange"))
        kept.append(row)
    return kept, repeats


def _seller(person: dict, rows: list[dict], as_of: date) -> None:
    """A seller for cash: shares sold, proceeds and settlement timing."""
    quantity = sum((_quantity(item) or 0) for item in rows)
    person["seller_status"] = "verified"
    person["shares_offered"] = indian(Decimal(quantity))
    person["amounts"] = {"proceeds": proceeds(rows, person["flags"])}
    person["timing"] = {"proceeds": settlement_timing(rows, as_of)}
    person["why_money"] = _action_words("sold", rows)


def _no_money(person: dict, rows: list[dict], side: str) -> None:
    """A buyer, or a seller whose rows are gifts, pledges or other non-cash transfers: context only."""
    verb = "bought" if side == "buy" else "transferred"
    person["seller_status"] = "no"
    if side == "buy":
        reason = BUYER_REASON
        money_reason = "bought shares; buying is not coming into money"
    else:
        modes = ", ".join(sorted({_mode(item) for item in rows}))
        reason = f"Transferred shares by {modes} (mode as printed): not a sale for cash, so no money from this event."
        money_reason = f"not a sale for cash (mode as printed: {modes})"
    person["amounts"] = {"proceeds": {"status": "not_applicable", "reason": money_reason}}
    person["timing"] = {"proceeds": {"status": "not_applicable", "reason": money_reason}}
    person["why_money"] = _action_words(verb, rows)
    person["context_reason"] = reason


def exchange_holder_type(name: str) -> tuple[str, str]:
    """The document name rules, then the exchange counterparty words: brokers and funds are entities."""
    kind, reason = holder_type(name)
    if kind in ("entity", "family_vehicle"):
        return kind, reason
    tokens = name_tokens(name)
    for token in tokens:
        if token in EXCHANGE_ENTITY_TOKENS:
            return "entity", f"contains '{token}' (exchange counterparty word)"
    if tokens and tokens[-1] in EXCHANGE_ENTITY_SUFFIX_TOKENS:
        return "entity", f"ends with '{tokens[-1]}' (legal form)"
    if kind == "unsure":
        for token in tokens:
            if token in FUND_LIKE_TOKENS:
                return "entity", f"contains '{token}' (fund word)"
    return kind, reason


def confidence(person: dict, config: dict) -> dict:
    """high, medium or low from how well the printed name identifies a holder. Kept apart from the amount."""
    label = config["seller_label"]
    tokens = name_tokens(person["name_as_printed"])
    reasons = [f"named in {label} (structured record, read by code)"]
    if person["holder_type"] == "unsure":
        return {"level": "low", "reasons": ["holder type unsure: " + person["holder_type_reason"]] + reasons}
    unsure = [flag for flag in person["flags"] if "unsure" in flag]
    if unsure:
        return {"level": "low", "reasons": unsure + reasons}
    level = "high"
    initials = [token for token in tokens if len(token) == 1]
    if person["holder_type"] == "person" and initials:
        level = "medium"
        reasons.append(f"name printed with initials ({' '.join(initials).upper()}); confirm the client before calling")
    elif person["holder_type"] == "person":
        reasons.append("full name printed")
    if len(person["names_as_printed"]) > 1:
        level = "medium" if level == "high" else level
        reasons.append("name printed differently across rows: " + " / ".join(person["names_as_printed"]))
    return {"level": level, "reasons": reasons}


# ---------- amounts ----------

def proceeds(rows: list[dict], flags: list[str]) -> dict:
    """The sale value: printed value per row, else quantity × printed price. Unknown when a row has neither."""
    total = Decimal(0)
    workings, inputs, kinds = [], [], set()
    for row in rows:
        value, how, note = record_value(row)
        if value is None:
            return unknown(f"{_row_label(row)} prints neither a trade value nor a price")
        if note:
            flags.append(note)
        total += value
        kinds.add(how)
        workings.append(_working(row, value, how))
        inputs.extend(_inputs(row, how))
    working = "; ".join(workings)
    if len(rows) > 1:
        working += f"; total {money_words(total)}"
    price_kind = "trade_price" if kinds == {"quantity_x_price"} else ("trade_value" if kinds == {"printed_value"}
                                                                       else "trade_price_and_value")
    return computed_figure(total, total, money_words(total), working, {"kind": price_kind, "inputs": []}, inputs)


def record_value(record: dict) -> tuple[Decimal | None, str | None, str | None]:
    """(rupees, how, flag) for one row. how is printed_value or quantity_x_price; flag notes a mismatch."""
    quantity = _quantity(record)
    price = rupees(record.get("price_inr"))
    value = rupees(record.get("value_inr"))
    # A filing that prints 0 for the consideration (a transfer with no price) gives no amount, not "₹0".
    price = price if price is not None and price > 0 else None
    value = value if value is not None and value > 0 else None
    if value is not None:
        note = None
        if quantity and price is not None:
            product = Decimal(quantity) * price
            if product and abs(value - product) / product > VALUE_TOLERANCE:
                note = (f"{_row_label(record)}: printed value {money_words(value)} differs from quantity × price "
                        f"{money_words(product)}; the printed value is used")
        return value, "printed_value", note
    if quantity and price is not None:
        return Decimal(quantity) * price, "quantity_x_price", None
    return None, None, None


def rupees(value: object) -> Decimal | None:
    """A printed rupee amount as Decimal: "1,234.50", "₹ 1,234.50", "Rs. 12.4 crore". None when unreadable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().lower()
    with_unit = rupees_from_printed(text)
    if with_unit is not None:
        return with_unit
    bare = re.sub(r"(₹|rs\.?|inr|,|\s)", "", text)
    if not re.fullmatch(r"\d+(\.\d+)?", bare):
        return None
    try:
        return Decimal(bare)
    except InvalidOperation:
        return None


def money_words(rupees_value: Decimal) -> str:
    """"₹153.08 crore", "₹4.50 lakh", or "₹20,000" under a lakh."""
    if rupees_value >= _CRORE:
        return crore_range(rupees_value, rupees_value)
    if rupees_value >= _LAKH:
        return f"₹{(rupees_value / _LAKH).quantize(Decimal('0.01'))} lakh"
    return f"₹{indian(rupees_value.quantize(Decimal('1')))}"


def indian(value: Decimal) -> str:
    """Indian digit grouping: 1240000 is "12,40,000"; 1234.50 is "1,234.50"."""
    sign = "-" if value < 0 else ""
    text = format(abs(value), "f")
    whole, _dot, fraction = text.partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join(groups + [tail]) if groups else tail
    return sign + grouped + (f".{fraction}" if fraction else "")


def _working(row: dict, value: Decimal, how: str) -> str:
    """One row's working, in printed numbers."""
    quantity = indian(Decimal(_quantity(row) or 0))
    if how == "quantity_x_price":
        return f"{quantity} shares × ₹{indian(rupees(row.get('price_inr')))} = {money_words(value)} ({_row_label(row)})"
    return f"{quantity} shares, value as printed {money_words(value)} ({_row_label(row)})"


def _inputs(row: dict, how: str) -> list[dict]:
    """The row's quantity and price (or value) as figure inputs, each with the record as evidence."""
    evidence = [_link_ref(row)]
    found = [{"field": "shares_sold", "value": indian(Decimal(_quantity(row) or 0)), "evidence": evidence}]
    if how == "quantity_x_price":
        found.append({"field": "trade_price", "value": f"₹{indian(rupees(row.get('price_inr')))}", "evidence": evidence})
    else:
        found.append({"field": "trade_value", "value": money_words(rupees(row.get("value_inr"))), "evidence": evidence})
    return found


# ---------- timing ----------

def settlement_kind(record: dict) -> str:
    """exchange (T+1 settlement), off_market (paid between the parties), not_cash (gift, pledge...), unknown."""
    if record.get("kind") in ("block_deal", "bulk_deal"):
        return "exchange"
    words = set(re.findall(r"[a-z]+", str(record.get("mode") or "").lower()))
    joined = " ".join(re.findall(r"[a-z]+", str(record.get("mode") or "").lower()))
    if any(stem in joined for stem in INSIDER_NON_CASH_MODE_WORDS):
        return "not_cash"
    if any(phrase in joined for phrase in INSIDER_OFF_MARKET_MODE_WORDS):
        return "off_market"
    if "market" in words:
        return "exchange"
    return "unknown"


def settles_on(traded: date) -> date:
    """Trade date + SETTLEMENT_TRADING_DAYS weekdays. Exchange holidays are not checked."""
    day, left = traded, SETTLEMENT_TRADING_DAYS
    while left:
        day += timedelta(days=1)
        if day.weekday() < 5:
            left -= 1
    return day


def settlement_timing(rows: list[dict], as_of: date) -> dict:
    """When the cash from exchange-settled rows arrives, labelled T+1; else why it is unknown.

    Rows on several dates: the cash counts as arrived from the first settlement (days_since), and the
    words say when the last part settles.
    """
    exchange = [row for row in rows if settlement_kind(row) == "exchange" and _trade_date(row)]
    if not exchange:
        modes = ", ".join(sorted({_mode(row) for row in rows}))
        if all(settlement_kind(row) == "off_market" for row in rows):
            result = unknown(f"off-market transfer (mode as printed: {modes}): paid between the parties, "
                             "so there is no exchange settlement date")
        else:
            result = unknown(f"mode of sale not printed as a market sale ({modes}), so the settlement date is not known")
        # The trade date is printed even when the payment date is not: the sale is that old, so rank can age it.
        dates = [_trade_date(row) for row in rows if _trade_date(row) and _trade_date(row) <= as_of]
        if dates:
            result["trade_date"] = max(dates).isoformat()
            result["days_since"] = (as_of - max(dates)).days
        return result
    latest = max(exchange, key=lambda row: (_trade_date(row), str(row.get("id"))))
    traded = _trade_date(latest)
    settle = settles_on(traded)
    first = settles_on(min(_trade_date(row) for row in exchange))
    if settle <= as_of:
        when = f"settled {fmt_date(settle)}, T+1 after the {fmt_date(traded)} trade ({age_text(settle, as_of)})"
    elif first <= as_of:
        when = f"part settled {fmt_date(first)}; the rest settles {fmt_date(settle)}, T+1 after the {fmt_date(traded)} trade"
    else:
        when = f"settles {fmt_date(settle)}, T+1 after the {fmt_date(traded)} trade"
    result = {
        "status": "settles",
        "when": when,
        "trade_date": traded.isoformat(),
        "settles_on": settle.isoformat(),
        "rule": "T+1",
        "note": SETTLEMENT_LABEL,
        "sources": [{"field": "trade_date", "value": fmt_date(traded), "evidence": [_link_ref(latest)]}],
    }
    if first <= as_of:
        result["days_since"] = (as_of - first).days
    return result


# ---------- words for the call list (the rules-module interface agents/rank.py uses) ----------

def why_money(person: dict) -> str:
    """One phrase: what this holder did, from the records."""
    return person.get("why_money") or "named in an exchange record"


def amount_display(person: dict) -> str:
    """The headline amount, or the reason it is unknown."""
    figure = person["amounts"]["proceeds"]
    if figure.get("status") == "computed":
        return figure["display"]
    word = "not applicable" if figure.get("status") == "not_applicable" else "unknown"
    return f"{word}: {figure.get('reason', 'not in the record')}"


def timing_display(person: dict) -> str:
    """When the cash arrives."""
    return _display_timing(person)[0]


def timing_display_status(person: dict) -> str:
    """The status the app's timing pill shows."""
    return _display_timing(person)[1]


def _display_timing(person: dict) -> tuple[str, str]:
    """(words, status) for the proceeds timing."""
    timing = person["timing"]["proceeds"]
    if timing.get("when"):
        return timing["when"], timing.get("status") or "unknown"
    word = "not applicable" if timing.get("status") == "not_applicable" else "unknown"
    return f"{word}: {timing.get('reason', 'not in the record')}", timing.get("status") or "unknown"


# ---------- evidence and small helpers ----------

def record_evidence(record: dict) -> dict:
    """The exchange record as a name evidence item, shaped like a page reference (row in place of page)."""
    return {**_link_ref(record), "field": "name_as_printed", "section": SECTION, "field_kept": True,
            "record_id": str(record.get("id")), "exchange": record.get("exchange"), "kind": record.get("kind")}


def _link_ref(record: dict) -> dict:
    """{source_url, link, printed_page (the row reference), row_ref, quote (the row as printed)}."""
    link = record.get("link")
    return {"source_url": link, "link": link, "pdf_index": None, "printed_page": record.get("row_ref"),
            "row_ref": record.get("row_ref"), "quote": row_text(record)}


def row_text(record: dict) -> str:
    """The record's printed fields on one line, for the evidence chip."""
    parts = [str(record.get("exchange") or ""), str(record.get("symbol") or ""), str(record.get("name_as_printed") or ""),
             str(record.get("side") or "").upper(), f"{indian(Decimal(_quantity(record) or 0))} shares"]
    if record.get("price_inr") not in (None, ""):
        parts.append(f"price {record['price_inr']}")
    if record.get("value_inr") not in (None, ""):
        parts.append(f"value {record['value_inr']}")
    if record.get("mode"):
        parts.append(str(record["mode"]))
    parts.append(str(record.get("trade_date") or ""))
    return " | ".join(part for part in parts if part)


def _row_label(record: dict) -> str:
    """The row reference as the source wrote it, prefixed with the exchange when it does not already say it."""
    ref = str(record.get("row_ref") or f"record {record.get('id')}")
    exchange = str(record.get("exchange") or "")
    return ref if not exchange or ref.upper().startswith(exchange.upper()) else f"{exchange} {ref}"


def _trades(rows: list[dict]) -> list[dict]:
    """Rows added up per trade date: quantity and the record ids behind it."""
    by_date: dict[str, dict] = {}
    for row in rows:
        day = by_date.setdefault(str(row.get("trade_date")), {"trade_date": str(row.get("trade_date")), "quantity": 0,
                                                              "record_ids": []})
        day["quantity"] += _quantity(row) or 0
        day["record_ids"].append(str(row.get("id")))
    return [by_date[key] for key in sorted(by_date)]


def _action_words(verb: str, rows: list[dict]) -> str:
    """"sold 12,40,000 shares in a block deal on 12 Nov 2026", or the mode for an insider disclosure."""
    quantity = indian(Decimal(sum((_quantity(row) or 0) for row in rows)))
    dates = sorted({_trade_date(row) for row in rows if _trade_date(row)})
    if not dates:
        when = "on an unprinted date"
    elif len(dates) == 1:
        when = f"on {fmt_date(dates[0])}"
    elif len(dates) == 2:
        when = f"on {fmt_date(dates[0])} and {fmt_date(dates[1])}"
    else:
        when = f"between {fmt_date(dates[0])} and {fmt_date(dates[-1])}"
    kinds = sorted({row.get("kind") for row in rows})
    if kinds == ["insider_sale"]:
        modes = sorted({_mode(row) for row in rows if row.get("mode")})
        how = f" ({', '.join(modes)})" if modes else ""
        return f"{verb} {quantity} shares{how} {when}"
    single, plural = KIND_WORDS.get(kinds[0], ("an exchange deal", "exchange deals")) if len(kinds) == 1 \
        else ("an exchange deal", "exchange deals")
    return f"{verb} {quantity} shares in {single if len(rows) == 1 else plural} {when}"


def _role(rows: list[dict]) -> str | None:
    """The insider category as a role ("Promoter group"); None for deal reports, which print none."""
    categories = [CATEGORY_ROLES.get(str(row.get("category"))) for row in rows]
    found = sorted({category for category in categories if category})
    return " / ".join(found) or None


def _mode(record: dict) -> str:
    """The mode as printed, or "mode not printed"."""
    return str(record.get("mode") or "").strip() or "mode not printed"


def _quantity(record: dict) -> int | None:
    """The quantity as an int, or None when it is missing or not a whole number."""
    value = record.get("quantity")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = re.sub(r"[,\s]", "", str(value or ""))
    return int(text) if text.isdigit() else None


def _trade_date(record: dict) -> date | None:
    """The record's YYYY-MM-DD trade date, or None."""
    try:
        return date.fromisoformat(str(record.get("trade_date")))
    except ValueError:
        return None


def _price_basis(sellers: list[dict]) -> dict:
    """The sellers' printed trade prices: one price, a range, or unknown (insider rows often print only a value)."""
    prices = [(rupees(row.get("price_inr")), row) for row in sellers]
    known = [(price, row) for price, row in prices if price is not None]
    if not known:
        return {"kind": "unknown", "reason": "the records print no trade price"}
    low = min(known, key=lambda pair: pair[0])
    high = max(known, key=lambda pair: pair[0])
    inputs = [{"field": "trade_price", "value": f"₹{indian(price)}", "evidence": [_link_ref(row)]}
              for price, row in (low, high)] if low is not high else [
        {"field": "trade_price", "value": f"₹{indian(low[0])}", "evidence": [_link_ref(low[1])]}]
    return {"kind": "trade_price", "low": str(low[0]), "high": str(high[0]), "inputs": inputs}


def _sale_summary(people: list[dict]) -> dict:
    """Event-level sale facts the app shows: dates, settlement rule and total shares sold for cash."""
    sellers = [person for person in people if person.get("seller_status") == "verified"]
    days = sorted({day["trade_date"] for person in sellers for day in person["trades"]})
    total = sum(day["quantity"] for person in sellers for day in person["trades"])
    if not days:
        return {"sale_date": "no sale for cash in these records", "sale_date_parsed": None,
                "settlement": SETTLEMENT_LABEL, "total_shares_offered": "none"}
    printed = fmt_date(date.fromisoformat(days[0]))
    if len(days) > 1:
        printed += f" to {fmt_date(date.fromisoformat(days[-1]))}"
    return {"sale_date": printed, "sale_date_parsed": days[-1], "settlement": SETTLEMENT_LABEL,
            "total_shares_offered": f"{indian(Decimal(total))} shares sold by {len(sellers)} seller(s)"}


def _identity_log(groups: dict) -> list[dict]:
    """A row-merge entry for every name printed more than one way (same name tokens)."""
    log = []
    for (_key, side), members in sorted(groups.items()):
        printed = sorted({str(item.get("name_as_printed")).strip() for item in members})
        for other in printed[1:]:
            log.append({"pair": [printed[0], other], "method": "same_name_tokens", "outcome": "merge", "side": side})
    return log


def _attach_families(people: list[dict], families: list[dict]) -> None:
    """Put {id, reason} on each family member, as agents/people.py does."""
    for family in families:
        for person in people:
            if person["name_as_printed"] in family["members"]:
                mine = [text for text in family["reasons"] if f"'{person['name_as_printed']}'" in text]
                person["family_group"] = {"id": family["id"], "reason": "; ".join(mine or family["reasons"])}


def _counts(people: list[dict], groups: dict, families: list[dict]) -> dict:
    """The same totals agents/people.py writes, for the report and the app."""
    def tally(values) -> dict:
        return dict(sorted(Counter(values).items()))

    log = _identity_log(groups)
    return {
        "people": len(people),
        "by_holder_type": tally(p["holder_type"] for p in people),
        "by_confidence": tally(p["confidence"]["level"] for p in people),
        "sellers": sum(1 for p in people if p["seller_status"] == "verified"),
        "sellers_unverified": 0,
        "buyers": sum(1 for p in people if p["side"] == "buy"),
        "proceeds_computed": sum(1 for p in people if p["amounts"]["proceeds"].get("status") == "computed"),
        "gain_computed": 0,
        "retained_valued": 0,
        "retained_timing": {"not_applicable": len(people)} if people else {},
        "identity_decisions": tally(entry["method"] for entry in log),
        "identity_merges": len(log),
        "llm_asks": 0,
        "family_groups": len(families),
        "flagged": sum(1 for p in people if p["flags"]),
    }


# ---------- command line: records file -> event files ----------

def main(argv: list[str] | None = None) -> int:
    """Print (or write to events/auto/) the event specs grouped from one records file."""
    parser = argparse.ArgumentParser(description="Group exchange records into structured event files.")
    parser.add_argument("records_file", help="outputs/signals/<kind>.json")
    parser.add_argument("--write", action="store_true", help="write events/auto/<event_id>.json")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(Path(args.records_file).read_text(encoding="utf-8"))
    specs = group_records(payload.get("records") or [])
    for spec in specs:
        if not args.write:
            print(json.dumps(spec, ensure_ascii=False))
            continue
        path = root / "events" / "auto" / f"{spec['event_id']}.json"
        if path.is_file():
            old = json.loads(path.read_text(encoding="utf-8"))
            spec["records"] = sorted(set(old.get("records") or []) | set(spec["records"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path} ({len(spec['records'])} records)")
    if not specs:
        print("no event: no group with a seller")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
