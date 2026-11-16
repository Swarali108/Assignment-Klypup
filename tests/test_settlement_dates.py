"""Exchange-sale money is dated on the settlement day the label shows (T+1), not the trade day.

Chat windows, Today and the calendar all read an item's money date, so they must agree with
"Settled 16 Nov, T+1 after the 13 Nov trade". IPO listing and buyback dates are unchanged.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from api import views
from api.chat.windows import Window, split

ROOT = Path(__file__).resolve().parents[1]
SETTLED = date(2026, 11, 16)  # proceeds settle on D
TRADED = date(2026, 11, 13)  # trade on D-1 (the Friday before)


def _event(event_type: str, people: dict) -> dict:
    return {"spec": SimpleNamespace(event_type=event_type, event_id=f"x_{event_type}", company="X"),
            "out": {"people": people}, "processed": True}


def _settled_sale() -> tuple[dict, dict]:
    proceeds = {"status": "settles", "when": "settled 16 Nov 2026, T+1 after the 13 Nov 2026 trade (today)",
                "trade_date": TRADED.isoformat(), "settles_on": SETTLED.isoformat(), "rule": "T+1"}
    person = {"timing": {"proceeds": proceeds}}
    event = _event("block_deal", {"sale": {"sale_date_parsed": TRADED.isoformat()}})
    return person, event


def test_settled_sale_falls_in_its_settlement_day_window():
    person, event = _settled_sale()
    timing = views.headline_timing("cash_now", {}, person, event)
    assert timing["date_iso"] == SETTLED.isoformat()
    item = {"timing": timing}
    inside, _ = split([item], Window(SETTLED, SETTLED, "today"))
    assert inside == [item]
    inside, outside = split([item], Window(TRADED, TRADED, "that day"))
    assert inside == [] and outside == [item]


def test_ipo_and_buyback_dates_are_unchanged():
    listing = {"listing": {"listed_on": "2026-11-26", "status": "scheduled"}}
    ipo = _event("ipo", listing)
    person = {"timing": {"proceeds": {"status": "scheduled", "days_since": -10}}}
    assert views.headline_timing("cash_now", {}, person, ipo)["date_iso"] == "2026-11-26"

    buyback = _event("buyback", {"buyback_dates": {"payment": {"status": "verified", "date": "2026-06-24"}}})
    paid = {"timing": {"proceeds": {"status": "settles", "when": "Paid by 24 Jun 2026"}}}
    assert views.headline_timing("cash_now", {}, paid, buyback)["date_iso"] == "2026-06-24"
    assert views.headline_timing("holding", {}, paid, buyback)["date_iso"] == "2026-06-24"


def _stored_people(event_id: str) -> dict:
    doc = json.loads((ROOT / "outputs" / event_id / "people.json").read_text(encoding="utf-8"))
    return {p["person_id"]: p for p in doc["people"]}


def test_calendar_places_exchange_sale_on_settlement_day(client_admin):
    rows = client_admin.get("/api/calendar").json()["items"]
    sales = [r for r in rows if r["kind"] == "ofs_sale" and r["event"]["type"] in ("block_deal", "insider_sale")]
    assert sales
    for row in sales:
        people = _stored_people(row["event"]["id"])
        for p in row["people"]:
            settles = people[p["person_id"]]["timing"]["proceeds"].get("settles_on")
            assert settles == row["date_iso"], (row["event"]["id"], p["name"], row["date_iso"], settles)
        assert row["label"] == "Exchange sale settles"

    cohance = [r for r in sales if r["event"]["id"] == "cohance_lifesciences_block_deal_2026w46"]
    assert [r["date_iso"] for r in cohance] == ["2026-11-12"]

    # An off-market transfer has no exchange settlement date, so it is not shown as one.
    assert not any(r["event"]["id"] == "tribhovandas_bhimji_zaveri_insider_sale_2026w44" for r in sales)


def test_calendar_keeps_listing_dates(client_admin):
    """IPO listing rows (with sellers' cash on them) stay on the stored listing day."""
    rows = client_admin.get("/api/calendar").json()["items"]
    zetwerk = [r for r in rows if r["event"]["id"] == "zetwerk_manufacturing_businesses_limited_ipo_202610"
               and r["kind"] == "listing"]
    assert [r["date_iso"] for r in zetwerk] == ["2026-10-23"] and zetwerk[0]["people"]
    assert any(r["kind"] == "listing" and r["date_iso"] == "2026-11-26" for r in rows)
