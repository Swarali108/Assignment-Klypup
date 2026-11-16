"""The five pages, in the order an RM asks:

Home       "Who do I call today?": KPI cards, money becoming available, event mix, today's calls, live feed.
Live feed  money events found in official public sources, and what was done with each.
Prospects  "Why them, how much, when?": filters, money by person, call prep sheets, CSV.
Insights   "Can I trust it?": holder-table checks, verification funnel, what we didn't trust.
Network    family links and cross-event matches.
Reports    cost and time per event, the report, downloads, runs, the gated pipeline.

Pages read the loaded events and draw; none computes a figure. Charts count or sum
stored values (ui/dashboard_data.py) and show the stored display text.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from tools.people_index import STOP_RULES
from ui import charts
from ui import components as c
from ui import dashboard_data as data
from ui import views, widgets
from ui.shell import ALL_EVENTS, bump, c_html, chips, clear_focus, go, queue_toast, set_state

MONEY_RANGES = ["Past 90 days", "Next 90 days", "All"]
SORTS = {"Score": "score", "Amount": "amount", "Date": "date"}
BAR_LIMIT = 12


# ---------- Home ----------

def home(events: list[dict], outputs: Path) -> None:
    """KPI cards; money becoming available beside the event mix; today's calls; the live feed's newest items."""
    _kpi_cards(events)
    st.write("")
    left, right = st.columns([1.6, 1])
    with left, st.container(key="panel-money"):
        picked_money = _money_panel(events)
    with right, st.container(key="panel-mix"):
        picked_type = _mix_panel(events)
    st.write("")
    with st.container(key="panel-calls"):
        _calls_panel(events, picked_money, picked_type)
    st.write("")
    with st.container(key="panel-feed-home"):
        feed_compact(events, outputs)


def _kpi_cards(events: list[dict]) -> None:
    """New signals, high priority, potential clients; each opens Prospects with that filter."""
    numbers = data.kpis(events)
    cards = (
        ("new", "layers", numbers["new"], "New Signals", f"money event in the last {numbers['new_days']} days", "lavender",
         f"Callable people whose money event happened 0 to {numbers['new_days']} days ago. Click to see them."),
        ("high", "flame", numbers["high"], "High Priority", "high confidence; cash in hand or on a printed date", "peach",
         "Callable people with high confidence whose money is in hand, paid at listing, or due on a printed "
         "timetable date. Click to see them."),
        ("all", "people", numbers["potential"], "Potential Clients",
         f"across {numbers['events']} events from {numbers['sources']} source{'s' if numbers['sources'] != 1 else ''}",
         "teal", "Everyone on the call lists of the processed events. Click to see them all."),
    )
    for column, (key, icon, value, label, note, tone, tip) in zip(st.columns(3), cards):
        with column, st.container(key=f"kpi-{key}"):
            c_html(c.stat_card(icon, value, label, note, tone))
            st.button(f"Open {label}", key=f"open-kpi-{key}", help=tip, on_click=go, args=("prospects", ALL_EVENTS, key))


def _money_range(choice: str, today: date) -> tuple[date | None, date | None]:
    """The date window for a range pill choice."""
    if choice == "Past 90 days":
        return today - timedelta(days=90), today
    if choice == "Next 90 days":
        return today, today + timedelta(days=90)
    return None, None


def _money_panel(events: list[dict]) -> dict | None:
    """Money becoming available. Returns the clicked point's row (date, series, who), or None."""
    choice = charts.head("Money becoming available",
                         "₹ crore per stored date: cash (proceeds) and shares unlocking, summed from the high end "
                         "of each callable person's stored amount (people.json).",
                         MONEY_RANGES, key="money_range", default="All")
    today = date.today()
    start, end = _money_range(choice, today)
    found = data.money_points(events)
    rows = data.money_by_date(found["points"], start, end)
    event = charts.show(charts.money_chart(rows, today, start, end),
                        pd.DataFrame([{"Date": row["date"], "Series": row["status"], "Amount": row["crore_text"],
                                       "People": row["people"], "Stored amounts": row["who"]} for row in rows]),
                        key=f"money-{st.session_state['money_v']}", table_key="money-table")
    if not rows:
        st.caption(f"No stored money dates in “{choice}”. Choose All to see every date.")
    _money_footnote(found)
    key = charts.picked(event, "pick", "key")
    return next((row for row in rows if row["key"] == key), None)


def _money_footnote(found: dict) -> None:
    """Who is not plotted, and why, counted in words."""
    parts = [(data.unique_count(found["date_unknown"]), "date unknown", found["date_unknown"]),
             (data.unique_count(found["amount_unknown"]), "amount not stored", found["amount_unknown"]),
             (data.unique_count(found["split_unknown"]),
              "retained shares split across lock-in periods; shares per period not stored", found["split_unknown"])]
    shown = [(count, words, names) for count, words, names in parts if count]
    if not shown:
        return
    st.caption("Not plotted: " + " · ".join(f"{count} {'person' if count == 1 else 'people'}: {words}"
                                             for count, words, _names in shown))
    with st.expander("Who is not plotted"):
        for count, words, names in shown:
            st.markdown(f"**{words.capitalize()}** ({count}): " + "; ".join(sorted(set(names))))


