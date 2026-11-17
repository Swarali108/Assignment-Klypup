"""tools/exchanges on REAL responses recorded by the connector on 2026-11-15 (tests/fixtures/exchanges,
trimmed; SOURCES.json says where each came from). No network: fetchers and transports are fakes."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from config.exchanges import USER_AGENT
from tools import exchanges
from tools.discover import new_item
from tools.exchanges import bse, nse
from tools.exchanges.client import ExchangeClient
from tools.exchanges.common import date_blocks, day_ages, parse_day, window_start
from tools.fetch import FetchError

FIXTURES = Path(__file__).parent / "fixtures" / "exchanges"
NOW = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)  # 23:30 IST
START = date(2026, 11, 8)
NSE_SOURCE = {"id": "nse_test", "name": "NSE test", "exchange": "NSE"}
BSE_SOURCE = {"id": "bse_test", "name": "BSE test", "exchange": "BSE"}
ITEM_KEYS = set(new_item({"id": "x", "name": "x"}, "A - B", None, "https://example.org"))
RECORD_KEYS = {"id", "kind", "exchange", "symbol", "company", "trade_date", "name_as_printed", "category", "side",
               "quantity", "price_inr", "value_inr", "mode", "link", "row_ref", "fetched_at"}


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _json(name: str):
    return json.loads(_text(name))


# URL fragment -> fixture; tried in order.
ROUTES = (
    ("corporate-announcements", "nse_announcements.json"),
    ("ipo-current-issue", "nse_ipo_current.json"),
    ("all-upcoming-issues", "nse_ipo_current.json"),
    ("public-past-issues", "nse_ipo_past.json"),
    ("optionType=bulk_deals", "nse_bulk_deals.json"),
    ("optionType=block_deals", "nse_block_deals.json"),
    ("/content/equities/bulk.csv", "nse_bulk.csv"),
    ("/content/equities/block.csv", "nse_block.csv"),
    ("corporates-pit-gg", "nse_pit_list.json"),
    ("AnnSubCategoryGetData", "bse_announcements.json"),
    ("GetPublicIssue_par_updated", "bse_issues.json"),
    ("BulkDeal_Beta", "bse_bulk.json"),
    ("BlockDeal_Beta", "bse_block.json"),
    ("getCorp_Regulation_ng", "bse_insider.json"),
)


def _fake_fetcher(calls: list[str], blocked_hosts: tuple[str, ...] = ()):
    """Serve fixtures by URL; the one recorded XBRL file is served, other XBRL files are 404s."""
    xbrl_url = _json("nse_pit_list.json")["data"][0]["xmlFileName"]

    def fetch(url: str, max_age_days: float) -> str:
        calls.append(url)
        host = url.split("/")[2]
        if host in blocked_hosts:
            raise FetchError(url, 403, f"HTTP 403 from {host}")
        if url == xbrl_url:
            return _text("nse_pit_xbrl.xml")
        if url.endswith(".xml"):
            raise FetchError(url, 404, "HTTP 404")
        for fragment, name in ROUTES:
            if fragment in url:
                text = _text(name)
                # BSE pages 50 rows; the fixture is shorter, so page 1 is the last page.
                return text
        raise AssertionError(f"unexpected URL {url}")
    return fetch


# ---------- dates ----------

def test_parse_day_reads_every_exchange_format():
    assert parse_day("09-NOV-2026") == "2026-11-09"
    assert parse_day("14-Nov-2026 22:33:34") == "2026-11-14"
    assert parse_day("13/11/2026") == "2026-11-13"
    assert parse_day("2026-11-13T22:26:21.697") == "2026-11-13"
    assert parse_day("2026-11-12 18:21:23") == "2026-11-12"
    assert parse_day("soon") is None and parse_day(None) is None


def test_blocks_are_fixed_weeks_and_only_today_is_short_lived():
    blocks = date_blocks(7, NOW)
    assert window_start(7, NOW) == START
    assert blocks[0][0] == date(2026, 11, 2) and blocks[-1][1] == date(2026, 11, 15)
    assert all(first.weekday() == 0 for first, _last, _age in blocks)
    assert blocks[-1][2] == pytest.approx(0.1)
    # The week that closed on Sunday 8 Nov may be served from a copy fetched after it closed (~6.9 days ago).
    assert 6.5 < blocks[0][2] < 7.0
    days = day_ages(1, NOW)
    assert [d for d, _same, _age in days] == [date(2026, 11, 14), date(2026, 11, 15)]
    assert days[-1][2] == pytest.approx(0.1) and days[0][2] < 1


# ---------- NSE ----------

def test_nse_announcements_keep_only_money_events_with_their_pdf():
    rows = nse.parse_announcements(_text("nse_announcements.json"))
    items = {row["desc"]: nse.announcement_item(NSE_SOURCE, row) for row in rows}
    assert items["Buyback"]["class"] == "buyback_announcement"
    assert items["Public Announcement - Buyback of Shares"]["class"] == "buyback_public_announcement"
    assert items["Public Announcement - Buyback of Shares"]["event_type"] == "buyback"
    assert items["Public Announcement - Buyback of Shares"]["supported"] is True
    assert items["Post Buyback Public Announcement"]["class"] == "buyback_announcement"
    assert items["Open Offer"]["class"] == "acquisition" and items["Acquisition"]["class"] == "acquisition"
    assert items["Acquisition"]["supported"] is False
    for other in ("Allotment of Securities", "Outcome of Board Meeting", "Press Release",
                  "Copy of Newspaper Publication"):
        assert items[other] is None
    kept = items["Public Announcement - Buyback of Shares"]
    assert ITEM_KEYS <= set(kept)
    assert kept["documents"] == [kept["link"]] and kept["link"].endswith(".pdf")
    assert kept["published_iso"] == "2026-11-10" and kept["source"] == "nse_test"
    assert kept["company"] == next(r["sm_name"] for r in rows if r["desc"].startswith("Public Announcement"))


def test_nse_subject_rules_cover_ofs_and_allotment_wording():
    from tools.exchanges.common import classify_subject

    assert classify_subject("Offer for sale") == "ofs_notice"
    assert classify_subject("Announcement: Offer For Sale - Stock Exchange Mechanism") == "ofs_notice"
    assert classify_subject("Updates", "informed the Exchange about the Basis of Allotment") == "basis_of_allotment"
    assert classify_subject("Listing of Equity Shares") == "listing_notice"
    assert classify_subject("Delisting of Shares") is None
    assert classify_subject("Allotment of Securities") is None


def test_nse_listed_ipos_in_the_window_become_listing_notices():
    rows = _json("nse_ipo_past.json")
    items = nse.ipo_items(NSE_SOURCE, rows, listed=True, start=START)
    assert len(items) == 1
    assert items[0]["class"] == "listing_notice" and items[0]["published_iso"] == "2026-11-09"
    assert f"issue price {rows[0]['issuePrice']}" in items[0]["title"]
    assert nse.ipo_items(NSE_SOURCE, _json("nse_ipo_current.json"), listed=False, start=START) == []


def test_nse_deal_rows_become_records_with_printed_money():
    rows = nse.parse_deals(_text("nse_bulk_deals.json"))
    records = nse.deal_records(NSE_SOURCE, "bulk_deal", rows, "https://example.org/page", "t", START)
    assert len(records) == 5
    first = records[0]
    assert set(first) == RECORD_KEYS
    assert first["side"] == "sell" and first["quantity"] == rows[0]["BD_QTY_TRD"]
    assert first["price_inr"] == str(rows[0]["BD_TP_WATP"]) and first["value_inr"] is None
    assert first["trade_date"] == "2026-11-09" and first["category"] is None and first["mode"] is None
    assert records[1]["side"] == "buy"


def test_nse_archive_csv_and_api_agree_on_ids():
    csv_rows = nse.parse_deals_csv(_text("nse_block.csv"))
    assert len(csv_rows) == 4 and "mode" not in csv_rows[0]
    fields = {name: name for name in nse._CSV_FIELDS}
    from tools.exchanges.common import deal_record

    from_csv = deal_record(NSE_SOURCE, "block_deal", csv_rows[0], fields, "https://a", "t1")
    api_row = {"BD_DT_DATE": csv_rows[0]["date"], "BD_SYMBOL": csv_rows[0]["symbol"],
               "BD_SCRIP_NAME": csv_rows[0]["company"], "BD_CLIENT_NAME": csv_rows[0]["name"],
               "BD_BUY_SELL": csv_rows[0]["side"], "BD_QTY_TRD": int(csv_rows[0]["qty"]),
               "BD_TP_WATP": float(csv_rows[0]["price"]), "BD_REMARKS": None}
    from_api = deal_record(NSE_SOURCE, "block_deal", api_row, nse.NSE_DEAL_FIELDS, "https://b", "t2")
    assert from_csv["id"] == from_api["id"]
    trailing = {**csv_rows[0], "price": "39.50"}
    assert deal_record(NSE_SOURCE, "block_deal", trailing, fields, "https://a", "t")["id"] == \
        deal_record(NSE_SOURCE, "block_deal", {**api_row, "BD_TP_WATP": 39.5}, nse.NSE_DEAL_FIELDS, "https://b", "t")["id"]
    with pytest.raises(ValueError):
        nse.parse_deals_csv("a,b,c\n1,2,3\n")


def test_nse_xbrl_keeps_the_sale_and_skips_the_buy():
    filing = nse.parse_pit_xbrl(_text("nse_pit_xbrl.xml"))
    assert len(filing["disclosures"]) == 2 and filing["symbol"]
    records, skipped = nse.insider_records(NSE_SOURCE, filing, "https://example.org/x.html", "t")
    assert skipped == 1 and len(records) == 1
    sale = records[0]
    assert set(sale) == RECORD_KEYS
    assert sale["kind"] == "insider_sale" and sale["side"] == "sell" and sale["category"] == "director"
    assert sale["quantity"] == 20000 and sale["value_inr"] == "2858200" and sale["price_inr"] is None
    assert sale["trade_date"] == "2026-11-12" and sale["mode"] == "Market Sale"
    assert sale["row_ref"] == "XBRL context Disclosure2"


def test_nse_xbrl_with_entities_is_refused():
    with pytest.raises(ValueError):
        nse.parse_pit_xbrl('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')


# ---------- BSE ----------

def test_bse_announcements_and_attachment_links():
    rows = bse._table(_text("bse_announcements.json"))
    items = {row["SUBCATNAME"]: bse.announcement_item(BSE_SOURCE, row) for row in rows}
    assert items["Offer for Sale"]["class"] == "ofs_notice"
    assert items["Offer for Sale"]["event_type"] == "ofs_stock_exchange"
    assert items["Public Announcement-Buyback of Shares"]["class"] == "buyback_public_announcement"
    assert items["Closure of Buy Back"]["class"] == "buyback_announcement"
    assert items["Public Announcement-Open Offer"]["class"] == "acquisition"
    assert items["New Listing"]["class"] == "listing_notice"
    assert items["New Listing"]["documents"] == [] and "#" in items["New Listing"]["link"]
    live = next(row for row in rows if str(row["PDFFLAG"]) == "0")
    history = next(row for row in rows if str(row["PDFFLAG"]) == "1" and row["ATTACHMENTNAME"])
    assert "/AttachLive/" in bse.attachment_url(live) and "/AttachHis/" in bse.attachment_url(history)
    assert ITEM_KEYS <= set(items["Offer for Sale"])


def test_bse_issue_list_keeps_buybacks_and_open_offers_only():
    rows = bse._table(_text("bse_issues.json"))
    items = bse.issue_items(BSE_SOURCE, rows)
    flags = [row["IR_flag"].upper() for row in rows]
    assert len(items) == flags.count("BUYBACK") + flags.count("OTB")
    assert {item["class"] for item in items} == {"buyback_announcement", "acquisition"}
    assert all("DisplayIPO" in item["link"] for item in items)


def test_bse_deals_and_insider_sales():
    bulk = bse.deal_records(BSE_SOURCE, "bulk_deal", bse._table(_text("bse_bulk.json")), "https://p", "t", START)
    assert len(bulk) == 5 and {r["side"] for r in bulk} == {"buy", "sell"}
    assert all(r["trade_date"] == "2026-11-13" for r in bulk)
    assert bse.deal_records(BSE_SOURCE, "block_deal", bse._table(_text("bse_block.json")), "https://p", "t",
                            START) == []  # 6 Nov is before the window
    rows = bse._table(_text("bse_insider.json"))
    sales = [bse.insider_record(BSE_SOURCE, row, "t") for row in rows]
    kept = [sale for sale in sales if sale]
    assert rows[1]["ModeOfAquisation"] == "Inter-se-Transfer" and sales[1] is None  # no cash to the seller
    assert sales[2] is None  # the acquisition is not a sale
    assert [sale["category"] for sale in kept] == ["director"]
    assert kept[0]["value_inr"] == "2858200.00" and kept[0]["link"].startswith("https://www.bseindia.com/XBRLFILES/")
    assert set(kept[0]) == RECORD_KEYS


def test_bse_insider_never_copies_personal_fields():
    row = {**_json("bse_insider.json")["Table"][0], "Fld_PromoterAdd": "an address", "Fld_PromoterContact": "123",
           "Fld_PromoterPAN": "ABCDE1234F"}
    record = bse.insider_record(BSE_SOURCE, row, "t")
    assert not any(value in json.dumps(record) for value in ("an address", "ABCDE1234F"))


# ---------- read_all ----------

def test_read_all_on_recorded_responses(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCHANGE_SOURCES", "on")
    calls: list[str] = []
    result = exchanges.read_all(7, fetcher=_fake_fetcher(calls), outputs_dir=tmp_path, now=NOW)
    status = {s["id"]: s for s in result["sources"]}
    assert all(s["status"] == "ok" for s in status.values()), status
    assert status["nse_insider"]["records"] == 1
    classes = {item["class"] for item in result["items"]}
    assert {"buyback_announcement", "acquisition", "listing_notice"} <= classes
    assert len({item["link"] for item in result["items"]}) == len(result["items"])
    deals = result["records"]["deals"]
    assert len({r["id"] for r in deals}) == len(deals)
    assert {r["exchange"] for r in deals} == {"NSE", "BSE"}
    saved = json.loads((tmp_path / "signals" / "deals.json").read_text(encoding="utf-8"))
    assert set(saved) == {"refreshed_at", "source_status", "records"}
    assert set(saved["source_status"]) == {"nse_bulk_deals", "nse_block_deals", "nse_deals_archive",
                                           "bse_bulk_deals", "bse_block_deals"}
    assert len(saved["records"]) == len(deals)
    insider = json.loads((tmp_path / "signals" / "insider.json").read_text(encoding="utf-8"))
    assert {r["kind"] for r in insider["records"]} == {"insider_sale"}
    # The director's sale is filed on both exchanges: it is kept once, as the NSE record.
    assert [r["exchange"] for r in insider["records"]] == ["NSE"]
    assert status["bse_insider"]["records"] == 0 and "also filed on NSE" in status["bse_insider"]["note"]


def test_insider_xbrl_links_off_the_archive_host_are_not_fetched(monkeypatch):
    listing = _json("nse_pit_list.json")
    listing["data"][0]["xmlFileName"] = "http://169.254.169.254/latest/x.xml"
    calls: list[str] = []
    good = _fake_fetcher(calls)

    def fetch(url, age):
        return json.dumps(listing) if "corporates-pit-gg" in url else good(url, age)
    ctx = exchanges.Context(fetch, lambda url, age: True, 7, NOW)
    _items, records, _notes = nse.read_insider(NSE_SOURCE, ctx)
    assert records == [] and not any("169.254" in url for url in calls)


def test_a_403_stops_the_host_and_keeps_earlier_records(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCHANGE_SOURCES", "on")
    exchanges.read_all(7, fetcher=_fake_fetcher([]), outputs_dir=tmp_path, now=NOW)
    before = json.loads((tmp_path / "signals" / "deals.json").read_text(encoding="utf-8"))["records"]
    calls: list[str] = []
    result = exchanges.read_all(7, fetcher=_fake_fetcher(calls, blocked_hosts=("www.nseindia.in",)),
                                outputs_dir=tmp_path, now=NOW)
    status = {s["id"]: s for s in result["sources"]}
    for source_id in ("nse_announcements", "nse_ipo", "nse_bulk_deals", "nse_block_deals", "nse_insider"):
        assert status[source_id]["status"] == "blocked" and status[source_id]["http_status"] == 403
    assert status["nse_deals_archive"]["status"] == "ok" and status["bse_bulk_deals"]["status"] == "ok"
    assert sum(1 for url in calls if "www.nseindia.in" in url) == 1  # one request, then the host is left alone
    after = json.loads((tmp_path / "signals" / "deals.json").read_text(encoding="utf-8"))
    assert after["source_status"]["nse_bulk_deals"]["status"] == "blocked"
    assert {r["id"] for r in before} <= {r["id"] for r in after["records"]}


def test_switch_off_makes_no_request(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCHANGE_SOURCES", "off")
    calls: list[str] = []
    result = exchanges.read_all(7, fetcher=_fake_fetcher(calls), outputs_dir=tmp_path, now=NOW)
    assert calls == [] and result["items"] == [] and result["records"] == {"deals": [], "insider": []}
    assert {s["status"] for s in result["sources"]} == {"disabled"}
    assert json.loads((tmp_path / "signals" / "insider.json").read_text())["source_status"]["nse_insider"][
        "status"] == "disabled"


def test_a_page_that_is_not_json_fails_only_its_source(monkeypatch):
    monkeypatch.setenv("EXCHANGE_SOURCES", "on")
    good = _fake_fetcher([])

    def fetch(url, age):
        return "<html>challenge</html>" if "ipo-current-issue" in url else good(url, age)
    result = exchanges.read_all(7, fetcher=fetch, outputs_dir=None, now=NOW)
    status = {s["id"]: s["status"] for s in result["sources"]}
    assert status["nse_ipo"] == "failed" and status["nse_announcements"] == "ok"


def test_signal_events_group_sales():
    records = bse.deal_records(BSE_SOURCE, "bulk_deal", bse._table(_text("bse_bulk.json")), "https://p", "t", START)
    events = exchanges.signal_events(records)
    sells = [r for r in records if r["side"] == "sell"]
    assert sum(len(e["records"]) for e in events) == len(sells)
    assert all(e["event_type"] == "block_deal" and e["records_file"] == "outputs/signals/deals.json"
               and e["documents"] == [] for e in events)
    assert len({e["event_id"] for e in events}) == len(events)


# ---------- client ----------

class _Clock:
    def __init__(self):
        self.now, self.slept = 100.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_client_visits_home_once_waits_between_requests_and_latches_403(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/blocked":
            return httpx.Response(403, text="denied")
        return httpx.Response(200, text="{}", headers={"set-cookie": "site=1; Path=/"} if request.url.path == "/" else {})
    clock = _Clock()
    client = ExchangeClient(transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock)
    client.get_text("https://www.bseindia.com/a", 1)
    client.get_text("https://www.bseindia.com/a", 1)  # cached: no request
    client.get_text("https://www.bseindia.com/b", 1)
    assert [r.url.path for r in seen] == ["/", "/a", "/b"]
    assert all(r.headers["user-agent"] == USER_AGENT and "FinSight" in USER_AGENT for r in seen)
    assert not any(key.startswith("sec-") for r in seen for key in r.headers)
    assert seen[1].headers.get("cookie") == "site=1" and seen[1].headers["referer"] == "https://www.bseindia.com/"
    assert clock.slept and all(s == pytest.approx(2.0) for s in clock.slept)
    with pytest.raises(FetchError) as first:
        client.get_text("https://www.bseindia.com/blocked", 1)
    assert first.value.status == 403
    with pytest.raises(FetchError) as again:
        client.get_text("https://www.bseindia.com/c", 1)
    assert again.value.status == 403
    assert [r.url.path for r in seen][-1] == "/blocked"  # nothing sent after the block


def test_client_blocked_home_page_blocks_the_api_host(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    seen: list[str] = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(403 if request.url.path == "/" else 200, text="[]")
    clock = _Clock()
    client = ExchangeClient(transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock)
    for _ in range(2):
        with pytest.raises(FetchError):
            client.get_text("https://www.nseindia.in/api/x", 1)
    assert seen == ["https://www.nseindia.in/"]


def test_a_deals_answer_at_nse_row_cap_is_reported_as_possibly_cut(monkeypatch):
    from config.exchanges import NSE_DEALS_ROW_CAP

    row = _json("nse_bulk_deals.json")["data"][0]
    full = json.dumps({"data": [{**row, "BD_QTY_TRD": row["BD_QTY_TRD"] + n} for n in range(NSE_DEALS_ROW_CAP)]})
    ctx = exchanges.Context(lambda url, age: full, lambda url, age: True, 1, datetime(2026, 11, 9, 12, tzinfo=timezone.utc))
    _items, records, notes = nse.read_bulk(NSE_SOURCE, ctx)
    assert len({record["id"] for record in records}) == NSE_DEALS_ROW_CAP
    assert any("may be cut" in note for note in notes)
