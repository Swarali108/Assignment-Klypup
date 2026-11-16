"""BSE: announcements, the public issue list, bulk and block deals, insider (PIT) disclosures.

Same shape as tools/exchanges/nse.py: read_*(source, ctx) -> (items, records, notes), and
pure parse_* functions for tests on recorded responses.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from config.exchanges import (BSE, BSE_ANNOUNCEMENTS, BSE_ATTACHMENT, BSE_BLOCK, BSE_BULK, BSE_INSIDER, BSE_ISSUES,
                              BSE_PAGE_ROWS, BSE_QUERIES, MAX_BSE_PAGES, PAGES, TODAY_MAX_AGE_DAYS)
from tools.exchanges.common import (cash_sale, category_of, classify_subject, deal_record, in_window, make_item, make_record,
                                    money, parse_day, quantity, side_of)

BSE_DEAL_FIELDS = {"date": "DEAL_DATE", "symbol": "ScripName", "company": "ScripName", "name": "CLIENT_NAME",
                   "side": "TRANSACTION_TYPE", "qty": "QUANTITY", "price": "PRICE"}
# The public issue list's IR_flag -> class. Rights issues ("RI") and debt issues ("DPI") are not kept.
ISSUE_CLASSES = {"IPO": ("ipo_issue", ""), "FPO": ("ipo_issue", "Further public offer"),
                 "OFS": ("ofs_notice", ""), "BUYBACK": ("buyback_announcement", "Buyback on BSE's issue list"),
                 "OTB": ("acquisition", "Open offer (offer to buy) on BSE's issue list")}


def _ymd(day) -> str:
    """A date as BSE's API wants it: YYYYMMDD."""
    return day.strftime("%Y%m%d")


def _table(text: str, url: str = "") -> list[dict]:
    """The "Table" list of a BSE API answer ({} means no rows); a non-JSON page raises ValueError."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"not JSON from {url} (starts {text[:60]!r})") from exc
    return list((data or {}).get("Table") or []) if isinstance(data, dict) else []


# ---------- announcements ----------

def attachment_url(row: dict) -> str | None:
    """The announcement's PDF as BSE's own page links it (AttachLive when PDFFLAG is 0, else AttachHis)."""
    name = str(row.get("ATTACHMENTNAME") or "").strip()
    if not name:
        return None
    folder = "AttachLive" if str(row.get("PDFFLAG")) == "0" else "AttachHis"
    return BSE_ATTACHMENT.format(folder=folder, name=name)


def announcement_item(source: dict, row: dict) -> dict | None:
    """A money-event announcement as an item; None for every other subject."""
    subject = str(row.get("SUBCATNAME") or row.get("CATEGORYNAME") or "").strip()
    text = str(row.get("HEADLINE") or row.get("MORE") or "").strip()
    item_class = classify_subject(subject, text)
    company = str(row.get("SLONGNAME") or "").strip()
    if not item_class or not company:
        return None
    pdf = attachment_url(row)
    link = pdf or f"{PAGES['bse_announcements']}#{row.get('NEWSID')}"
    published = parse_day(row.get("NEWS_DT") or row.get("DissemDT") or row.get("DT_TM"))
    return make_item(source, company, subject, published, link, item_class, [pdf] if pdf else [], summary=text)


def read_announcements(source: dict, ctx) -> tuple[list[dict], list[dict], list[str]]:
    """BSE_QUERIES (category, subcategory) per 7-day block, every page; money-event subjects only."""
    items, seen, requests = [], 0, 0
    for first, last, age in ctx.blocks:
        for category, subcategory in BSE_QUERIES:
            for page in range(1, MAX_BSE_PAGES + 1):
                url = BSE_ANNOUNCEMENTS.format(page=page, category=quote(category), start=_ymd(first),
                                               end=_ymd(last), subcategory=quote(subcategory))
                rows = _table(ctx.get(url, age), url)
                requests += 1
                seen += len(rows)
                items += [item for item in (announcement_item(source, row) for row in rows)
                          if item and in_window(item["published_iso"], ctx.start)]
                if len(rows) < BSE_PAGE_ROWS:
                    break
    unique = list({item["link"]: item for item in items}.values())
    return unique, [], [f"{requests} list pages, {seen} announcements read, {len(unique)} kept as money events"]


# ---------- public issues ----------

def issue_items(source: dict, rows: list[dict]) -> list[dict]:
    """Rows of the public issue list as items: IPO/FPO, OFS, buyback, open offer. Others are left out."""
    items = []
    for row in rows:
        flag = str(row.get("IR_flag") or "").strip().upper()
        if flag not in ISSUE_CLASSES:
            continue
        item_class, label = ISSUE_CLASSES[flag]
        company = str(row.get("LONG_NAME") or row.get("Scrip_Name") or "").strip()
        opens, closes = parse_day(row.get("Start_Dt")), parse_day(row.get("End_Dt"))
        price = str(row.get("Price_Band") or row.get("FloorPrice") or "").strip()
        status = {"F": "forthcoming", "L": "live"}.get(str(row.get("Status") or ""), str(row.get("Status") or ""))
        subject = f"{flag} {status} {opens or '?'} to {closes or '?'}" + (f", price {price}" if price else "")
        link = str(row.get("navigate_url") or "").strip() or f"{PAGES['bse_issues']}#{row.get('Scrip_cd')}"
        if company:
            items.append(make_item(source, company, subject, opens, link, item_class, label=label,
                                   summary=str(row.get("eXCHANGE_PLATFORM") or "")))
    return items


def read_issues(source: dict, ctx) -> tuple[list[dict], list[dict], list[str]]:
    """The current public issue list (it carries no date filter; every listed issue is kept)."""
    rows = _table(ctx.get(BSE_ISSUES, TODAY_MAX_AGE_DAYS), BSE_ISSUES)
    items = issue_items(source, rows)
    return items, [], [f"{len(rows)} issues listed, {len(items)} kept (IPO, OFS, buyback, open offer)"]


# ---------- bulk and block deals ----------

def deal_records(source: dict, kind: str, rows: list[dict], link: str, fetched_at: str, start) -> list[dict]:
    """BSE deal rows as records inside the window. BSE prints the scrip name, not the company's full name."""
    found = [deal_record(source, kind, row, BSE_DEAL_FIELDS, link, fetched_at) for row in rows]
    return [record for record in found if record and in_window(record["trade_date"], start)]


