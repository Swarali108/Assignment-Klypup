"""ui/dashboard_data.py: counts, dates, notifications and the search index. No network."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from config.ranking import NEW_SIGNAL_DAYS
from ui import dashboard_data as data

WEB = Path(__file__).resolve().parents[1] / "ui" / "web"


def _doc(url: str = "https://example.org/a.pdf"):
    return SimpleNamespace(model_dump=lambda: {"url": url, "doc_type": "rhp", "note": None})


def _entry(pid: str, days: int | None, confidence: str = "medium", status: str = "in_hand") -> dict:
    return {"person_id": pid, "name_as_printed": pid.upper(), "role_as_printed": None, "holder_type": "person",
            "confidence": confidence, "timing_display_status": status, "amount_display": "₹1 crore",
            "trigger": None if days is None else {"days_since": days}}


def _event(event_id: str, event_type: str, people: dict, callable_people: list, processed: bool = True, **extra) -> dict:
    spec = SimpleNamespace(event_id=event_id, event_type=event_type, company=f"{event_id} Ltd", documents=[_doc()])
    out = {"people": people, "ranked": {"callable": callable_people, "entities": []}, "extract": extra.get("extract"),
           "briefs": extra.get("briefs"), "cost": None, "timeline": None}
    if not processed:
        out = {key: None for key in out}
    return {"spec": spec, "out": out, "processed": processed, "path": Path(f"{event_id}.json")}


def _events() -> list[dict]:
    listing = {"listing": {"status": "scheduled", "listed_on": "2026-11-06", "date_as_printed": "On or before 6 Nov"}}
    sale = {"sale": {"sale_date_parsed": "2026-04-21", "sale_date": "21st April, 2026"}}
    return [
        _event("a", "ipo", listing, [_entry("p1", 9, "high", "scheduled"), _entry("p2", NEW_SIGNAL_DAYS + 1, "high")],
               briefs={"briefs": [{"brief_source": "template", "template_problem": None}]}),
        _event("b", "ofs_stock_exchange", sale, [_entry("p3", None)],
               extract={"completeness": {"t": {"status": "values unverified"}}}),
        _event("c", "ipo", {}, [], processed=False),
    ]


def test_kpis_follow_the_rules_in_config():
    numbers = data.kpis(_events())
    assert numbers == {"events": 2, "sources": 1, "potential": 3, "new": 1, "high": 2, "new_days": NEW_SIGNAL_DAYS}
    assert data.is_high_priority(_entry("x", 1, "high", "scheduled"))
    assert not data.is_high_priority(_entry("x", 1, "high", "locked_in"))
    assert not data.is_new_signal(_entry("x", None))


def test_event_dates_come_from_stored_fields_only():
    events = _events()
    assert data.event_date(events[0]["out"]["people"])["kind"] == "scheduled listing"
    assert data.event_date(events[1]["out"]["people"])["date"] == "2026-04-21"
    unknown = data.event_date({})
    assert unknown["date"] is None and unknown["status"] == "unknown" and unknown["reason"]


def test_monthly_counts_fill_empty_months_and_respect_the_range():
    rows = data.timeline_rows(_events(), "event", {})
    months = data.monthly_counts(rows, None, date(2026, 11, 15))
    assert [m["month_key"] for m in months][:2] == ["2026-04", "2026-05"] and len(months) == 8
    assert sum(m["events"] for m in months) == 2
    recent = data.monthly_counts(rows, date(2026, 10, 1), date(2026, 11, 15))
    assert [(m["month_key"], m["events"]) for m in recent] == [("2026-10", 0), ("2026-11", 1)]


def test_event_mix_counts_processed_events():
    assert data.event_mix(_events()) == [{"type": "IPO", "events": 1, "share": 50},
                                         {"type": "OFS (stock exchange)", "events": 1, "share": 50}]


def test_notifications_name_each_stored_problem():
    notes = data.notifications(_events(), date(2026, 11, 15))
    titles = [note["title"] for note in notes]
    assert "a Ltd: scheduled listing date has passed" in titles
    assert any("template brief" in title for title in titles)
    assert any("values unverified" in title for title in titles)
    assert "c Ltd: no outputs yet" in titles
    assert len({note["id"] for note in notes}) == len(notes)
    unverified = next(note for note in notes if "values unverified" in note["title"])
    assert "could not be verified" in unverified["detail"]


def test_search_index_covers_companies_events_and_people():
    index = data.search_index(_events())
    kinds = {item["kind"] for item in index}
    assert kinds == {"action", "company", "event", "person"}
    person = next(item for item in index if item["label"] == "P1")
    assert person["target"] == {"page": "prospects", "event": "a", "person": "p1", "group": "callable"}
    assert "role unknown" in person["sub"]


def test_search_script_never_writes_html():
    lines = (WEB / "search.js").read_text(encoding="utf-8").splitlines()
    script = "\n".join(line for line in lines if not line.strip().startswith("//"))
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script and "textContent" in script


# ---------- money becoming available, today's calls, call sheet, funnel ----------

def _figure(crore: str, display: str) -> dict:
    return {"status": "computed", "crore_high": crore, "display": display}


def _money_events() -> list[dict]:
    """One IPO: a seller with cash and one unlock period, a holder whose lock-in end is not stored,
    a holder split across two periods, and a seller whose amount is unknown."""
    people = {
        "listing": {"status": "verified", "listed_on": "2026-03-11", "date_as_printed": "March 11, 2026"},
        "people": [
            {"person_id": "p1", "amounts": {"proceeds": _figure("9.13", "up to ₹9.13 crore"),
                                            "retained": _figure("64.08", "₹64.08 crore (estimate)")},
             "timing": {"retained": {"periods": [{"share_of_retained": "all", "ends_on": "2026-09-09", "label": "pre"}]}}},
            {"person_id": "p2", "amounts": {"retained": _figure("10.00", "₹10.00 crore (estimate)")},
             "timing": {"retained": {"periods": [{"share_of_retained": "unknown", "ends_on": None}]}}},
            {"person_id": "p3", "amounts": {"retained": _figure("5.00", "₹5.00 crore (estimate)")},
             "timing": {"retained": {"periods": [{"share_of_retained": "unknown", "ends_on": "2026-09-09"},
                                                 {"share_of_retained": "unknown", "ends_on": "2027-03-09"}]}}},
            {"person_id": "p4", "amounts": {"proceeds": {"status": "unknown", "reason": "own shares not printed"}},
             "timing": {}},
            {"person_id": "p5", "amounts": {"proceeds": _figure("2.00", "up to ₹2.00 crore")}, "timing": {}},
        ],
    }
    entries = [{**_entry(pid, 5), "rank": index + 1, "score": score}
               for index, (pid, score) in enumerate((("p1", "9.1"), ("p2", "1.0"), ("p3", "0.5"), ("p4", "0"),
                                                     ("p5", "3.5")))]
    return [_event("m", "ipo", people, entries)]


def test_money_points_split_cash_and_estimate_and_count_what_cannot_be_plotted():
    found = data.money_points(_money_events())
    plotted = {(point["person_id"], point["series"], point["date"]) for point in found["points"]}
    assert plotted == {("p1", data.CASH, "2026-03-11"), ("p1", data.ESTIMATE, "2026-09-09"),
                       ("p5", data.CASH, "2026-03-11")}
    assert found["date_unknown"] == ["P2 (m Ltd)"]
    assert found["split_unknown"] == ["P3 (m Ltd)"]
    assert found["amount_unknown"] == ["P4 (m Ltd)"]


def test_money_by_date_sums_stored_high_ends_and_keeps_display_text():
    rows = data.money_by_date(data.money_points(_money_events())["points"], None, None)
    cash = next(row for row in rows if row["series"] == data.CASH)
    assert cash["crore_text"] == "₹11.13 crore (sum of stored high ends)" and cash["people"] == 2
    assert "up to ₹9.13 crore" in cash["who"] and cash["status"] == data.VERIFIED_DATE
    estimate = next(row for row in rows if row["series"] == data.ESTIMATE)
    assert estimate["crore"] == 64.08 and "(estimate)" in estimate["who"]
    assert data.money_by_date(data.money_points(_money_events())["points"], date(2026, 4, 1), date(2026, 12, 31)) == [
        estimate]


def test_scheduled_listing_cash_is_marked_scheduled():
    events = _money_events()
    events[0]["out"]["people"]["listing"] = {"status": "scheduled", "listed_on": "2026-11-06",
                                             "date_as_printed": "On or before 6 Nov"}
    statuses = {point["status"] for point in data.money_points(events)["points"] if point["series"] == data.CASH}
    assert statuses == {data.SCHEDULED_DATE}


def test_top_calls_are_ordered_by_stored_score_and_filterable():
    calls = data.top_calls(_money_events(), 3)
    assert [call["entry"]["person_id"] for call in calls] == ["p1", "p5", "p2"]
    only = data.top_calls(_money_events(), 8, only={("m", "p3")})
    assert [call["entry"]["person_id"] for call in only] == ["p3"]
    assert data.top_calls(_money_events(), 8, event_type="Buyback") == []


def test_call_sheet_csv_has_the_stated_columns_and_neutralises_formulas():
    calls = data.top_calls(_money_events(), 2)
    calls[0]["entry"] = {**calls[0]["entry"], "name_as_printed": "=HYPERLINK(\"x\")", "why_money": "+1",
                         "amount_display": "-5", "timing_display": "@now"}
    calls[0]["brief"] = {"lines": ["line one", "line two"]}
    text = data.call_sheet_csv(data.call_sheet_rows(calls))
    header, first = text.splitlines()[:2]
    assert header == "rank,name,role,company,why money,amount,timing,confidence,brief,first evidence link"
    assert "'=HYPERLINK" in first and ",'+1," in first and ",'-5," in first and ",'@now," in first
    assert "line one line two" in first
    for line in text.splitlines()[1:]:
        for cell in next(iter(__import__("csv").reader([line]))):
            assert not cell.startswith(("=", "+", "-", "@"))


def test_safe_cell_leaves_ordinary_text_alone():
    assert data.safe_cell("up to ₹9.13 crore") == "up to ₹9.13 crore"
    assert data.safe_cell(None) == "" and data.safe_cell("=1") == "'=1"


def test_funnel_rows_use_stored_counts_and_reasons():
    extracted = {"counts": {"a": {"proposed": 8, "kept": 6, "rejected": 1, "unattributed": 1}, "note": 3},
                 "rejections": [{"section": "a", "reason": "value not in quote"},
                                {"section": "a", "reason": "value not in quote"}]}
    assert data.funnel_rows(extracted) == [{"section": "a", "proposed": 8, "kept": 6, "rejected": 1, "unattributed": 1,
                                            "reasons": "value not in quote ×2"}]


def test_timing_groups_keep_unlocked_and_not_applicable_apart():
    assert data.timing_group("in_hand") == "In hand" and data.timing_group("at_listing") == "Scheduled"
    assert data.timing_group("partly_unlocked") == "Locked" and data.timing_group("unlocked") == "Unlocked"
    assert data.timing_group("not_applicable") == "Not applicable" and data.timing_group(None) == "Unknown"



def test_provenance_says_where_an_event_came_from():
    hand = data.provenance({"discovery": None})
    assert hand == {"kind": "hand", "text": "Added by hand", "links": []}
    found = data.provenance({"discovery": {"sources": ["sebi_prospectus"], "first_seen": "2026-11-15T07:44:29+00:00",
                                           "items": [{"title": "Example - Prospectus", "link": "https://example.org/i"}]}})
    assert found["text"].startswith("Discovered from SEBI") and found["text"].endswith("on 2026-11-15")
    assert found["links"] == [{"title": "Example - Prospectus", "link": "https://example.org/i"}]


def test_check_lines_grade_each_document():
    report = {"documents": [
        {"doc_type": "prospectus", "url": "https://example.org/p.pdf", "fetched": "yes", "pages": 100,
         "low_text_pages": list(range(30)), "sections_found": {"selling_shareholders": "p. 16"},
         "sections_missing": ["waca"]},
        {"doc_type": "announcement", "url": "https://example.org/a.pdf", "fetched": "no: HTTP 404"}]}
    levels = [level for level, _words in data.check_lines(report)]
    assert levels == ["pass", "warning", "pass", "warning", "fail"]
    assert data.check_lines(None) == [("fail", "the check did not run")]
