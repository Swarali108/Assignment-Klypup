"""One sale reported twice (insider disclosure + exchange notice, block + bulk deal) is one row, once in the totals."""

from types import SimpleNamespace

from api import views


def _event(event_id, event_type, company, date_iso, shares, name="anand pandit"):
    spec = SimpleNamespace(event_id=event_id, event_type=event_type, company=company)
    people = {"people": [{"person_id": "p1", "name_clean": name, "shares_offered": shares}],
              "sale": {"sale_date_parsed": date_iso}}
    return {"spec": spec, "processed": True, "out": {"people": people}, "raw": {}}


def _item(event, value, tier="cash_now"):
    ref = {"id": event["spec"].event_id, "company": event["spec"].company, "type": event["spec"].event_type,
           "type_label": views.type_label(event["spec"].event_type)}
    return {"id": f"{ref['id']}/p1", "event": ref, "person": {"id": "p1", "name": "Anand Pandit"}, "tier": tier,
            "amount": {"value_cr": value}}


def test_same_sale_in_two_sources_is_kept_once():
    insider = _event("a_insider_sale_2026w45", "insider_sale", "Lotus Realty Limited", "2026-11-04", "2,38,58,955")
    notice = _event("a_ofs_stock_exchange_202611", "ofs_stock_exchange", "Lotus Realty", "2026-11-03", "2,37,95,818")
    kept, dropped = views._merge_duplicate_sales([(notice, [_item(notice, 571.1)]), (insider, [_item(insider, 572.96)])])
    assert [i["amount"]["value_cr"] for i in kept] == [572.96]  # the actual trade wins over the notice
    assert dropped == {"a_ofs_stock_exchange_202611/p1"}
    assert kept[0]["sources"] == ["Insider sale", "Offer for sale (exchange)"]


def test_different_trades_are_not_merged():
    week1 = _event("a_insider_sale_2026w44", "insider_sale", "Lotus", "2026-10-29", "1,00,000")
    week2 = _event("a_insider_sale_2026w45", "insider_sale", "Lotus", "2026-11-04", "1,04,265")
    kept, dropped = views._merge_duplicate_sales([(week1, [_item(week1, 4.99)]), (week2, [_item(week2, 5.04)])])
    assert len(kept) == 2 and not dropped


def test_same_shares_far_apart_in_time_are_not_merged():
    first = _event("a_block_deal_2026w44", "block_deal", "Lotus", "2026-10-20", "50,000")
    second = _event("a_block_deal_2026w46", "block_deal", "Lotus", "2026-11-11", "50,000")
    kept, dropped = views._merge_duplicate_sales([(first, [_item(first, 3.0)]), (second, [_item(second, 3.0)])])
    assert len(kept) == 2 and not dropped


def test_pronoun_with_one_person_in_focus_beats_calendar_words(monkeypatch):
    from types import SimpleNamespace as NS

    from api.chat import agent, router

    focus = [{"kind": "person", "event_id": "e", "person_id": "p", "label": "Manish Sharma"}]
    turn = NS(state={"focus": focus})
    question = "when does he get the money and when is the lock-in over?"
    route = router.rules(question)
    assert route is not None and route.intent == "calendar"  # the time words alone would dump the calendar
    pointed = agent.pronoun_focus(turn, question, route)
    assert pointed.intent == "person" and pointed.args["entities"] == focus
    assert agent.pronoun_focus(NS(state={"focus": []}), question, route) is None  # nobody in focus: unchanged
    monkeypatch.setattr(agent.tools, "companies", lambda: ["SEDEMAC Mechatronics"])
    other = "when is the lock-in over for him at SEDEMAC Mechatronics?"
    assert agent.pronoun_focus(turn, other, router.Route("calendar")) is None  # a named company: a different question