def read_bulk(source: dict, ctx):
    """The latest bulk deals list (no date filter on BSE's endpoint)."""
    rows = _table(ctx.get(BSE_BULK, TODAY_MAX_AGE_DAYS), BSE_BULK)
    records = deal_records(source, "bulk_deal", rows, PAGES["bse_bulk"], ctx.fetched_at, ctx.start)
    return [], records, [f"{len(rows)} rows read, {len(records)} in the window"]


def read_block(source: dict, ctx):
    """The latest block deals list."""
    rows = _table(ctx.get(BSE_BLOCK, TODAY_MAX_AGE_DAYS), BSE_BLOCK)
    records = deal_records(source, "block_deal", rows, PAGES["bse_block"], ctx.fetched_at, ctx.start)
    return [], records, [f"{len(rows)} rows read, {len(records)} in the window"]


# ---------- insider trading (PIT) ----------

def insider_record(source: dict, row: dict, fetched_at: str) -> dict | None:
    """One disclosure row as an insider_sale record; None unless it is an equity sale for cash with a count and a date.

    Only the fields named here are read: address, contact, PAN, CIN and DIN in the row are never kept.
    """
    side, qty = side_of(row.get("Fld_TransactionType")), quantity(row.get("Fld_SecurityNo"))
    day = parse_day(row.get("Fld_ToDate") or row.get("Fld_FromDate"))
    name = str(row.get("Fld_PromoterName") or "").strip()
    equity = "equity" in str(row.get("Fld_SecurityTypeName") or "equity").lower()
    if side != "sell" or not qty or not day or not name or not equity or not cash_sale(row.get("ModeOfAquisation")):
        return None
    xbrl = str(row.get("xbrlurl") or "").strip()
    link = (BSE + xbrl) if xbrl.startswith("/") else (xbrl or PAGES["bse_insider"])
    return make_record(kind="insider_sale", exchange=source["exchange"], symbol=str(row.get("Fld_ScripCode") or ""),
                       company=str(row.get("Companyname") or ""), trade_date=day, name=name,
                       category=category_of(row.get("Fld_PersonCatgName")), side="sell", qty=qty, price=None,
                       value=money(row.get("Fld_SecurityValue")), mode=row.get("ModeOfAquisation"), link=link,
                       row_ref=f"Fld_ID {row.get('Fld_ID')} · {name}", fetched_at=fetched_at)


def read_insider(source: dict, ctx) -> tuple[list[dict], list[dict], list[str]]:
    """Disclosures per 7-day block (BSE filters by its stamp date); equity sales kept."""
    records, rows_seen = [], 0
    for first, last, age in ctx.blocks:
        url = BSE_INSIDER.format(start=_ymd(first), end=_ymd(last))
        rows = _table(ctx.get(url, age), url)
        rows_seen += len(rows)
        for row in rows:
            record = insider_record(source, row, ctx.fetched_at)
            if record and in_window(parse_day(_stamp(row)), ctx.start):
                records.append(record)
    return [], records, [f"{rows_seen} disclosures read, {len(records)} equity sales for cash kept"]


def _stamp(row: dict) -> str:
    """The day BSE stamped the disclosure (what its date filter uses)."""
    return str(row.get("Fld_StampDate") or row.get("Fld_DateIntimation") or "")
