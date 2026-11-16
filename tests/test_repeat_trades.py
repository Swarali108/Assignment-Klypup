"""Today: repeat sales by one holder at one company are one call, led by the newest trade, with every trade listed
on the slot. The trades keep their own rows on event pages and in the calendar, a chat answer about a date window
counts only the trades inside it, filters see every trade, and no trade drops off Today."""

from __future__ import annotations

from datetime import date

from api import brief, store, views
from api.chat import tools
from api.chat.windows import Window


def _item(eid: str, cr: float | None, iso: str, *, name: str = "Elvin Machado", company: str = "Avenue Supermarts Limited",
          kind: str = "insider_sale", tier: str = "cash_now", score: float = 1.0) -> dict:
    return {"id": f"{eid}/p_x", "event": {"id": eid, "company": company, "type": kind, "type_label": "Insider sale"},
            "person": {"id": "p_x", "name": name, "role": None, "holder_type": "person", "kind_label": None},
            "tier": tier, "tier_label": "Cash in hand",
            "amount": {"value_cr": cr, "low_cr": cr, "display": "" if cr is None else f"₹{cr:.2f} Cr", "detail": None,
                       "kind": "cash", "estimate": False, "reason": None, "source": "proceeds"},
            "timing": {"label": f"Settled {iso}", "status": "settled", "date_iso": iso, "past": True},
            "confidence": {"level": "high", "reason": ""}, "why": "Sold shares", "brief_first_line": None,
            "household": None, "household_id": None, "rank": 1, "score": score, "flags": [],
            "rm": {"status": "to_call", "follow_up": None, "note": ""}, "in_book": False}


def _elvin() -> list[dict]:
    """Three trades in call order (best first), plus a different holder and the same name at another company."""
    return [_item("avenue_w45", 3.35, "2026-11-05", score=9), _item("avenue_w43", 1.90, "2026-10-23", score=8),
            _item("other_w45", 2.00, "2026-11-05", name="Vikram Bhatia", score=7),
            _item("avenue_w46", 1.73, "2026-11-10", score=6),
            _item("dmart_other_w46", 1.00, "2026-11-10", company="Kapston Services Limited", score=5)]


def test_repeat_sales_fold_into_the_newest_trade_in_its_own_place():
    folded = views.fold_repeat_trades(_elvin())
    assert [i["id"] for i in folded] == ["other_w45/p_x", "avenue_w46/p_x", "dmart_other_w46/p_x"]
    lead = folded[1]
    assert lead["amount"]["value_cr"] == 1.73 and lead["timing"]["date_iso"] == "2026-11-10"  # the newest sale's own
    assert [t["date_iso"] for t in lead["trades"]] == ["2026-11-10", "2026-11-05", "2026-10-23"]
    assert [t["id"] for t in lead["trades"]] == ["avenue_w46/p_x", "avenue_w45/p_x", "avenue_w43/p_x"]
    assert lead["trades_total_cr"] == 6.98 and lead["trades_unpriced"] == 0
    assert "trades" not in folded[0] and "trades" not in folded[2]


def test_the_slot_carries_the_newest_sales_call_status_and_each_trade_its_own():
    """A sale after the RM's call is a new reason to call; the earlier call stays visible on its trade."""
    items = _elvin()
    items[0]["rm"] = {"status": "won", "follow_up": None, "note": ""}  # 5 Nov sale: won
    lead = next(i for i in views.fold_repeat_trades(items) if i.get("trades"))
    assert lead["rm"]["status"] == "to_call"
    assert next(t for t in lead["trades"] if t["id"] == "avenue_w45/p_x")["rm_status"] == "won"


def test_ltd_and_limited_and_punctuation_are_one_company_and_one_holder():
    items = [_item("a", 1.0, "2026-11-05"), _item("b", 2.0, "2026-11-12", company="Avenue Supermarts Ltd.",
                                                   name="ELVIN  MACHADO.")]
    folded = views.fold_repeat_trades(items)
    assert len(folded) == 1 and len(folded[0]["trades"]) == 2


def test_only_cash_sales_fold():
    """An IPO seller and a holder still locked in are not weekly trades; they keep their rows."""
    ipo = [_item("ipo_a", 5.0, "2026-10-21", kind="ipo"), _item("ipo_b", 4.0, "2026-10-21", kind="ipo")]
    held = [_item("w1", None, "2026-11-05", tier="holding"), _item("w2", None, "2026-11-12", tier="holding")]
    assert len(views.fold_repeat_trades(ipo)) == 2
    assert len(views.fold_repeat_trades(held)) == 2