def _mix_panel(events: list[dict]) -> str | None:
    """Event Mix donut with events and callable people per type. Returns the clicked type."""
    charts.head("Event Mix", "Processed events by type, and the callable people in each (events/, ranked.json).")
    mix = data.mix_with_people(events)
    if not mix:
        st.caption("No processed events yet. Run an event from Reports.")
        return None
    event = charts.show(charts.donut_chart(mix),
                        pd.DataFrame([{"Type": row["type"], "Events": row["events"], "Callable people": row["people"],
                                       "Share of events %": row["share"]} for row in mix]),
                        key=f"mix-{st.session_state['mix_v']}", table_key="mix-table", height=200)
    c_html(c.mix_legend_html(mix, charts.TYPE_COLOURS))
    return charts.picked(event, "type", "type")


def _calls_panel(events: list[dict], money: dict | None, kind: str | None) -> None:
    """Today's calls: the top 8 by stored score, filtered by the chart clicks; click opens the card."""
    head, link = st.columns([4, 1], vertical_alignment="center")
    with head:
        c_html(c.chart_head_html("Today's calls", "The 8 callable people with the highest stored score across "
                                 "events (ranked.json). Hover or focus a row for the brief and its source."))
    link.button("View all →", key="calls-view-all", type="tertiary", on_click=go, args=("prospects", ALL_EVENTS, "all"))
    active = []
    if money:
        active.append((f"Date: {money['date']} · {money['status']}", bump, ("money_v",)))
    if kind:
        active.append((f"Type: {kind}", bump, ("mix_v",)))
    chips(active, "calls")
    only = set(map(tuple, money["person_ids"])) if money else None
    calls = data.top_calls(events, 8, only=only, event_type=kind)
    if not calls:
        st.caption("No callable people match these filters. Remove a chip above, or open Prospects to see everyone.")
        return
    columns = st.columns(2)
    for index, call in enumerate(calls):
        entry, spec = call["entry"], call["event"]["spec"]
        with columns[index % 2], st.container(key=f"call-{index}"):
            c_html(c.call_row_html(call, index + 1))
            st.button(f"Open {entry['name_as_printed']} ({spec.company})", key=f"open-call-{index}",
                      on_click=go, args=("prospects", spec.event_id, "all", entry["person_id"]))


# ---------- Prospects ----------

def prospects(events: list[dict]) -> None:
    """The working screen: sticky filters, money by person, the CSV, then one prep sheet per person."""
    done = data.processed(events)
    if not done:
        st.info("No processed events yet. Open Reports, unlock the pipeline in the profile menu, and run an event.")
        return
    names = {event["spec"].event_id: event["spec"].company for event in done}
    options = [ALL_EVENTS] + list(names)
    if st.session_state.get("prospects_event") not in options:
        st.session_state["prospects_event"] = ALL_EVENTS
    chosen, which, people_only, table, levels, groups, sort, count_slot = _filter_bar(options, names)
    picked = [event for event in done if chosen in (ALL_EVENTS, event["spec"].event_id)]
    every = [call for event in picked for call in data.event_calls(event)]
    dates = data.money_dates(data.money_points(picked)["points"])
    shown = _sorted([call for call in every if _keep(call, which, people_only, levels, groups)], sort, dates)
    count_slot.markdown(f"**{len(shown)} of {len(every)} shown**")
    _prospect_chips(chosen, names, which, people_only, levels, groups, every)
    if chosen != ALL_EVENTS:
        views.header(picked[0]["spec"], picked[0]["out"])
        c_html(c.provenance_html(data.provenance(picked[0])))
    if not every:
        st.info("This event has no callable people: every holder found is an entity (listed below), "
                "or no holder was found in its documents.")
    elif not shown:
        st.info("No one matches these filters. Remove a chip above, or choose Everyone and All events.")
    else:
        with st.container(key="panel-bars"):
            _person_bars(shown)
        _download(shown)
        if table:
            st.dataframe(pd.DataFrame(data.call_sheet_rows(shown)), hide_index=True, width="stretch")
        else:
            for call in shown:
                _prep_card(call, show_company=chosen == ALL_EVENTS)
    if chosen != ALL_EVENTS:
        entities = data.event_calls(picked[0], group="entities")
        with st.expander(f"Entities: {len(entities)} holders not called directly"):
            for call in entities:
                _prep_card(call, show_company=False, simple=True)
    _scroll_to_focus()


