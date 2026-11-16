"""NSE: announcements, IPO lists, bulk and block deals, insider (PIT) filings.

Each read_* takes (source, ctx) and returns (items, records, notes). ctx is a Context from
tools/exchanges/__init__.py: ctx.get(url, max_age_days) -> text, ctx.blocks, ctx.start,
ctx.fetched_at, ctx.is_cached(url, max_age_days). Each parse_* is pure (text in, rows out)
so tests run on recorded responses.
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET

from config.exchanges import (BLOCK_CODES, FILE_MAX_AGE_DAYS, NSE_DEALS_ROW_CAP, NSE_XBRL_HOST, MAX_XBRL_PER_RUN, NSE_ANNOUNCEMENTS, NSE_BLOCK_CSV, NSE_BULK_CSV,
                              NSE_DEALS, NSE_INSIDER, NSE_IPO_CURRENT, NSE_IPO_PAST, NSE_IPO_UPCOMING, PAGES,
                              TODAY_MAX_AGE_DAYS)
from tools.fetch import FetchError
from tools.exchanges.common import (cash_sale, category_of, classify_subject, deal_record, in_window, make_item, make_record,
                                    money, parse_day, quantity, side_of)

NSE_DEAL_FIELDS = {"date": "BD_DT_DATE", "symbol": "BD_SYMBOL", "company": "BD_SCRIP_NAME", "name": "BD_CLIENT_NAME",
                   "side": "BD_BUY_SELL", "qty": "BD_QTY_TRD", "price": "BD_TP_WATP", "mode": "BD_REMARKS"}
# The archive CSV's printed headers (matched loosely: lower case, letters only).
_CSV_FIELDS = {"date": "date", "symbol": "symbol", "company": "securityname", "name": "clientname",
               "side": "buysell", "qty": "quantitytraded", "price": "tradepricewghtavgprice", "mode": "remarks"}
_XBRL_FACT = re.compile(r"\{[^}]+\}(\w+)$")


def _dmy(day) -> str:
    """A date as NSE's API wants it: DD-MM-YYYY."""
    return day.strftime("%d-%m-%Y")


def _json(text: str, url: str):
    """Parse an API answer; a page that is not JSON (an HTML challenge, say) raises ValueError naming the URL."""
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ValueError(f"not JSON from {url} (starts {text[:60]!r})") from exc


# ---------- announcements ----------

def parse_announcements(text: str, url: str = "") -> list[dict]:
    """Rows of /api/corporate-announcements (a JSON list)."""
    data = _json(text, url)
    return data if isinstance(data, list) else list((data or {}).get("data") or [])


def announcement_item(source: dict, row: dict) -> dict | None:
    """A money-event announcement as an item (its PDF as the document); None for every other subject."""
    subject, text = str(row.get("desc") or "").strip(), str(row.get("attchmntText") or "").strip()
    item_class = classify_subject(subject, text)
    company = str(row.get("sm_name") or row.get("symbol") or "").strip()
    if not item_class or not company:
        return None
    attachment = str(row.get("attchmntFile") or "").strip()
    documents = [attachment] if attachment.lower().endswith(".pdf") else []
    link = attachment or f"{PAGES['nse_announcements']}#{row.get('seq_id')}"
    published = parse_day(row.get("sort_date") or row.get("an_dt"))
    return make_item(source, company, subject, published, link, item_class, documents, summary=text)


def read_announcements(source: dict, ctx) -> tuple[list[dict], list[dict], list[str]]:
    """Announcements per 7-day block; only money-event subjects are kept."""
    items, seen = [], 0
    for first, last, age in ctx.blocks:
        url = NSE_ANNOUNCEMENTS.format(start=_dmy(first), end=_dmy(last))
        rows = parse_announcements(ctx.get(url, age), url)
        seen += len(rows)
        items += [item for item in (announcement_item(source, row) for row in rows)
                  if item and in_window(item["published_iso"], ctx.start)]
    return items, [], [f"{seen} announcements read, {len(items)} kept as money events"]


# ---------- IPO lists ----------

def _first(row: dict, *keys: str) -> str:
    """The first non-blank value among keys, as text."""
    for key in keys:
        value = row.get(key)
        if value not in (None, "", "-"):
            return str(value).strip()
    return ""


def ipo_items(source: dict, rows: list[dict], listed: bool, start) -> list[dict]:
    """IPO rows as items: open/upcoming issues as ipo_issue, listed ones (in the window) as listing_notice."""
    items = []
    for row in rows:
        company = _first(row, "companyName", "company", "name", "symbol")
        symbol = _first(row, "symbol")
        if not company:
            continue
        opens = parse_day(_first(row, "ipoStartDate", "issueStartDate", "startDate"))
        closes = parse_day(_first(row, "ipoEndDate", "issueEndDate", "endDate"))
        band = _first(row, "priceRange", "priceBand")
        kind = _first(row, "securityType", "series")
        if listed:
            day, price = parse_day(_first(row, "listingDate")), _first(row, "issuePrice")
            if not in_window(day, start):
                continue
            subject = f"Listed on NSE on {day}" + (f" (issue price {price})" if price else "")
            details = [kind, f"issue {opens} to {closes}", f"price band {band}" if band else ""]
            items.append(make_item(source, company, subject, day, f"{PAGES['nse_ipo']}#listed-{symbol or company}",
                                   "listing_notice", summary=" · ".join(filter(None, details))))
        else:
            subject = f"IPO open {opens or '?'} to {closes or '?'}" + (f", price band {band}" if band else "")
            items.append(make_item(source, company, subject, opens, f"{PAGES['nse_ipo']}#issue-{symbol or company}",
                                   "ipo_issue", summary=kind))
    return items