def test_an_unpriced_trade_is_counted_but_not_added():
    folded = views.fold_repeat_trades([_item("a", 2.5, "2026-11-05"), _item("b", None, "2026-11-12")])
    assert folded[0]["trades_total_cr"] == 2.5 and folded[0]["trades_unpriced"] == 1


def test_a_small_total_is_shown_in_rupees_not_as_zero_crore():
    folded = views.fold_repeat_trades([_item("a", 0.000254, "2026-11-05"), _item("b", 0.0001, "2026-11-12")])
    assert folded[0]["trades_total_display"] == "₹3,540" and folded[0]["trades_total_cr"] == 0.0


def test_folding_twice_changes_nothing():
    once = views.fold_repeat_trades(_elvin())
    assert views.fold_repeat_trades(once) == once


def test_chat_window_counts_only_the_trades_inside_it():
    """'Who came into money this week' must not credit a holder with last month's trade."""
    week = Window(date(2026, 11, 4), date(2026, 11, 10), "this week")
    result = tools.windowed(_elvin(), week, 8, {}, "Came into money this week")
    rows = result["data"]["people"]
    elvin = [r for r in rows if r["name"] == "Elvin Machado" and r["company"].startswith("Avenue")]
    assert len(elvin) == 1
    assert elvin[0]["trades"] == 2 and elvin[0]["trades_total"] == "₹5.08 Cr"  # 3.35 + 1.73, not the October 1.90
    assert elvin[0]["money_date"] == "10 Nov 2026"
    assert result["data"]["count"] == len(rows) == 3


def test_chat_nearest_rows_date_each_holder_by_the_trade_nearest_the_window():
    later = Window(date(2026, 11, 20), date(2026, 11, 26), "next week")
    rows = tools.windowed(_elvin(), later, 8, {}, "Came into money next week")["data"]["nearest"]
    elvin = [r for r in rows if r["name"] == "Elvin Machado" and r["company"].startswith("Avenue")]
    assert len(elvin) == 1 and elvin[0]["money_date"] == "10 Nov 2026"
    earlier = Window(date(2026, 10, 1), date(2026, 10, 7), "early October")
    rows = tools.windowed(_elvin(), earlier, 8, {}, "Came into money in early October")["data"]["nearest"]
    elvin = [r for r in rows if r["name"] == "Elvin Machado" and r["company"].startswith("Avenue")]
    assert len(elvin) == 1 and elvin[0]["money_date"] == "23 Oct 2026"


def test_compact_row_names_the_trades_only_when_there_are_several():
    single = tools.compact(_item("a", 1.0, "2026-11-05"))
    assert "trades" not in single
    lead = tools.compact(next(i for i in views.fold_repeat_trades(_elvin()) if i.get("trades")))
    assert lead["trades"] == 3 and lead["trades_total"] == "₹6.98 Cr"


def test_coverage_judges_a_folded_slot_by_every_trade():
    """An RM who covers insider sales still sees a holder whose newest sale was a block deal."""
    items = [_item("g_insider_w45", 270.62, "2026-11-03"), _item("g_block_w46", 201.20, "2026-11-13", kind="block_deal")]
    slot = views.fold_repeat_trades(items)[0]
    assert slot["event"]["type"] == "block_deal"
    assert brief.fits_coverage(slot, {"event_types": ["insider_sale"]})
    assert not brief.fits_coverage(slot, {"event_types": ["ipo"]})
    assert brief.fits_coverage(slot, {"min_ticket_cr": 400})  # 471.82 together
    assert not brief.fits_coverage(slot, {"min_ticket_cr": 500})


def test_no_trade_drops_off_today_when_a_household_member_sells_again(monkeypatch):
    """Week 44: a family (HUF leads, the individual is its member). Week 45: the individual sells again alone."""
    huf = _item("jain_w44", 37.33, "2026-11-02", name="Nitn Kapoor and HUF", score=9)
    solo44 = _item("jain_w44", 33.01, "2026-11-02", name="Nitn Kapoor", score=8)
    solo44["id"] = "jain_w44/p_y"
    solo45 = _item("jain_w45", 10.0, "2026-10-28", name="Nitn Kapoor", score=7)  # older money date: w44 leads
    family = {"id": "jain_w44:family_1", "label": "Kapoor family", "members": [huf, solo44]}
    for member in (huf, solo44):
        member["household_id"], member["household"] = "jain_w44:family_1", family
    monkeypatch.setattr(views, "all_items", lambda events, rm: [huf, solo44, solo45])
    queue = views.today_queue([], {})
    shown = {s["id"] for s in queue} | {m["id"] for s in queue for m in s["members"]} \
        | {t["id"] for s in queue for t in s.get("trades") or []}
    assert {"jain_w44/p_x", "jain_w44/p_y", "jain_w45/p_x"} <= shown