def _filter_bar(options: list[str], names: dict[str, str]):
    """The sticky filter bar. Returns the choices and a slot for the "N of M shown" count."""
    with st.container(key="filterbar"):
        top = st.columns([2.2, 2.4, 1.1, 1.1], vertical_alignment="bottom")
        chosen = top[0].selectbox("Event", options, key="prospects_event",
                                  format_func=lambda key: "All processed events" if key == ALL_EVENTS else names[key])
        which = top[1].segmented_control("Show", list(data.FILTER_LABELS), key="prospects_filter",
                                         format_func=data.FILTER_LABELS.get) or "all"
        people_only = top[2].checkbox("People only", key="prospects_people_only")
        table = top[3].toggle("Table view", key="prospects_table")
        bottom = st.columns([2, 2.4, 1.3, 1.2], vertical_alignment="bottom")
        levels = bottom[0].multiselect("Confidence", ["high", "medium", "low"], key="prospects_conf",
                                       placeholder="Any confidence")
        groups = bottom[1].multiselect("Timing", list(data.TIMING_GROUPS), key="prospects_timing",
                                       placeholder="Any timing")
        sort = bottom[2].selectbox("Sort by", list(SORTS), key="prospects_sort")
        count_slot = bottom[3].empty()
    return chosen, which, people_only, table, levels, groups, SORTS[sort], count_slot


def _keep(call: dict, which: str, people_only: bool, levels: list[str], groups: list[str]) -> bool:
    """Whether a call passes the filter bar."""
    entry = call["entry"]
    return (data.FILTERS[which](entry)
            and (not people_only or entry["holder_type"] == "person")
            and (not levels or entry.get("confidence") in levels)
            and (not groups or data.timing_group(entry.get("timing_display_status")) in groups))


def _sorted(calls: list[dict], sort: str, dates: dict[tuple, str]) -> list[dict]:
    """By stored score, stored money_now_crore, or latest stored money date (undated last); highest first."""
    if sort == "amount":
        return sorted(calls, key=lambda call: Decimal(str(call["entry"].get("money_now_crore") or 0)), reverse=True)
    if sort == "date":
        return sorted(calls, key=lambda call: dates.get((call["event"]["spec"].event_id, call["entry"]["person_id"]), ""),
                      reverse=True)
    return sorted(calls, key=lambda call: Decimal(str(call["entry"].get("score") or 0)), reverse=True)


def _prospect_chips(chosen: str, names: dict, which: str, people_only: bool, levels: list, groups: list,
                    every: list[dict]) -> None:
    """Every active filter as a removable chip, including the person a click opened."""
    active = []
    if chosen != ALL_EVENTS:
        active.append((f"Event: {names[chosen]}", set_state, ("prospects_event", ALL_EVENTS)))
    if which != "all":
        active.append((f"Show: {data.FILTER_LABELS[which]}", set_state, ("prospects_filter", "all")))
    if people_only:
        active.append(("People only", set_state, ("prospects_people_only", False)))
    if levels:
        active.append((f"Confidence: {', '.join(levels)}", set_state, ("prospects_conf", [])))
    if groups:
        active.append((f"Timing: {', '.join(groups)}", set_state, ("prospects_timing", [])))
    focus = st.session_state.get("focus_person")
    person = next((call for call in every if _focus_key(call) == focus), None)
    if person:
        active.append((f"Opened: {person['entry']['name_as_printed']}", clear_focus, ()))
    chips(active, "prospects")


def _focus_key(call: dict) -> str:
    """"event_id|person_id": how a click-through names one card."""
    return f"{call['event']['spec'].event_id}|{call['entry']['person_id']}"


def _card_key(call: dict) -> str:
    """The card container's key; the scroll helper finds the card by it."""
    return f"card-{call['event']['spec'].event_id}-{call['entry']['person_id']}"


def _person_bars(shown: list[dict]) -> None:
    """Money by person: the shown people with stored money now; a click opens and scrolls to the card."""
    with_money = [call for call in shown if Decimal(str(call["entry"].get("money_now_crore") or 0)) > 0]
    top = with_money[:BAR_LIMIT]
    many = len({call["event"]["spec"].event_id for call in shown}) > 1
    charts.head("Money by person",
                f"Stored money_now_crore (high end) for the {len(top)} shown people with money now, in the current "
                "sort order (ranked.json). Colour follows the timing of that money.")
    if not top:
        st.caption("No shown person has money now stored. Their amounts are unknown or not applicable; "
                   "open a card below to see why.")
        return
    rows = [{"label": (f"{call['entry']['name_as_printed']} ({call['event']['spec'].company})" if many
                       else f"{call['entry']['rank']}. {call['entry']['name_as_printed']}"),
             "name": call["entry"]["name_as_printed"], "company": call["event"]["spec"].company,
             "crore": float(Decimal(str(call["entry"]["money_now_crore"]))),
             "money_text": f"₹{call['entry']['money_now_crore']} crore (stored money_now_crore)",
             "trigger": (call["entry"].get("trigger") or {}).get("label") or "no money event stored",
             "amount_display": call["entry"].get("amount_display") or "unknown",
             "legend": charts.GROUP_WORDS[data.timing_group(call["entry"].get("timing_status"))],
             "person_key": _focus_key(call)} for call in top]
    event = charts.show(charts.person_bars(rows),
                        pd.DataFrame([{"Name": row["name"], "Company": row["company"], "Money now": row["money_text"],
                                       "From": row["trigger"], "Card amount": row["amount_display"],
                                       "Timing": row["legend"]} for row in rows]),
                        key=f"bars-{st.session_state['bars_v']}", table_key="bars-table",
                        height=min(260, max(220, 22 * len(rows))))
    hidden = len(with_money) - len(top)
    zero = len(shown) - len(with_money)
    notes = ([f"{hidden} more with money now are in the cards below"] if hidden > 0 else []) + \
            ([f"{zero} shown without money now stored"] if zero else [])
    if notes:
        st.caption(" · ".join(notes) + ".")
    clicked = charts.picked(event, "person", "person_key")
    if clicked and clicked != st.session_state.get("bars_last"):
        st.session_state["focus_person"] = clicked
        st.session_state["scroll_token"] = f"{clicked}|bars|{st.session_state['bars_v']}"
    st.session_state["bars_last"] = clicked