def read_ipo(source: dict, ctx) -> tuple[list[dict], list[dict], list[str]]:
    """Current and upcoming issues, and issues listed inside the window."""
    current = []
    for url in (NSE_IPO_CURRENT, NSE_IPO_UPCOMING):
        data = _json(ctx.get(url, TODAY_MAX_AGE_DAYS), url)
        current += data if isinstance(data, list) else list((data or {}).get("data") or [])
    past = _json(ctx.get(NSE_IPO_PAST, TODAY_MAX_AGE_DAYS), NSE_IPO_PAST)
    past = past if isinstance(past, list) else list((past or {}).get("data") or [])
    items = ipo_items(source, current, False, ctx.start) + ipo_items(source, past, True, ctx.start)
    return items, [], [f"{len(current)} open or upcoming issues listed by NSE; "
                       f"{sum(1 for i in items if i['class'] == 'listing_notice')} listings in the window"]


# ---------- bulk and block deals ----------

def parse_deals(text: str, url: str = "") -> list[dict]:
    """Rows of /api/historicalOR/bulk-block-short-deals ({"data": [...]})."""
    data = _json(text, url)
    return list((data or {}).get("data") or []) if isinstance(data, dict) else list(data or [])


def deal_records(source: dict, kind: str, rows: list[dict], link: str, fetched_at: str, start) -> list[dict]:
    """API deal rows as records inside the window."""
    found = [deal_record(source, kind, row, NSE_DEAL_FIELDS, link, fetched_at) for row in rows]
    return [record for record in found if record and in_window(record["trade_date"], start)]


def read_deals(source: dict, ctx, kind: str) -> tuple[list[dict], list[dict], list[str]]:
    """Block deals per 7-day block; bulk deals per day (NSE answers a bulk range with its first day only)."""
    option = "bulk_deals" if kind == "bulk_deal" else "block_deals"
    records, rows_seen, cut = [], 0, []
    for first, last, age in (ctx.days if kind == "bulk_deal" else ctx.blocks):
        url = NSE_DEALS.format(option=option, start=_dmy(first), end=_dmy(last))
        rows = parse_deals(ctx.get(url, age), url)
        rows_seen += len(rows)
        if len(rows) >= NSE_DEALS_ROW_CAP:
            cut.append(first.isoformat() if first == last else f"{first.isoformat()} to {last.isoformat()}")
        records += deal_records(source, kind, rows, PAGES["nse_deals"], ctx.fetched_at, ctx.start)
    notes = [f"{rows_seen} rows read"]
    if cut:
        notes.append(f"NSE returned its {NSE_DEALS_ROW_CAP}-row maximum for {', '.join(cut)}: those lists may be cut "
                     "(the archive file has the full latest day)")
    return [], records, notes


def read_bulk(source: dict, ctx):
    """Bulk deals (API)."""
    return read_deals(source, ctx, "bulk_deal")