def _sale_event(eid, kind, date_iso, shares, lines):
    from types import SimpleNamespace
    spec = SimpleNamespace(event_id=eid, event_type=kind, company="Gallantt Ispat Limited")
    people = {"people": [{"person_id": "p1", "name_clean": "dinesh r agarwal", "shares_offered": shares,
                          "trades": [{"trade_date": d, "quantity": q} for d, q in lines]}],
              "sale": {"sale_date_parsed": date_iso}}
    return {"spec": spec, "processed": True, "out": {"people": people}, "raw": {}}


def _sale_item(ev, value):
    ref = {"id": ev["spec"].event_id, "company": ev["spec"].company, "type": ev["spec"].event_type,
           "type_label": views.type_label(ev["spec"].event_type)}
    return {"id": f"{ref['id']}/p1", "event": ref, "person": {"id": "p1", "name": "DINESH R AGARWAL"},
            "tier": "cash_now", "amount": {"value_cr": value}}


def _merge(*pairs):
    return views._merge_duplicate_sales([(ev, [_sale_item(ev, value)]) for ev, value in pairs])


def test_an_insider_disclosure_that_contains_a_block_deal_is_one_sale():
    """Gallantt: the insider disclosure is a 2 Nov market sale plus the 3 Nov block deal, reported on its own too."""
    event, item = _sale_event, _sale_item
    insider = event("g_insider_sale_2026w45", "insider_sale", "2026-11-03", "53,89,708",
                    [("2026-11-02", 389708), ("2026-11-03", 5000000)])
    block = event("g_block_deal_2026w45", "block_deal", "2026-11-04", "50,00,000", [("2026-11-03", 5000000)])
    later = event("g_block_deal_2026w46", "block_deal", "2026-11-13", "40,00,000", [("2026-11-12", 4000000)])
    kept, dropped = views._merge_duplicate_sales([(block, [item(block, 250.5)]), (later, [item(later, 201.2)]),
                                                  (insider, [item(insider, 270.62)])])
    assert dropped == {"g_block_deal_2026w45/p1"}
    assert sorted(i["amount"]["value_cr"] for i in kept) == [201.2, 270.62]
    assert next(i for i in kept if i["amount"]["value_cr"] == 270.62)["sources"] == ["Insider sale", "Block deal"]


def test_containment_never_chains_and_a_partial_overlap_keeps_both_rows():
    """K sits inside I; B shares K's line but also has a 5 Nov sale I lacks. Only K is dropped; no trade is lost."""
    i = _sale_event("g_insider_sale_w45", "insider_sale", "2026-11-03", "53,89,708",
                    [("2026-11-02", 389708), ("2026-11-03", 5000000)])
    k = _sale_event("g_block_deal_w45", "block_deal", "2026-11-04", "50,00,000", [("2026-11-03", 5000000)])
    b = _sale_event("g_bulk_deal_w45", "block_deal", "2026-11-06", "60,00,000",
                    [("2026-11-03", 5000000), ("2026-11-05", 1000000)])
    kept, dropped = _merge((i, 270.62), (k, 250.50), (b, 300.60))
    assert dropped == {"g_block_deal_w45/p1"}
    assert sorted(x["amount"]["value_cr"] for x in kept) == [270.62, 300.60]


def test_a_multi_day_row_absorbs_every_sale_it_contains():
    """The week's bulk row repeats Monday's insider sale and Thursday's block deal: one row, counted once."""
    mon = _sale_event("x_insider_sale_w46", "insider_sale", "2026-11-10", "1,00,000", [("2026-11-09", 100000)])
    thu = _sale_event("x_block_deal_w46", "block_deal", "2026-11-13", "8,00,000", [("2026-11-12", 800000)])
    week = _sale_event("x_bulk_deal_w46", "block_deal", "2026-11-13", "9,00,000",
                       [("2026-11-09", 100000), ("2026-11-12", 800000)])
    kept, dropped = _merge((mon, 1.0), (thu, 8.0), (week, 9.0))
    assert [x["amount"]["value_cr"] for x in kept] == [9.0]
    assert dropped == {"x_insider_sale_w46/p1", "x_block_deal_w46/p1"}


