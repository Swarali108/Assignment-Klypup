"""Signals v2 in tools/discover.py (tier 1, data integrity): exchange notices attach to the right
event and never edit a hand-made one; structured records become events and feed items; SEBI's
real draft-offer list becomes watchlist items, never events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools import discover

NOW = datetime(2026, 11, 15, 8, 0, tzinfo=timezone.utc)
PDF = "https://nsearchives.example.org/content/"
FIXTURE = Path(__file__).parent / "fixtures" / "sebi" / "drhp_list.html"


def _never_ask(items):
    raise AssertionError("no model call expected")


def _no_fetch(url, max_age_days):
    raise AssertionError(f"no SEBI fetch expected: {url}")


def _exchange(*items: dict, status: str = "ok"):
    """A stand-in for tools.exchanges.read_all."""
    return lambda since_days: {"sources": [{"id": "nse_announcements", "name": "NSE · Announcements",
                                            "status": status, "items": len(items), "reason": ""}],
                               "items": list(items), "records": {}}


def _notice(company: str, cls: str, day: str, name: str) -> dict:
    return {"source": "nse_announcements", "source_name": "NSE · Announcements", "title": f"{company} - {name}",
            "published": day, "link": f"https://www.nseindia.example/{name}", "company": company, "class": cls,
            "documents": [f"{PDF}{name}.pdf"]}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_an_allotment_notice_attaches_to_the_existing_ipo_event_of_the_same_company(tmp_path):
    events = tmp_path / "events"
    existing = {"event_id": "example_widgets_limited_ipo_202610", "event_type": "ipo", "company": "Example Widgets Limited",
                "documents": [{"url": PDF + "rhp.pdf", "doc_type": "rhp"}],
                "discovery": {"sources": ["sebi_rhp"], "first_seen": "x", "last_seen": "x",
                              "items": [{"title": "t", "link": "l", "published": "Oct 30, 2026", "class": "ipo_rhp"}]}}
    _write(events / "auto" / "example_widgets_limited_ipo_202610.json", existing)
    reader = _exchange(_notice("Example Widgets Ltd", "ipo_allotment", "Nov 06, 2026", "allotment"),
                       _notice("Other Gadgets Ltd", "ipo_listing", "Nov 07, 2026", "listing"))
    report = discover.refresh(30, events, tmp_path / "outputs", _no_fetch, _never_ask, NOW, (), exchange_reader=reader)
    written = json.loads((events / "auto" / "example_widgets_limited_ipo_202610.json").read_text(encoding="utf-8"))
    assert [d["doc_type"] for d in written["documents"]] == ["rhp", "announcement"]
    assert written["documents"][1]["url"] == PDF + "allotment.pdf"
    assert "nse_announcements" in written["discovery"]["sources"] and len(written["discovery"]["items"]) == 2
    other = next(e for e in report["events"] if e["company"] == "Other Gadgets Ltd")
    assert not other["processable"] and other["missing"].startswith("waiting for")
    assert {s["id"]: s["status"] for s in report["sources"]} == {"nse_announcements": "ok"}


def test_a_notice_for_a_hand_made_event_is_reported_as_covered_and_the_file_is_not_edited(tmp_path):
    events = tmp_path / "events"
    manual = {"event_id": "hand_made", "event_type": "ipo", "company": "Example Widgets Limited",
              "documents": [{"url": PDF + "prospectus.pdf", "doc_type": "prospectus"}]}
    _write(events / "hand_made.json", manual)
    before = (events / "hand_made.json").read_text(encoding="utf-8")
    reader = _exchange(_notice("Example Widgets Limited", "ipo_listing", "Nov 07, 2026", "listing"))
    report = discover.refresh(30, events, tmp_path / "outputs", _no_fetch, _never_ask, NOW, (), exchange_reader=reader)
    assert report["events"][0]["status"] == "covered by a hand-made event"
    assert report["events"][0]["covered_by"] == "hand_made"
    assert (events / "hand_made.json").read_text(encoding="utf-8") == before


def test_a_crashing_exchange_reader_is_one_failed_source(tmp_path):
    def boom(since_days):
        raise RuntimeError("HTTP 403")

    report = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _no_fetch, _never_ask, NOW, (),
                              exchange_reader=boom)
    assert report["sources"][0]["status"] == "failed" and "403" in report["sources"][0]["reason"]


def test_structured_records_become_an_event_file_and_one_feed_item(tmp_path):
    record = {"id": "r1", "kind": "block_deal", "exchange": "NSE", "symbol": "EXW", "company": "Example Widgets Limited",
              "trade_date": "2026-11-12", "name_as_printed": "A Seller", "category": None, "side": "sell",
              "quantity": 1000, "price_inr": "10.00", "value_inr": None, "mode": None,
              "link": "https://www.nseindia.example/deals", "row_ref": "row 3", "fetched_at": "x"}
    old = {**record, "id": "r0", "trade_date": "2026-01-02"}
    _write(tmp_path / "outputs" / "signals" / "deals.json", {"refreshed_at": "x", "source_status": {}, "records": [record, old]})
    seen = []

    def group(records):
        seen.extend(r["id"] for r in records)
        return [{"event_id": "example_widgets_limited_block_deal_2026w46", "event_type": "block_deal",
                 "company": "Example Widgets Limited", "documents": [], "records": [r["id"] for r in records],
                 "records_file": "outputs/signals/block_deal.json"}]  # the grouping's guess; the real file is deals.json

    report = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _no_fetch, _never_ask, NOW, (),
                              group_records=group)
    assert seen == ["r1"]  # the record outside the window is left out
    event = next(e for e in report["events"] if e.get("structured"))
    assert event["status"] == "created" and event["records"] == ["r1"] and event["processable"]
    written = json.loads((tmp_path / "events" / "auto" / f"{event['event_id']}.json").read_text(encoding="utf-8"))
    assert written["records"] == ["r1"] and written["documents"] == []
    assert written["records_file"] == "outputs/signals/deals.json"  # the file the records were read from
    item = next(i for i in report["items"] if i["classified_by"] == "structured")
    assert item["exchange"] == "NSE" and item["event_id"] == event["event_id"] and item["published_iso"] == "2026-11-12"
    assert item["link"] == record["link"]
    again = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _no_fetch, _never_ask, NOW, (),
                             group_records=group)
    assert next(e for e in again["events"] if e.get("structured"))["status"] == "unchanged"
    # A new record changes the fingerprint, so the event is processed again.
    assert discover.event_hash(event) != discover.event_hash({**event, "records": ["r1", "r2"]})


def test_sebi_draft_offer_documents_are_watchlist_items_not_events(tmp_path):
    """A real SEBI 'Draft Offer Documents filed with SEBI' page, saved from a live fetch on 2026-11-15."""
    from config.signals import WATCH_SOURCES

    page = FIXTURE.read_text(encoding="utf-8", errors="replace")
    source = {**WATCH_SOURCES[0], "url": "drhp-list"}
    report = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", lambda url, age: page, _never_ask, NOW,
                              (source,))
    assert len(report["items"]) >= 10
    assert {item["class"] for item in report["items"]} == {"ipo_coming"}
    assert not any(item["supported"] for item in report["items"]) and report["events"] == []


def test_a_type_corrected_from_the_first_page_survives_the_next_refresh(tmp_path):
    """A buyback "PA" file whose first page said LETTER OF OFFER keeps the corrected type when discovery runs again."""
    url = "https://www.sebi.gov.in/sebi_data/commondocs/nov-2026/Example%20PA_p.pdf"
    previous = {"documents": [{"url": url, "doc_type": "letter_of_offer", "from_class": "buyback_public_announcement",
                               "doc_type_from": "its first page: LETTER OF OFFER"}]}
    fresh = [{"url": url, "doc_type": "public_announcement", "from_class": "buyback_public_announcement"}]
    kept = discover.keep_corrections(fresh, previous)
    assert kept[0]["doc_type"] == "letter_of_offer" and kept[0]["doc_type_from"].startswith("its first page")
    assert discover.keep_corrections(fresh, None) == fresh


def test_an_aged_out_prospectus_is_kept_when_only_a_notice_is_in_the_window(tmp_path):
    """Same event id, prospectus no longer in the window: the event keeps it and gains the notice."""
    events = tmp_path / "events"
    existing = {"event_id": "example_widgets_limited_ipo_202611", "event_type": "ipo", "company": "Example Widgets Limited",
                "documents": [{"url": PDF + "prospectus.pdf", "doc_type": "prospectus"}],
                "discovery": {"sources": ["sebi_prospectus"], "first_seen": "x", "last_seen": "x",
                              "items": [{"title": "t", "link": "l", "published": "Nov 01, 2026", "class": "ipo_prospectus"}]}}
    _write(events / "auto" / "example_widgets_limited_ipo_202611.json", existing)
    reader = _exchange(_notice("Example Widgets Limited", "ipo_allotment", "Nov 08, 2026", "allotment"))
    report = discover.refresh(10, events, tmp_path / "outputs", _no_fetch, _never_ask, NOW, (), exchange_reader=reader)
    written = json.loads((events / "auto" / "example_widgets_limited_ipo_202611.json").read_text(encoding="utf-8"))
    assert [d["doc_type"] for d in written["documents"]] == ["prospectus", "announcement"]
    assert report["events"][0]["processable"]


def test_a_notice_is_kept_when_its_source_is_blocked_on_the_next_run(tmp_path):
    """Run 1 attaches an exchange notice; run 2 has the exchange blocked: the notice stays and nothing changes."""
    from tests.test_discovery import _ipo_pages, _fetcher  # the same synthetic SEBI pages

    sources, pages = _ipo_pages()
    events, outputs = tmp_path / "events", tmp_path / "outputs"
    first = discover.refresh(30, events, outputs, _fetcher(pages), _never_ask, NOW, sources,
                             exchange_reader=_exchange(_notice("Example Widgets Limited", "ipo_listing", "Nov 09, 2026",
                                                               "listing-nse")))
    event_id = first["events"][0]["event_id"]
    urls = lambda: [d["url"] for d in json.loads((events / "auto" / f"{event_id}.json").read_text(encoding="utf-8"))["documents"]]
    assert PDF + "listing-nse.pdf" in urls()
    second = discover.refresh(30, events, outputs, _fetcher(pages), _never_ask, NOW, sources,
                              exchange_reader=_exchange(status="blocked"))
    assert PDF + "listing-nse.pdf" in urls() and second["events"][0]["status"] == "unchanged"


def test_exchange_files_are_fetched_at_least_two_seconds_apart(monkeypatch):
    """The default download path keeps the exchanges' 2 s rule; other hosts are not slowed."""
    from tools import fetch

    sleeps, clock = [], [100.0]
    monkeypatch.setattr(fetch.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fetch.time, "sleep", lambda s: (sleeps.append(round(s, 3)), clock.__setitem__(0, clock[0] + s)))
    fetch._LAST_HIT.clear()
    fetch._pace("https://nsearchives.nseindia.in/corporate/a.pdf")
    clock[0] += 0.5
    fetch._pace("https://nsearchives.nseindia.in/corporate/b.pdf")
    fetch._pace("https://www.sebi.gov.in/x.pdf")
    assert sleeps == [1.5]


def test_a_structured_event_with_only_context_rows_is_an_empty_list_not_a_failure(tmp_path):
    (tmp_path / "ranked.json").write_text(json.dumps({"callable": [], "entities": [], "context": [{"id": "p1"}]}),
                                          encoding="utf-8")
    assert discover.outcome_problem(tmp_path) == ""
    (tmp_path / "ranked.json").write_text(json.dumps({"callable": [], "entities": [], "context": []}), encoding="utf-8")
    assert discover.outcome_problem(tmp_path)


def test_an_exchange_row_is_evidence_with_no_pdf_page():
    """A deal row has no PDF: its evidence links to the exchange page and shows the row, never '.pdf#page=None'."""
    from api import views

    ref = {"source_url": "https://www.nseindia.in/report-detail/display-bulk-and-block-deals", "pdf_index": None,
           "printed_page": "06-NOV-2026 · EXW · A SELLER · SELL · 100", "quote": "NSE | EXW | A SELLER | SELL | 100 shares"}
    out = views.evidence_ref(ref, {})
    assert out["pdf_index"] is None and out["cached"] is False and out["image_url"] is None
    assert out["url"] == ref["source_url"] and "page=None" not in str(out) and out["doc_label"] == "Exchange record"