def read_block(source: dict, ctx):
    """Block deals (API)."""
    return read_deals(source, ctx, "block_deal")


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def parse_deals_csv(text: str) -> list[dict]:
    """The archive's bulk.csv / block.csv as rows keyed like _CSV_FIELDS (headers matched loosely)."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader, None)
    if not header:
        return []
    keys = [_letters(cell) for cell in header]
    wanted = {name: keys.index(key) for name, key in _CSV_FIELDS.items() if key in keys}
    if not {"date", "symbol", "name", "side", "qty"} <= set(wanted):
        raise ValueError(f"unexpected deals CSV header: {header}")
    rows = []
    for cells in reader:
        if len(cells) >= len(keys) and any(cell.strip() for cell in cells):
            rows.append({name: cells[index].strip() for name, index in wanted.items()})
    return rows


def read_archive(source: dict, ctx) -> tuple[list[dict], list[dict], list[str]]:
    """The latest trading day's bulk.csv and block.csv from NSE's archive host."""
    records, notes = [], []
    fields = {name: name for name in _CSV_FIELDS}
    for url, kind in ((NSE_BULK_CSV, "bulk_deal"), (NSE_BLOCK_CSV, "block_deal")):
        rows = parse_deals_csv(ctx.get(url, TODAY_MAX_AGE_DAYS))
        found = [deal_record(source, kind, row, fields, url, ctx.fetched_at) for row in rows]
        kept = [record for record in found if record and in_window(record["trade_date"], ctx.start)]
        records += kept
        notes.append(f"{url.rsplit('/', 1)[-1]}: {len(rows)} rows, {len(kept)} in the window")
    return [], records, notes


# ---------- insider trading (PIT) ----------

def parse_pit_list(text: str, url: str = "") -> list[dict]:
    """Rows of /api/corporates-pit-gg ({"data": [...]}): one row per filing, its XBRL file named."""
    data = _json(text, url)
    return list((data or {}).get("data") or []) if isinstance(data, dict) else list(data or [])


def parse_pit_xbrl(text: str) -> dict:
    """A PIT XBRL filing: {"company", "symbol", "disclosures": [{fact: value, "context": id}, ...]}.

    Facts are grouped by their contextRef; the "MainI" context holds the company's own facts.
    """
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("an XBRL file with a DTD or entities is not read")
    root = ET.fromstring(text.encode("utf-8"))
    contexts: dict[str, dict] = {}
    for node in root:
        match = _XBRL_FACT.match(node.tag)
        ref = node.get("contextRef")
        if match and ref and not node.tag.startswith("{http://www.xbrl.org/2003/instance}"):
            contexts.setdefault(ref, {})[match.group(1)] = (node.text or "").strip()
    main = contexts.pop("MainI", {})
    disclosures = [{**facts, "context": ref} for ref, facts in contexts.items() if facts.get("NameOfThePerson")]
    return {"company": main.get("NameOfTheCompany", ""), "symbol": main.get("Symbol", ""), "disclosures": disclosures}


def insider_records(source: dict, filing: dict, link: str, fetched_at: str) -> tuple[list[dict], int]:
    """(sale records, other disclosures skipped) from one parsed XBRL filing; equity sales for cash only."""
    records, skipped = [], 0
    for row in filing["disclosures"]:
        side = side_of(row.get("SecuritiesAcquiredOrDisposedTransactionType"))
        qty = quantity(row.get("SecuritiesAcquiredOrDisposedNumberOfSecurity"))
        day = parse_day(row.get("DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyToDate")
                        or row.get("DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyFromDate"))
        equity = "equity" in str(row.get("TypeOfInstrument") or "equity").lower()
        if side != "sell" or not qty or not day or not equity or not cash_sale(row.get("ModeOfAcquisitionOrDisposal")):
            skipped += 1
            continue
        records.append(make_record(
            kind="insider_sale", exchange=source["exchange"], symbol=filing["symbol"], company=filing["company"],
            trade_date=day, name=row["NameOfThePerson"], category=category_of(row.get("CategoryOfPerson")),
            side="sell", qty=qty, price=None, value=money(row.get("SecuritiesAcquiredOrDisposedValueOfSecurity")),
            mode=row.get("ModeOfAcquisitionOrDisposal"), link=link, row_ref=f"XBRL context {row['context']}",
            fetched_at=fetched_at))
    return records, skipped


def read_insider(source: dict, ctx) -> tuple[list[dict], list[dict], list[str]]:
    """Insider filings per 7-day block, then each filing's XBRL file (newest first, MAX_XBRL_PER_RUN downloads)."""
    filings = []
    for first, last, age in ctx.blocks:
        url = NSE_INSIDER.format(start=_dmy(first), end=_dmy(last))
        filings += [row for row in parse_pit_list(ctx.get(url, age), url)
                    if in_window(parse_day(row.get("broadcastDateTime")), ctx.start)
                    and str(row.get("xmlFileName") or "").startswith(f"https://{NSE_XBRL_HOST}/")]
    filings = list({str(row["xmlFileName"]): row for row in filings}.values())
    records, skipped, downloads, waiting, failed = [], 0, 0, 0, 0
    for row in sorted(filings, key=lambda r: str(r.get("appId") or ""), reverse=True):
        xml_url = str(row["xmlFileName"])
        if not ctx.is_cached(xml_url, FILE_MAX_AGE_DAYS):
            if downloads >= MAX_XBRL_PER_RUN:
                waiting += 1
                continue
            downloads += 1
        try:
            filing = parse_pit_xbrl(ctx.get(xml_url, FILE_MAX_AGE_DAYS))
        except FetchError as exc:
            if exc.status in BLOCK_CODES:  # a block stops the source; any other miss skips one filing
                raise
            failed += 1
            continue
        except Exception:  # one unreadable filing does not stop the rest
            failed += 1
            continue
        found, other = insider_records(source, filing, str(row.get("ixbrl") or xml_url), ctx.fetched_at)
        records += found
        skipped += other
    notes = [f"{len(filings)} filings, {downloads} XBRL files downloaded, {len(records)} sales, "
             f"{skipped} buys, pledges, gifts, inter-se transfers and others skipped"]
    if waiting:
        notes.append(f"{waiting} filings wait for the next run (at most {MAX_XBRL_PER_RUN} downloads per run)")
    if failed:
        notes.append(f"{failed} XBRL files could not be read")
    return [], records, notes