def _download(shown: list[dict]) -> None:
    """Download call sheet (CSV) for exactly the shown people, built from stored fields."""
    csv_text = data.call_sheet_csv(data.call_sheet_rows(shown))
    st.download_button("Download call sheet (CSV)", csv_text, file_name="call_sheet.csv", mime="text/csv",
                       icon=":material/download:", key="call-sheet",
                       on_click=queue_toast, args=("Call sheet downloaded", ":material/download_done:"))


def _prep_card(call: dict, show_company: bool, simple: bool = False) -> None:
    """One card: the head, then the call prep sheet in the expander, top to bottom."""
    entry, person, brief = call["entry"], call["person"], call["brief"]
    focused = st.session_state.get("focus_person") == _focus_key(call)
    with st.container(key=_card_key(call)):
        if show_company:
            c_html(c.tag("div", f"{call['event']['spec'].company} · "
                                f"{data.type_label(call['event']['spec'].event_type)}", cls="mc-label"))
        c_html(c.card_html(entry))
        with st.expander("Call prep sheet: brief, why now, amounts, sources", expanded=focused):
            if simple or not person:
                c_html(c.detail_html(entry, person, brief) if person else c.unknown("person not in people.json"))
                return
            parts = c.prep_sections(entry, person, brief, first_as_chip=False)
            c_html(parts["brief"])
            lines = (brief or {}).get("lines") or []
            if lines:
                copied = widgets.copy_button("\n".join(lines), key=f"copy-{_card_key(call)}")
                if copied == "ok":
                    st.toast("Brief copied to the clipboard", icon=":material/content_copy:")
                elif copied == "failed":
                    st.toast("The browser blocked copying. Select the brief text instead.", icon=":material/block:")
            c_html(parts["why_now"])
            c_html(parts["amounts"])
            source = call.get("source")
            if source and c.safe_url(source["link"]):
                st.link_button(f"Open source page · {source['label']}", source["link"], type="primary",
                               icon=":material/open_in_new:", help=source.get("quote") or None)
            c_html(parts["evidence"])
            for name in ("confidence", "family", "flags", "rank"):
                c_html(parts[name])


def _scroll_to_focus() -> None:
    """After a click-through or a bar click, scroll the opened card into view once."""
    focus, token = st.session_state.get("focus_person"), st.session_state.get("scroll_token")
    if focus and token:
        event_id, person_id = focus.split("|", 1)
        widgets.scroll_to(f".st-key-card-{event_id}-{person_id}", token)


# ---------- Insights ----------

def insights(events: list[dict]) -> None:
    """Holder-table checks as pills, the verification funnel for one event, then what we didn't trust."""
    done = data.processed(events)
    rows = [{"Event": event["spec"].company, "Check": key, "Status": result.get("status")}
            for event in done for key, result in ((event["out"]["extract"] or {}).get("completeness") or {}).items()]
    with st.container(key="panel-checks"):
        c_html(c.chart_head_html("Holder-table checks", "Verified rows summed against each printed table total "
                                 "(extract.json). Red means people may be missing from the call list."))
        c_html(c.check_pills_html(rows))
    event = _event_picker(done, "insights_event")
    if not event:
        return
    with st.container(key="panel-funnel"):
        _funnel(event)
    views.distrust_tab(event["out"])


def _funnel(event: dict) -> None:
    """Verification funnel beside the rejected fields; clicking a section filters the list."""
    charts.head("Verification funnel", "Every value the model proposed is checked against its page; this shows "
                "what was kept, per section (extract.json counts and rejections).")
    rows = data.funnel_rows(event["out"]["extract"])
    if not rows:
        st.caption("No extraction counts stored for this event. Run its extract step from Reports.")
        return
    left, right = st.columns([1.5, 1])
    with left:
        chosen = charts.picked(charts.show(charts.funnel_chart(rows), pd.DataFrame(rows),
                                           key=f"funnel-{event['spec'].event_id}-{st.session_state['funnel_v']}",
                                           table_key="funnel-table", height=max(220, min(260, 26 * len(rows)))),
                               "section", "section")
    with right:
        rejected = [item for item in (event["out"]["extract"] or {}).get("rejections") or []
                    if chosen is None or item.get("section") == chosen]
        chips([(f"Section: {chosen}", bump, ("funnel_v",))] if chosen else [], "funnel")
        c_html(c.tag("div", f"Rejected fields{'' if chosen is None else ' in ' + chosen}: {len(rejected)}",
                     cls="mc-label"))
        if rejected:
            st.dataframe(pd.DataFrame([{"Section": item.get("section"), "Row": item.get("row"),
                                        "Field": item.get("field"), "Value": item.get("value"),
                                        "Reason": item.get("reason")} for item in rejected]),
                         hide_index=True, width="stretch", height=240)
        else:
            st.caption("Nothing was rejected here.")