def test_a_family_that_sells_together_in_two_weeks_keeps_both_family_slots(monkeypatch):
    """Ramesh leads his family's sale in two weeks; folding would hide one week's family, so families never fold."""
    rows = []
    for week, iso in (("acme_w45", "2026-11-05"), ("acme_w46", "2026-11-12")):
        lead = _item(week, 5.0, iso, name="Ramesh Shah", company="Acme Limited", score=9)
        wife = _item(week, 4.0, iso, name="Sunita Shah", company="Acme Limited", score=8)
        wife["id"] = f"{week}/p_w"
        family = {"id": f"{week}:family_1", "label": "Shah family", "members": [lead, wife]}
        for member in (lead, wife):
            member["household_id"], member["household"] = family["id"], family
        rows += [lead, wife]
    monkeypatch.setattr(views, "all_items", lambda events, rm: rows)
    queue = views.today_queue([], {})
    assert [s["id"] for s in queue] == ["acme_w45/p_x", "acme_w46/p_x"]
    assert all(len(s["members"]) == 1 and not s.get("trades") for s in queue)


def test_today_on_real_outputs_has_one_slot_per_holder_and_company():
    events = store.load_events()
    items = views.all_items(events, {})
    queue = views.today_queue(events, {})
    keys = [views.repeat_trade_key(i) for i in queue if views.repeat_trade_key(i) and not i["members"]]
    assert len(keys) == len(set(keys))  # a holder's own sales are one slot (a family slot of theirs may sit apart)
    shown = {s["id"] for s in queue} | {m["id"] for s in queue for m in s["members"]} \
        | {t["id"] for s in queue for t in s.get("trades") or []}
    assert {i["id"] for i in items} <= shown  # every trade is on Today as a slot, a family member or a listed trade
    for slot in queue:
        if slot.get("trades"):
            assert slot["timing"]["date_iso"] == max(t["date_iso"] or "" for t in slot["trades"])
            assert not slot["members"]  # a family slot is never folded
    head = views.summary(events, {})
    assert head["cash_now_cr"] == views.crore(views.cash_total(items))  # every trade's cash still counts
    assert head["people_total"] == len(views.fold_repeat_trades(items))
    for slot in queue:
        for trade in slot.get("trades") or []:
            assert views.repeat_trade_key({**slot, "event": trade["event"]}) == views.repeat_trade_key(slot)


def test_event_pages_and_calendar_keep_each_trade():
    events = store.load_events()
    items = views.all_items(events, {})
    folded = views.fold_repeat_trades(items)
    if len(folded) == len(items):
        return  # no repeat trades in this data set
    lead = next(i for i in folded if i.get("trades"))
    dated = {p["id"] for row in views.calendar(events, {}, None, None) for p in row["people"]}
    assert {t["id"] for t in lead["trades"] if t["date_iso"]} <= dated


def test_a_family_slot_stays_apart_but_the_holders_own_weeks_still_fold(monkeypatch):
    """The HUF leads its family's w44 sale and sells alone in w45 and w46: the family call plus one folded row."""
    huf = _item("jain_w44", 37.33, "2026-11-02", name="Nitn Kapoor and HUF", company="Jain Irrigation Systems L", score=9)
    solo = _item("jain_w44", 33.01, "2026-11-02", name="Nitn Kapoor", company="Jain Irrigation Systems L", score=8)
    solo["id"] = "jain_w44/p_y"
    family = {"id": "jain_w44:family_1", "label": "Kapoor family", "members": [huf, solo]}
    for member in (huf, solo):
        member["household_id"], member["household"] = family["id"], family
    w45 = _item("jain_w45", 13.55, "2026-11-03", name="Nitn Kapoor and HUF", company="Jain Irrigation Systems L", score=7)
    w46 = _item("jain_w46", 10.0, "2026-11-12", name="Nitn Kapoor and HUF", company="Jain Irrigation Systems L", score=6)
    monkeypatch.setattr(views, "all_items", lambda events, rm: [huf, solo, w45, w46])
    queue = views.today_queue([], {})
    assert [s["id"] for s in queue] == ["jain_w44/p_x", "jain_w46/p_x"]
    assert [m["id"] for m in queue[0]["members"]] == ["jain_w44/p_y"] and not queue[0].get("trades")
    assert [t["id"] for t in queue[1]["trades"]] == ["jain_w46/p_x", "jain_w45/p_x"]
