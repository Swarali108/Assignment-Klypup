"""Page sections: header, KPI row, call-list cards, follow-on, what we didn't trust, cost.

Each function reads the loaded outputs and draws; none computes a figure. HTML comes
only from ui/components.py, which escapes every value taken from a document.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from tools.people_index import STOP_RULES
from ui import components as c

CONFIDENCE_LEVELS = ("high", "medium", "low")


def html(fragment: c.Html, where=st) -> None:
    """Draw one fragment built by ui/components.py."""
    where.markdown(fragment, unsafe_allow_html=True)


def header(spec, out: dict) -> None:
    """The event block: company, type, documents, price basis, listing date."""
    documents = [document.model_dump() for document in spec.documents]
    html(c.event_block(spec.company, spec.event_type, spec.event_id, documents, out["people"]))


def kpi_row(out: dict) -> None:
    """Four KPI cards from ranked.json and cost.json."""
    for column, card in zip(st.columns(4), c.kpi_cards(out["ranked"], out["cost"])):
        html(card, column)
    st.write("")


def people_tab(out: dict, key: str, people_only_filter: bool) -> None:
    """Filters and a Table view toggle, then cards (or the table) for ranked.json[key]."""
    entries = list((out["ranked"] or {}).get(key) or [])
    if not entries:
        st.write("None.")
        return
    shown = _filtered(entries, key, people_only_filter)
    if not shown:
        st.write("No one matches these filters.")
    elif st.session_state.get(f"{key}_table_view"):
        _table(shown, out, key)
    else:
        for index, entry in enumerate(shown):
            _card(entry, out, f"card-{key}-{index}")


def _filtered(entries: list[dict], key: str, people_only_filter: bool) -> list[dict]:
    """The filter row; returns the entries that pass it, in rank order."""
    columns = st.columns([1, 1.4, 2, 1])
    people_only = columns[0].checkbox("People only", key=f"{key}_people") if people_only_filter else False
    minimum = columns[1].number_input("Minimum money now (₹ crore)", min_value=0.0, value=0.0, key=f"{key}_min")
    levels = columns[2].multiselect("Confidence", CONFIDENCE_LEVELS, default=list(CONFIDENCE_LEVELS), key=f"{key}_conf")
    columns[3].toggle("Table view", key=f"{key}_table_view")
    return [
        entry for entry in entries
        if (not people_only or entry["holder_type"] == "person")
        and Decimal(entry["money_now_crore"]) >= Decimal(str(minimum))
        and entry["confidence"] in levels
    ]


def _card(entry: dict, out: dict, key: str) -> None:
    """One card with an expander for the brief, workings and evidence."""
    with st.container(key=key):
        html(c.card_html(entry))
        with st.expander("Brief, workings and evidence"):
            _detail(entry, out)


def _detail(entry: dict, out: dict) -> None:
    """The detail HTML for one ranked entry."""
    people = {person["person_id"]: person for person in out["people"]["people"]}
    briefs = {brief["person_id"]: brief for brief in (out["briefs"] or {}).get("briefs") or []}
    html(c.detail_html(entry, people[entry["person_id"]], briefs.get(entry["person_id"])))


def _table(shown: list[dict], out: dict, key: str) -> None:
    """The plain table; selecting a row shows its detail below."""
    table = pd.DataFrame([_table_row(entry) for entry in shown])
    event = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun",
                         selection_mode="single-row", key=f"{key}_table")
    rows = event.selection.rows if event is not None else []
    if not rows:
        st.caption("Click a row to see the brief, workings and evidence.")
        return
    with st.container(key=f"panel-{key}-detail"):
        html(c.card_html(shown[rows[0]]))
        _detail(shown[rows[0]], out)


def _table_row(entry: dict) -> dict:
    """One row of the table view. A missing value reads "unknown"."""
    return {
        "Rank": entry["rank"],
        "Name": entry["name_as_printed"],
        "Type": entry["holder_type"],
        "Role": entry.get("role_as_printed") or "unknown",
        "Why money": entry["why_money"],
        "Amount": entry["amount_display"],
        "Timing": entry["timing_display"],
        "Confidence": entry["confidence"],
    }


def follow_on_tab(out: dict) -> None:
    """Every cross-event match with its strength, and the stop rules that bound the search."""
    people = (out["people"] or {}).get("people") or []
    rows = [
        {"Person": person["name_as_printed"], "Other event": match["event_id"], "Company": match["company"],
         "Role there": match["role"] or "unknown", "Amount there": match["amount"] or "unknown",
         "Trigger date": match["trigger_date"] or "unknown", "Strength": match["match_strength"], "Reason": match["reason"]}
        for person in people
        for match in person.get("follow_on") or []
    ]
    counts = (out["people"] or {}).get("counts") or {}
    with st.container(key="panel-follow-on"):
        st.caption(f"Index lookups: {counts.get('index_lookups', 'unknown')}; "
                   f"matches: {counts.get('follow_on_matches', 'unknown')}")
        _table_or_none(rows, "No matches in other processed events.")
        st.caption("Stop rules: " + "; ".join(STOP_RULES) + ".")


def distrust_tab(out: dict) -> None:
    """Completeness lines, unattributed rows, rejections by reason, identity decisions."""
    extracted = out["extract"] or {}
    with st.container(key="panel-distrust"):
        html(c.section("Holder table completeness", c.completeness_html(extracted.get("completeness") or {})))
        html(c.section("Unattributed rows", c.tag("div", "Name failed verification; their amounts are not used.",
                                                  cls="mc-note")))
        _table_or_none([{"Section": row.get("section"), "Name": row.get("name_as_printed"), "Reason": row.get("reason")}
                        for row in extracted.get("unattributed") or []])
        html(c.section("Rejected fields by reason", ""))
        rejections = pd.DataFrame(extracted.get("rejections") or [])
        if rejections.empty:
            st.write("none")
        else:
            counts = rejections.groupby(["section", "reason"]).size().reset_index(name="count")
            st.dataframe(counts, hide_index=True, width="content")
        html(c.section("Identity decisions sent to the model", ""))
        log = (out["people"] or {}).get("identity_log") or []
        sent = [{"Pair": " / ".join(item["pair"]), "Score": item["score"], "Model said": item.get("llm_outcome") or "unknown",
                 "Reason": item.get("llm_reason") or "unknown"}
                for item in log if str(item.get("method", "")).startswith("llm")]
        _table_or_none(sent, "none: every pair was settled by code")
        if log:
            st.caption("All identity decisions by method")
            st.dataframe(pd.DataFrame(log).groupby("method").size().reset_index(name="pairs"), hide_index=True,
                         width="content")


def cost_tab(out: dict, event_id: str, runs_csv: Path) -> None:
    """This run's totals, the last full run's steps, per person, and the runs history."""
    totals = (out["cost"] or {}).get("totals") or {}
    cards = [
        c.kpi_card("Cost this run", c.usd(totals.get("cost_usd"))),
        c.kpi_card("With no cache", c.usd(totals.get("fresh_usd"))),
        c.kpi_card("Cached calls", f"{totals.get('cached_calls', 'unknown')} of {totals.get('calls', 'unknown')}"),
        c.kpi_card("Wall time", c.unknown("not recorded") if totals.get("wall_s") is None else f"{totals['wall_s']:.1f} s"),
    ]
    for column, card in zip(st.columns(4), cards):
        html(card, column)
    timeline = out["timeline"]
    with st.container(key="panel-cost"):
        if timeline:
            st.markdown(f"**Last full run** ({timeline.get('run_id') or 'unknown'})")
            st.dataframe(pd.DataFrame(timeline["steps"]), hide_index=True)
        st.markdown("**Per person**")
        st.dataframe(pd.DataFrame((out["cost"] or {}).get("per_person") or []), hide_index=True)
        st.markdown("**Runs history**")
        _table_or_none(_runs_history(event_id, runs_csv))


def _table_or_none(rows: list[dict], empty: str = "none") -> None:
    """A table, or a plain word when there are no rows."""
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    else:
        st.write(empty)


def _runs_history(event_id: str, path: Path) -> list[dict]:
    """Rows of outputs/runs.csv for this event, newest first."""
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("event_id") == event_id]
    return list(reversed(rows))