# ---------- Network ----------

def network(events: list[dict]) -> None:
    """Family groups per event with their stated reasons, then matches across events."""
    done = data.processed(events)
    groups = [{"Event": event["spec"].company, "Members": " · ".join(group["members"]),
               "Why linked": "; ".join(group.get("reasons") or []) or "unknown"}
              for event in done for group in (event["out"]["people"].get("family_groups") or [])]
    with st.container(key="panel-families"):
        c_html(c.panel_head("Family links", "a link is a lead, not a fact"))
        views._table_or_none(groups, "No family links found in the processed events.")
    matches = [{"Person": person["name_as_printed"], "In event": event["spec"].company, "Also in": match["company"],
                "Role there": match.get("role") or "unknown", "Amount there": match.get("amount") or "unknown",
                "Strength": match["match_strength"], "Reason": match["reason"]}
               for event in done for person in event["out"]["people"]["people"] for match in person.get("follow_on") or []]
    with st.container(key="panel-follow-on-all"):
        c_html(c.panel_head("Seen in more than one event"))
        views._table_or_none(matches, "No person matches across the processed events yet. Process more events "
                                      "from Reports; matches appear here automatically.")
        st.caption("Stop rules: " + "; ".join(STOP_RULES) + ".")


# ---------- Reports ----------

def reports(events: list[dict], outputs: Path, unlocked: bool, run_pipeline, new_event_form) -> None:
    """Cost and time per event, one event's report and files, then the pipeline when unlocked."""
    done = data.processed(events)
    with st.container(key="panel-cost-all"):
        _cost_panel(events, outputs)
    with st.container(key="panel-time-all"):
        _time_panel(events)
    event = _event_picker(done, "reports_event")
    if event:
        _report_panel(event, outputs)
    with st.container(key="panel-pipeline"):
        c_html(c.panel_head("Pipeline", "runs cost money, so they need the password in the profile menu"))
        if not unlocked:
            st.caption("Locked. Enter the password in the profile menu (top right) to run an event or add one.")
            return
        files = {item["spec"].event_id: item for item in events}
        target = st.selectbox("Event file to run", list(files), key="run_event",
                              format_func=lambda key: f"{files[key]['spec'].company} ({key})")
        if st.button("Run full pipeline", type="primary", key="run-button", icon=":material/play_arrow:"):
            run_pipeline(files[target]["path"])
        new_event_form()


def _cost_panel(events: list[dict], outputs: Path) -> None:
    """Cost per event beside the runs history; clicking an event filters the history."""
    charts.head("Cost per event", "This run and the no-cache cost of each event's last run, as stored in "
                "cost.json; cost per callable person is in the tooltip.")
    rows = data.cost_rows(events)
    if not rows:
        st.caption("No cost.json yet. Run an event below to record its cost.")
        return
    left, right = st.columns([1.5, 1])
    with left:
        chosen = charts.picked(charts.show(charts.cost_chart(rows), pd.DataFrame(rows),
                                           key=f"cost-{st.session_state['cost_v']}", table_key="cost-table"),
                               "event", "company")
    with right:
        ids = {row["company"]: row["event_id"] for row in rows}
        chips([(f"Event: {chosen}", bump, ("cost_v",))] if chosen else [], "cost")
        history = [run for event_id in ([ids[chosen]] if chosen else list(ids.values()))
                   for run in views._runs_history(event_id, outputs / "runs.csv")]
        c_html(c.tag("div", f"Runs history{'' if chosen is None else ' for ' + chosen}: {len(history)} runs",
                     cls="mc-label"))
        views._table_or_none([{"Event": run.get("event_id"), "Started": run.get("started_at"),
                               "Seconds": run.get("wall_s"), "Calls": run.get("n_llm_calls"),
                               "Cached": run.get("n_cached_calls"), "Cost US$": run.get("total_cost_usd"),
                               "Status": run.get("status")} for run in history],
                             "No runs recorded for this event.")


