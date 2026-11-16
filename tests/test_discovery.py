"""tools/discover.py with no network: synthetic SEBI pages, a fake fetcher, a fake model and a fake runner."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from tools import discover
from tools.fetch import FetchError

NOW = datetime(2026, 11, 15, 8, 0, tzinfo=timezone.utc)
BASE = "https://www.sebi.gov.in/filings/public-issues/nov-2026/"
PDF = "https://www.sebi.gov.in/sebi_data/attachdocs/nov-2026/"


def _source(source_id: str, url: str, default=None, details=True, enabled=True, kind="sebi_list") -> dict:
    return {"id": source_id, "name": f"Test {source_id}", "kind": kind, "url": url, "enabled": enabled,
            "default_class": default, "details": details, "terms_url": "https://example.org/terms", "reason": "test"}


def _row(day: str, link: str, title: str, nested: str = "") -> str:
    extra = f"<br><a href='{nested}' style=color:#000000>nested</a>" if nested else ""
    return (f'<tr><td>{day}</td><td><a href="{link}" target="_blank" title="{title} {extra}" class="points"> '
            f"{title} {extra}</a></td></tr>")


def _list(*rows: str) -> str:
    return "<table><tr><th>Date</th><th>Title</th></tr>" + "".join(rows) + "</table>"


def _detail(*pdfs: str) -> str:
    return "<html><body>Nov 10, 2026 " + " ".join(f"<iframe src='../web/?file={pdf}'></iframe>" for pdf in pdfs) + "</body></html>"


def _fetcher(pages: dict):
    def fetch(url: str, max_age_days: float) -> str:
        page = pages[url]
        if isinstance(page, Exception):
            raise page
        return page
    return fetch


def _never_ask(items: list[dict]) -> None:
    raise AssertionError(f"model asked about {[item['title'] for item in items]}")


@pytest.mark.parametrize(("title", "expected"), [
    ("Example Widgets Limited - RHP", "ipo_rhp"),
    ("Example Widgets Limited– Red Herring Prospectus", "ipo_rhp"),
    ("Example Widgets Ltd.- Prospectus", "ipo_prospectus"),
    ("Example Widgets Limited - Addendum to RHP and Price Band", "price_band_ad"),
    ("Example Widgets Limited - Basis of Allotment", "basis_of_allotment"),
    ("Example Widgets Limited - Listing and commencement of trading", "listing_notice"),
    ("Example Widgets Limited - Letter of Offer for Buyback", "buyback_letter_of_offer"),
    ("Example Widgets Limited - Public Announcement for Buy-back", "buyback_public_announcement"),
    ("Offer for Sale through Stock Exchange mechanism - notice", "ofs_notice"),
    ("Example Widgets Limited - Abridged Prospectus", "other"),
    ("Example Widgets Limited - DRHP", "other"),
    ("Example Widgets Limited - Addendum to RHP", "other"),
    ("Example Widgets Limited - Open Offer", "other"),
    ("Example Widgets Limited - Delisting and trading", "other"),
])
def test_title_rules_classify_sample_titles(title, expected):
    found = discover.classify_title(title)
    assert found is not None
    assert (found[0] or "other") == expected


def test_unmatched_title_is_left_for_the_model_and_bad_answers_become_other(monkeypatch):
    assert discover.classify_title("Example Widgets Limited - Board meeting outcome") is None
    item = discover.new_item(_source("s", "u"), "Example Widgets Limited - Board meeting outcome", "Nov 10, 2026", "l1")
    monkeypatch.setattr(discover, "llm_call", lambda **kwargs: {"item_class": "made_up", "label": "board meeting"})
    discover.classify_with_model([item])
    assert item["class"] == "other" and item["label"] == "board meeting" and item["classified_by"] == "model"


def test_nested_abridged_link_does_not_become_the_title():
    page = _list(_row("Nov 12, 2026", BASE + "example-widgets-rhp_1.html", "Example Widgets Limited– RHP",
                      nested=PDF + "abridged.pdf"))
    items = discover.parse_sebi_list(page, _source("s", "u"))
    assert [item["title"] for item in items] == ["Example Widgets Limited– RHP"]
    assert items[0]["company"] == "Example Widgets Limited" and items[0]["published_iso"] == "2026-11-12"


def _ipo_pages() -> tuple[tuple, dict]:
    sources = (_source("rhp", "list-rhp"), _source("final", "list-final"))
    pages = {
        "list-rhp": _list(_row("Oct 20, 2026", BASE + "w-rhp_1.html", "Example Widgets Ltd. - RHP"),
                          _row("Oct 25, 2026", BASE + "w-band_2.html", "Example Widgets Limited - Addendum to RHP and Price Band")),
        "list-final": _list(_row("Nov 02, 2026", BASE + "w-prospectus_3.html", "Example Widgets Limited - Prospectus"),
                            _row("Nov 06, 2026", BASE + "w-allot_4.html", "Example Widgets Limited - Basis of Allotment"),
                            _row("Nov 08, 2026", BASE + "w-listing_5.html",
                                 "Example Widgets Limited - Listing and commencement of trading")),
        BASE + "w-rhp_1.html": _detail(PDF + "rhp.pdf"),
        BASE + "w-band_2.html": _detail(PDF + "band.pdf"),
        BASE + "w-prospectus_3.html": _detail(PDF + "prospectus.pdf"),
        BASE + "w-allot_4.html": _detail(PDF + "allotment.pdf"),
        BASE + "w-listing_5.html": _detail(PDF + "listing.pdf"),
    }
    return sources, pages


def test_rhp_allotment_and_listing_group_into_one_event_and_the_prospectus_supersedes_the_rhp(tmp_path):
    sources, pages = _ipo_pages()
    report = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    assert len(report["events"]) == 1
    event = report["events"][0]
    assert event["event_id"] == "example_widgets_limited_ipo_202610" and event["status"] == "created"
    assert [document["doc_type"] for document in event["documents"]] == ["prospectus", "announcement", "announcement",
                                                                         "announcement"]
    assert PDF + "rhp.pdf" not in [document["url"] for document in event["documents"]]
    written = json.loads((tmp_path / "events" / "auto" / f"{event['event_id']}.json").read_text(encoding="utf-8"))
    assert written["discovery"]["sources"] == ["final", "rhp"] and len(written["discovery"]["items"]) == 5
    assert json.loads((tmp_path / "outputs" / "discovery.json").read_text(encoding="utf-8"))["counts"]["events"] == 1


def test_items_further_apart_than_the_window_are_separate_events(tmp_path):
    sources = (_source("final", "list-final"),)
    pages = {"list-final": _list(_row("Nov 02, 2026", BASE + "a_1.html", "Example Widgets Limited - Prospectus"),
                                 _row("Jul 01, 2026", BASE + "b_2.html", "Example Widgets Limited - Prospectus")),
             BASE + "a_1.html": _detail(PDF + "a.pdf"), BASE + "b_2.html": _detail(PDF + "b.pdf")}
    report = discover.refresh(200, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    assert sorted(event["event_id"] for event in report["events"]) == ["example_widgets_limited_ipo_202607",
                                                                       "example_widgets_limited_ipo_202611"]


def test_the_same_link_and_the_same_document_are_kept_once(tmp_path):
    sources = (_source("one", "list-1"), _source("two", "list-2"))
    same_row = _row("Nov 02, 2026", BASE + "w_1.html", "Example Widgets Limited - Prospectus")
    pages = {"list-1": _list(same_row), "list-2": _list(same_row, _row("Nov 03, 2026", BASE + "w_2.html",
                                                                         "Example Widgets Limited - Prospectus")),
             BASE + "w_1.html": _detail(PDF + "p.pdf"), BASE + "w_2.html": _detail(PDF + "p.pdf")}
    report = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    assert len(report["items"]) == 2
    assert [document["url"] for document in report["events"][0]["documents"]] == [PDF + "p.pdf"]


def test_buyback_class_comes_from_the_file_names_on_its_page(tmp_path):
    sources = (_source("bb", "list-bb", default="by_documents"),)
    link = "https://www.sebi.gov.in/filings/buybacks/nov-2026/example-widgets_9.html"
    pages = {"list-bb": _list(_row("Nov 06, 2026", link, "Example Widgets Limited")),
             link: _detail(PDF + "Example%20Widgets%20PA_p.pdf", PDF + "Example%20Widgets%20LOF_p.pdf",
                           PDF + "Example%20Widgets%20DLOF_p.pdf")}
    report = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    item = report["items"][0]
    assert item["class"] == "buyback_letter_of_offer" and item["classified_by"] == "documents"
    event = report["events"][0]
    # The letter of offer supersedes the public announcement; the draft letter of offer is not a document.
    assert [d["doc_type"] for d in event["documents"]] == ["letter_of_offer"] and event["processable"]
    assert event["missing"] == ""


def test_a_failed_or_blocked_source_is_recorded_not_raised(tmp_path):
    sources = (_source("down", "list-down"), _source("blocked", "list-blocked"), _source("off", "x", enabled=False),
               _source("ok", "list-ok"))
    pages = {"list-down": OSError("connection reset"),
             "list-blocked": FetchError("list-blocked", 403, "HTTP 403 for list-blocked"),
             "list-ok": _list()}
    report = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    statuses = {source["id"]: source["status"] for source in report["sources"]}
    assert statuses == {"down": "failed", "blocked": "blocked", "off": "disabled", "ok": "ok"}
    assert "connection reset" in next(s["reason"] for s in report["sources"] if s["id"] == "down")
    assert report["counts"]["sources_failed"] == ["down", "blocked"]


def test_auto_events_never_overwrite_hand_made_ones(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    manual = {"event_id": "hand_made", "event_type": "ipo", "company": "Example Widgets Limited",
              "documents": [{"url": PDF + "prospectus.pdf", "doc_type": "prospectus"}]}
    manual_path = events_dir / "hand_made.json"
    manual_path.write_text(json.dumps(manual), encoding="utf-8")
    before = manual_path.read_text(encoding="utf-8")
    sources, pages = _ipo_pages()
    report = discover.refresh(30, events_dir, tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    event = report["events"][0]
    assert event["status"] == "covered by a hand-made event" and event["covered_by"] == "hand_made"
    assert not (events_dir / "auto").exists() or not list((events_dir / "auto").glob("*.json"))
    assert manual_path.read_text(encoding="utf-8") == before


def test_an_unchanged_event_is_not_rewritten(tmp_path):
    sources, pages = _ipo_pages()
    discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    again = discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)
    assert again["events"][0]["status"] == "unchanged"


def _report(n: int) -> dict:
    return {"events": [{"event_id": f"example_{i}_ipo_2026{i:02d}", "event_type": "ipo", "processable": True,
                        "status": "created", "file": f"events/auto/example_{i}.json",
                        "documents": [{"url": f"{PDF}{i}.pdf", "doc_type": "prospectus"}]} for i in range(1, n + 1)]}


def test_the_cost_cap_stops_new_runs(tmp_path):
    ran = []

    def runner(path, event_id):
        ran.append(event_id)
        return {"status": "ok", "reason": "", "cost_usd": 0.6, "seconds": 1.0}

    result = discover.process_events(_report(4), limit=4, max_cost=1.0, outputs_dir=tmp_path, runner=runner)
    statuses = [entry["status"] for entry in result["processed"]]
    assert statuses == ["ok", "ok", "skipped", "skipped"] and len(ran) == 2
    assert "cost cap" in result["processed"][2]["reason"] and result["spent_usd"] == pytest.approx(1.2)
    log = json.loads((tmp_path / "discovery_log.json").read_text(encoding="utf-8"))["entries"]
    assert len(log) == 4


def test_a_failing_run_is_logged_and_the_loop_continues(tmp_path):
    def runner(path, event_id):
        if event_id.startswith("example_2"):
            raise RuntimeError("pdf would not open")
        return {"status": "ok", "reason": "", "cost_usd": 0.01, "seconds": 1.0}

    result = discover.process_events(_report(3), limit=3, max_cost=1.0, outputs_dir=tmp_path, runner=runner)
    by_id = {entry["event_id"]: entry for entry in result["processed"]}
    assert by_id["example_2_ipo_202602"]["status"] == "failed"
    assert "pdf would not open" in by_id["example_2_ipo_202602"]["reason"]
    assert sum(entry["status"] == "ok" for entry in result["processed"]) == 2


def test_a_processed_event_is_not_processed_again_until_its_documents_change(tmp_path):
    runner = lambda path, event_id: {"status": "ok", "reason": "", "cost_usd": 0.0, "seconds": 1.0}
    discover.process_events(_report(1), 5, 1.0, tmp_path, runner)
    assert discover.candidates(_report(1), tmp_path) == []
    changed = _report(1)
    changed["events"][0]["documents"].append({"url": PDF + "new.pdf", "doc_type": "announcement"})
    assert len(discover.candidates(changed, tmp_path)) == 1


def test_a_run_past_its_timeout_is_stopped_with_its_workers(tmp_path):
    import sys
    import time

    worker = "import time; time.sleep(30)"
    parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {worker!r}]); time.sleep(30)"
    started = time.perf_counter()
    result = discover.run_event(tmp_path / "x.json", "timeout_case", timeout_s=2,
                                command=[sys.executable, "-c", parent])
    assert result["status"] == "failed" and "timed out after 2 s" in result["reason"]
    assert time.perf_counter() - started < 15



def _buyback_report(tmp_path, files: tuple[str, ...]) -> dict:
    sources = (_source("bb", "list-bb", default="by_documents"),)
    link = "https://www.sebi.gov.in/filings/buybacks/nov-2026/example-widgets_9.html"
    pages = {"list-bb": _list(_row("Nov 06, 2026", link, "Example Widgets Limited")),
             link: _detail(*(PDF + name for name in files))}
    return discover.refresh(30, tmp_path / "events", tmp_path / "outputs", _fetcher(pages), _never_ask, NOW, sources)


def test_a_buyback_with_only_its_public_announcement_is_processable_on_condition(tmp_path):
    event = _buyback_report(tmp_path, ("Example%20Widgets%20PA_p.pdf",))["events"][0]
    assert event["processable"] and "public announcement" in event["missing"]
    assert discover.stand_in_sections(event) == ("buyback_terms", "promoter_intention")


def test_the_announcement_is_processed_only_when_check_finds_its_sections(tmp_path):
    report = _buyback_report(tmp_path, ("Example%20Widgets%20PA_p.pdf",))
    ran = []
    runner = lambda path, event_id: ran.append(event_id) or {"status": "ok", "reason": "", "cost_usd": 0.01}
    lacking = discover.process_events(report, 5, 1.0, tmp_path / "outputs", runner,
                                      checker=lambda path, event_id: (["buyback_terms"], ""))
    entry = lacking["processed"][0]
    assert entry["status"] == "waiting" and "promoter_intention" in entry["reason"] and not ran
    complete = discover.process_events(report, 5, 1.0, tmp_path / "outputs", runner,
                                       checker=lambda path, event_id: (["buyback_terms", "promoter_intention"], ""))
    assert complete["processed"][0]["status"] == "ok" and complete["processed"][0]["from"] == "public announcement"
    assert len(ran) == 1


def test_a_mislabelled_announcement_whose_first_page_is_a_letter_of_offer_is_corrected(tmp_path):
    report = _buyback_report(tmp_path, ("Example%20Widgets%20PA_p.pdf",))
    ran = []
    runner = lambda path, event_id: ran.append(event_id) or {"status": "ok", "reason": "", "cost_usd": 0.0}
    never_checked = lambda path, event_id: (_ for _ in ()).throw(AssertionError("no check needed"))
    reader = lambda url: ["LETTER OF OFFER THIS DOCUMENT IS IMPORTANT. Buyback of equity shares of Example Widgets Limited"]
    result = discover.process_events(report, 5, 1.0, tmp_path / "outputs", runner, checker=never_checked, reader=reader)
    assert result["processed"][0]["status"] == "ok" and len(ran) == 1
    assert report["events"][0]["documents"][0]["doc_type"] == "letter_of_offer"
    assert "first page" in report["events"][0]["documents"][0]["doc_type_from"]


def test_the_viewer_file_is_the_main_document_of_an_item_page():
    page = ("<a href='https://www.sebi.gov.in/sebi_data/commondocs/nov-2026/Example_DA_p.pdf'>abridged</a> Nov 12, 2026 "
            "<iframe src='../../../web/?file=https://www.sebi.gov.in/sebi_data/attachdocs/nov-2026/1794.PDF'></iframe>")
    detail = discover.parse_sebi_detail(page)
    assert detail["documents"][0].endswith("1794.PDF") and len(detail["documents"]) == 2