def _time_panel(events: list[dict]) -> None:
    """Pipeline time by step beside the chosen event's step table."""
    charts.head("Pipeline time by step", "Seconds per step in each event's last full run (timeline.json).")
    rows = data.time_rows(events)
    if not rows:
        st.caption("No timeline.json yet. A full run (--step all) records one.")
        return
    left, right = st.columns([1.5, 1])
    with left:
        chosen = charts.picked(charts.show(charts.time_chart(rows), pd.DataFrame(rows),
                                           key=f"time-{st.session_state['time_v']}", table_key="time-table"),
                               "event", "company")
    with right:
        chips([(f"Event: {chosen}", bump, ("time_v",))] if chosen else [], "time")
        steps = [row for row in rows if chosen is None or row["company"] == chosen]
        c_html(c.tag("div", "Steps" + ("" if chosen is None else f" for {chosen}"), cls="mc-label"))
        st.dataframe(pd.DataFrame([{"Event": row["company"], "Step": row["step"], "Seconds": round(row["seconds"], 1),
                                    "Calls": row["calls"], "Cached": row["cached"]} for row in steps]),
                     hide_index=True, width="stretch", height=240)


def _report_panel(event: dict, outputs: Path) -> None:
    """The event's report.md, downloads, and its per-person cost detail."""
    spec = event["spec"]
    with st.container(key="panel-report"):
        c_html(c.panel_head("Report", "the same figures as the call list, as Markdown"))
        downloads = st.columns(2)
        for column, name, mime in ((downloads[0], "report.md", "text/markdown"),
                                   (downloads[1], "people.json", "application/json")):
            path = outputs / spec.event_id / name
            if path.is_file():
                column.download_button(f"Download {name}", path.read_bytes(), file_name=f"{spec.event_id}_{name}",
                                       mime=mime, icon=":material/download:", key=f"dl-{name}",
                                       on_click=_toast_download, args=(name,))
            else:
                column.caption(f"{name}: not written yet. Run this event's report step.")
        report = outputs / spec.event_id / "report.md"
        if report.is_file():
            with st.expander("Read the report here"):
                st.markdown(report.read_text(encoding="utf-8").replace("$", "\\$"))
        with st.expander("Cost per person and last run, for this event"):
            views.cost_tab(event["out"], spec.event_id, outputs / "runs.csv")


def _toast_download(name: str) -> None:
    """Confirm a download on the next run."""
    queue_toast(f"{name} downloaded", ":material/download_done:")


def _event_picker(done: list[dict], key: str) -> dict | None:
    """A select box over the processed events; returns the chosen one."""
    if not done:
        st.info("No processed events yet. Open Reports, unlock the pipeline in the profile menu, and run an event.")
        return None
    names = {event["spec"].event_id: event for event in done}
    if st.session_state.get(key) not in names:
        st.session_state[key] = next(iter(names))
    chosen = st.selectbox("Event", list(names), key=key, format_func=lambda event_id: names[event_id]["spec"].company)
    return names[chosen]


# ---------- Live feed ----------

FEED_SECTIONS = (("today", "Today"), ("upcoming", "Upcoming"), ("recent", "Last 30 days"))
FEED_FILTERS = {"all": "Everything", "ready": "Call list ready", "waiting": "Supported, not processed",
                "failed": "Processing failed", "unsupported": "Detected; not supported yet"}


def live_feed(events: list[dict], outputs: Path, unlocked: bool, run_pipeline) -> None:
    """Every discovered item: Today / Upcoming / Last 30 days, with its status and the next step."""
    discovery = data.read_discovery(outputs)
    with st.container(key="panel-feed-head"):
        _feed_head(discovery, events)
    with st.expander("Add any event from a link", expanded=bool(st.session_state.pop("add_open", False)
                                                               or st.session_state.get("add_proposals"))):
        add_event_panel(events, unlocked, run_pipeline)
    if not discovery:
        st.info("Discovery has not run yet, so there is nothing to show. Run `python discover.py --since 30d` "
                "locally; the scheduled GitHub workflow runs it every 3 hours.")
        return
    rows = data.feed_rows(discovery, events, data.read_discovery_log(outputs), date.today())
    which = st.segmented_control("Show", list(FEED_FILTERS), key="feed_filter", default="all",
                                 format_func=FEED_FILTERS.get) or "all"
    for key, title in FEED_SECTIONS:
        shown = [row for row in rows[key] if which in ("all", row["status"])]
        st.markdown(f"#### {title} · {len(shown)}")
        if not shown:
            st.caption({"today": "Nothing published today in the enabled sources yet.",
                        "upcoming": "No processed event has a money date after today.",
                        "recent": "Nothing in the last 30 days matches this filter."}[key])
        for index, row in enumerate(shown):
            _feed_item(row, f"{key}-{index}", unlocked, run_pipeline, outputs)


def _feed_head(discovery: dict | None, events: list[dict]) -> None:
    """The header line, a warning per failed source, and every source with its reason."""
    header = data.feed_header(discovery, events)
    c_html(c.chart_head_html("Live feed", "Money events found in official public sources. Only sources whose "
                             "terms allow automated reading are read; the feed links to them and republishes nothing."))
    c_html(c.feed_header_html(header))
    c_html(c.tag("div", c.join([c.tag("b", "Coverage: "), data.COVERAGE]), cls="mc-note"))
    for source in header["problems"]:
        st.warning(f"{source['name']}: {source['status']}. {source['reason']} Its items are missing from this refresh.")
    if discovery:
        with st.expander("Sources, and why each is on or off"):
            for source in discovery.get("sources") or []:
                note = f" ({source['note']})" if source.get("note") else ""
                st.markdown(f"- **{source['name']}**: {source['status']}, {source['items']} items{note}. "
                            f"{source['reason']} [Terms]({source['terms_url']})")


def _feed_item(row: dict, key: str, unlocked: bool, run_pipeline, outputs: Path) -> None:
    """One row and its next step: open the call list, or (with the password) process it now."""
    with st.container(key=f"card-feed-{key}"):
        left, right = st.columns([5, 1.5], vertical_alignment="center")
        with left:
            c_html(c.feed_item_row_html(row))
        with right:
            if row["status"] == "ready":
                st.button("Open call list →", key=f"feed-open-{key}", on_click=go,
                          args=("prospects", row["event_id"], "all"))
            elif row["processable"] and unlocked:
                label = "Process again" if row["status"] == "failed" else "Process now"
                if st.button(label, key=f"feed-run-{key}", type="primary", icon=":material/play_arrow:"):
                    _process_now(row, run_pipeline, outputs)
            elif row["processable"]:
                st.caption("Unlock in the profile menu to process.")


def _process_now(row: dict, run_pipeline, outputs: Path) -> None:
    """Run the pipeline with live progress, then record the result in outputs/discovery_log.json."""
    from tools.discover import docs_hash, record

    code = run_pipeline(row["event"]["path"])
    record(outputs, {"event_id": row["event_id"], "docs_hash": docs_hash(row["summary"].get("documents") or []),
                     "status": "ok" if code == 0 else "failed", "via": "app",
                     "reason": "" if code == 0 else f"run.py exited with code {code}; see the run log above",
                     "at": date.today().isoformat()})
    st.button("Show the updated feed", key=f"feed-refresh-{row['event_id']}")


def feed_compact(events: list[dict], outputs: Path) -> None:
    """Home's short version: the header line and the five newest items, with their status."""
    discovery = data.read_discovery(outputs)
    head, link = st.columns([4, 1], vertical_alignment="center")
    with head:
        c_html(c.chart_head_html("Live feed", "Newest money events found in official public sources."))
        c_html(c.feed_header_html(data.feed_header(discovery, events)))
    link.button("Open live feed →", key="feed-view-all", type="tertiary", on_click=go, args=("feed",))
    rows = data.feed_rows(discovery, events, data.read_discovery_log(outputs), date.today())
    newest = sorted(rows["today"] + rows["upcoming"] + rows["recent"],
                    key=lambda row: row["item"]["published_iso"], reverse=True)[:5]
    if not discovery:
        st.caption("Discovery has not run yet. Run `python discover.py --since 30d`.")
    elif not newest:
        st.caption("No items in the last 30 days from the enabled sources.")
    for index, row in enumerate(newest):
        with st.container(key=f"card-feedhome-{index}"):
            c_html(c.feed_item_row_html(row))


# ---------- Add any event (Live feed, and Ctrl+K "Add event from a link") ----------

MAX_LINKS = 5
EVENT_TYPE_CHOICES = ("ipo", "buyback", "ofs_stock_exchange")


def add_event_panel(events: list[dict], unlocked: bool, run_pipeline) -> None:
    """Paste PDF links; the app proposes each document's type, the company and the event type, with quotes.

    Every field can be edited. "Check" reads the documents (no model call); "Build call list" is
    password-gated. An event already in the app is opened, not duplicated.
    """
    from tools.propose import propose

    c_html(c.chart_head_html("Add any event", "Paste one or more PDF links (an RHP, prospectus, letter of offer or "
                             "announcement). The app reads the first pages and proposes what each is."))
    links = st.text_area("PDF links, one per line", key="add_links", height=90,
                         placeholder="https://www.sebi.gov.in/sebi_data/attachdocs/....pdf")
    urls = [line.strip() for line in links.splitlines() if line.strip()][:MAX_LINKS]
    if st.button("Read the documents", key="add-read", icon=":material/description:", disabled=not urls):
        with st.spinner("Fetching and reading the first pages…"):
            st.session_state["add_proposals"] = [propose(url) for url in urls]
        st.session_state.pop("add_check", None)
    proposals = [item for item in st.session_state.get("add_proposals") or [] if item["url"] in urls]
    if not proposals:
        st.caption("Nothing read yet. Paste links and press Read the documents.")
        return
    documents = _proposal_editors(proposals)
    readable = [document for document in documents if document["doc_type"]]
    first = next((item for item in proposals if item.get("company")), {})
    company = st.text_input("Company as printed", value=first.get("company") or "", key="add_company")
    if first.get("company_quote"):
        st.caption(f"From the page: “{first['company_quote'][:200]}”")
    proposed_type = next((item["event_type"] for item in proposals if item.get("event_type")), "ipo")
    event_type = st.selectbox("Event type", EVENT_TYPE_CHOICES, key="add_event_type",
                              index=EVENT_TYPE_CHOICES.index(proposed_type) if proposed_type in EVENT_TYPE_CHOICES else 0)
    if not readable or not company.strip():
        st.warning("Give at least one document a type and the company a name to continue.")
        return
    month = date.today().strftime("%Y%m")
    existing = _existing(readable, company, event_type, month)
    if existing:
        _existing_event_actions(existing, events, unlocked, run_pipeline)
        return
    _new_event_actions(readable, company.strip(), event_type, month, unlocked, run_pipeline)


def _proposal_editors(proposals: list[dict]) -> list[dict]:
    """One row per document: its proposed type (editable) and the quote it came from, or why it was not read."""
    documents = []
    for index, item in enumerate(proposals):
        name = item["url"].rsplit("/", 1)[-1][:70]
        if item.get("error"):
            st.error(f"{name}: {item['error']}")
            continue
        choices = ["(not used)"] + [doc for doc in ("rhp", "prospectus", "letter_of_offer", "public_announcement",
                                                    "announcement")]
        chosen = st.selectbox(f"Document type for {name}", choices, key=f"add-type-{index}",
                              index=choices.index(item["doc_type"]) if item.get("doc_type") in choices else 0)
        how = "rules" if item.get("how") == "rules" else "the cheap model (quote checked on the page)"
        if item.get("type_quote"):
            st.caption(f"Proposed by {how} ({item.get('label') or 'type'}): “{item['type_quote'][:200]}”")
        else:
            st.caption("No rule or model settled the type; choose it yourself.")
        documents.append({"url": item["url"], "doc_type": None if chosen == "(not used)" else chosen})
    return documents


def _existing(documents: list[dict], company: str, event_type: str, month: str) -> str | None:
    """The id of the event already in the app for these documents, or this company, type and month."""
    from tools.propose import existing_event

    return existing_event([document["url"] for document in documents], company, event_type, month)


def _existing_event_actions(event_id: str, events: list[dict], unlocked: bool, run_pipeline) -> None:
    """Open the event that already exists, or (with the password) check and rebuild it from the cache."""
    event = next((item for item in events if item["spec"].event_id == event_id), None)
    if event is None:
        st.info(f"This event is already in the app ({event_id}) but its file could not be read.")
        return
    st.info(f"Already in the app: {event['spec'].company} ({event_id}). Opening it instead of making a duplicate.")
    cols = st.columns(3)
    if event["processed"]:
        cols[0].button("Open call list →", key="add-open-existing", type="primary", on_click=go,
                       args=("prospects", event_id, "all"))
    if cols[1].button("Check", key="add-check-existing", icon=":material/fact_check:"):
        _show_check(event["path"], event_id)
    if unlocked and cols[2].button("Rebuild call list", key="add-build-existing", icon=":material/play_arrow:"):
        _build(event["path"], event_id, run_pipeline)
    elif not unlocked:
        cols[2].caption("Unlock in the profile menu to rebuild.")


def _new_event_actions(documents: list[dict], company: str, event_type: str, month: str, unlocked: bool,
                       run_pipeline) -> None:
    """Check the proposed event (no model call), then build it with the password."""
    from pydantic import ValidationError

    from agents.spec import EventSpec
    from tools.discover import slug

    event_id = f"{slug(company)}_{event_type}_{month}"
    payload = {"event_id": event_id, "event_type": event_type, "company": company,
               "documents": [{"url": doc["url"], "doc_type": doc["doc_type"], "note": "added from a link"}
                             for doc in documents]}
    try:
        EventSpec.model_validate(payload)
    except ValidationError as exc:
        st.error(f"This event is not valid yet: {exc}")
        return
    st.caption(f"New event: {event_id}")
    draft = Path("cache") / "drafts" / f"{event_id}.json"
    cols = st.columns(2)
    if cols[0].button("Check", key="add-check", icon=":material/fact_check:"):
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _show_check(draft, event_id)
    if not unlocked:
        cols[1].caption("Building a call list costs money: unlock in the profile menu first.")
        return
    if cols[1].button("Build call list", key="add-build", type="primary", icon=":material/play_arrow:"):
        path = Path("events") / f"{event_id}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _build(path, event_id, run_pipeline)


def _show_check(path: Path, event_id: str) -> None:
    """Run `run.py --step check` and show its result as pass / warning / fail lines."""
    from tools.discover import run_check

    with st.spinner("Checking the documents (no model call)…"):
        report, error = run_check(path, event_id)
    if error:
        st.error(f"The check could not run: {error}")
    c_html(c.check_lines_html(data.check_lines(report)))


def _build(path: Path, event_id: str, run_pipeline) -> None:
    """Run the pipeline with live progress; on success open the Prospects card list for the event."""
    from tools.discover import outcome_problem

    code = run_pipeline(path)
    problem = outcome_problem(Path("outputs") / event_id) if code == 0 else f"run.py exited with code {code}"
    if problem:
        st.error(f"No call list: {problem}")
        return
    st.success("Call list ready.")
    st.button("Open the call list →", key="add-open-built", type="primary", on_click=go,
              args=("prospects", event_id, "all"))
