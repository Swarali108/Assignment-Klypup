"""Every chart in the app, in one style, with one helper to draw it.

Style: thin rules or bars with small filled points, faint dotted horizontal gridlines
only, muted labels, no axis lines, 240 px high. Colours have fixed meanings:
lavender = cash / verified, champagne = scheduled, teal (dashed) = estimate (shares,
not cash), grey = unknown. Legends always use words.

panel() draws the title, a one-line subtitle naming what is counted and from which
file, an optional range pill, the chart (click selects, double-click clears) and a
"Show as table" toggle. Charts only count or sum stored values; every tooltip carries
the stored display text.
"""

from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from ui import components as c
from ui import dashboard_data as data
from ui.styles import CHAMPAGNE, IVORY, LAVENDER, MUTED, PEACH, TEAL

GREY = "#8d93a1"
DIM = "#5b6170"
FONT = "Inter, system-ui, sans-serif"
HEIGHT = 240
TYPE_COLOURS = {"IPO": LAVENDER, "Buyback": PEACH, "OFS (stock exchange)": TEAL}
# Legend words for each timing group, so colour never carries the meaning alone.
GROUP_WORDS = {
    "In hand": "In hand (cash)",
    "Scheduled": "Scheduled (cash on a printed date)",
    "Locked": "Locked (shares, estimate)",
    "Unlocked": "Unlocked (shares, estimate)",
    "Not applicable": "Not applicable",
    "Unknown": "Unknown",
}
# Short words on the range pill, so it fits on one line.
RANGE_WORDS = {"Past 90 days": "Past 90d", "Next 90 days": "Next 90d"}
ROLE_COLOURS = {"cash": LAVENDER, "scheduled": CHAMPAGNE, "estimate": TEAL, "unknown": GREY}


# ---------- shared style and panel ----------

def style(chart: alt.TopLevelMixin, height: int = HEIGHT) -> alt.TopLevelMixin:
    """Transparent, dotted horizontal grid, no axis lines, muted words, legend underneath."""
    return (chart.properties(height=height, background="transparent")
            .configure_view(stroke=None)
            .configure_axis(domain=False, ticks=False, grid=False, labelColor=MUTED, titleColor=MUTED,
                            labelFont=FONT, titleFont=FONT, labelFontSize=11, titleFontSize=11, labelPadding=6)
            .configure_axisY(grid=True, gridDash=[1, 4], gridColor="rgba(241,236,227,0.18)")
            .configure_legend(orient="bottom", direction="horizontal", labelColor="#ddd6ca", titleColor=MUTED,
                              labelFont=FONT, labelFontSize=11, labelLimit=320, symbolSize=70, columns=2)
            .configure_text(font=FONT))


def head(title: str, subtitle: str, ranges: list[str] | None = None, key: str | None = None,
         default: str | None = None) -> str | None:
    """Title, subtitle and, when ranges are given, a small range pill on the right. Returns the range."""
    if not ranges:
        c_html(c.chart_head_html(title, subtitle))
        return None
    left, right = st.columns([1.45, 1], vertical_alignment="top")
    with left:
        c_html(c.chart_head_html(title, subtitle))
    with right, st.container(key=f"pill-{key}"):
        chosen = st.segmented_control("Range", ranges, default=default, key=key, label_visibility="collapsed",
                                      format_func=lambda label: RANGE_WORDS.get(label, label))
    return chosen or default


def show(chart: alt.TopLevelMixin, table: pd.DataFrame, key: str, table_key: str, height: int = HEIGHT):
    """The styled chart with click-to-select, then the "Show as table" toggle. Returns the selection."""
    event = st.altair_chart(style(chart, height), key=key, on_select="rerun", theme=None, width="stretch")
    if st.toggle("Show as table", key=table_key):
        st.dataframe(table, hide_index=True, width="stretch")
    return event


def picked(event: object, name: str, field: str) -> str | None:
    """The clicked value from a chart's selection, or None. Streamlit returns {name: [{field: value}]}."""
    selection = getattr(event, "selection", None) or {}
    chosen = selection.get(name) if isinstance(selection, dict) else getattr(selection, name, None)
    if not chosen:
        return None
    first = chosen[0] if isinstance(chosen, list) else chosen
    return first.get(field) if isinstance(first, dict) else None


def c_html(fragment: c.Html) -> None:
    """Draw one escaped fragment from ui/components.py."""
    st.markdown(fragment, unsafe_allow_html=True)


# ---------- Home: money becoming available ----------

def money_chart(rows: list[dict], today: date, start: date | None, end: date | None) -> alt.TopLevelMixin:
    """₹ crore per stored date: a thin stem and a point per (date, series); a dotted 'today' rule."""
    frame = pd.DataFrame(rows)
    dates = [date.fromisoformat(row["date"]) for row in rows] + [today]
    low = start or min(dates) - timedelta(days=20)
    high = end or max(dates) + timedelta(days=20)
    pick = alt.selection_point(name="pick", fields=["key"], on="click", clear="dblclick")
    x = alt.X("date:T", title=None, scale=alt.Scale(domain=[low.isoformat(), high.isoformat()]),
              axis=alt.Axis(format="%d %b %y", labelAngle=0, tickCount=5))
    y = alt.Y("crore:Q", title="₹ crore", axis=alt.Axis(format=",.0f", tickCount=4))
    colour = alt.Color("status:N", title=None, scale=alt.Scale(
        domain=[data.VERIFIED_DATE, data.SCHEDULED_DATE, data.ESTIMATE], range=[LAVENDER, CHAMPAGNE, TEAL]))
    tooltip = [alt.Tooltip("date:T", title="Date", format="%d %b %Y"), alt.Tooltip("kind:N", title="What"),
               alt.Tooltip("status:N", title="Series"), alt.Tooltip("crore_text:N", title="Amount"),
               alt.Tooltip("people:Q", title="People"), alt.Tooltip("who:N", title="Stored amounts")]
    layers = []
    if not frame.empty:
        base = alt.Chart(frame).encode(x=x)
        stems = base.mark_rule(strokeWidth=1.6).encode(
            y=y, y2=alt.datum(0), color=colour,
            strokeDash=alt.StrokeDash("series:N", legend=None,
                                      scale=alt.Scale(domain=[data.CASH, data.ESTIMATE], range=[[1, 0], [4, 3]])))
        points = base.mark_circle(size=70, opacity=1).encode(
            y=y, color=colour, tooltip=tooltip,
            size=alt.condition(pick, alt.value(120), alt.value(70)),
        ).add_params(pick)
        layers += [stems, points]
    marker = pd.DataFrame([{"date": today.isoformat(), "label": "today"}])
    rule = alt.Chart(marker).mark_rule(color=IVORY, strokeDash=[2, 3], opacity=0.5).encode(x=x)
    words = alt.Chart(marker).mark_text(color=MUTED, align="left", dx=4, dy=-4, baseline="top", fontSize=11).encode(
        x=x, y=alt.value(0), text="label:N")
    return alt.layer(*layers, rule, words)


# ---------- Home: event mix ----------

def donut_chart(mix: list[dict]) -> alt.TopLevelMixin:
    """Events by type as a donut with the total in the middle; a slice can be clicked."""
    frame = pd.DataFrame(mix)
    pick = alt.selection_point(name="type", fields=["type"], on="click", clear="dblclick")
    colours = alt.Scale(domain=list(TYPE_COLOURS), range=list(TYPE_COLOURS.values()))
    arcs = alt.Chart(frame).mark_arc(innerRadius=62, outerRadius=88, cornerRadius=3, padAngle=0.02).encode(
        theta=alt.Theta("events:Q"), color=alt.Color("type:N", scale=colours, legend=None),
        opacity=alt.condition(pick, alt.value(1), alt.value(0.45)),
        tooltip=[alt.Tooltip("type:N", title="Type"), alt.Tooltip("events:Q", title="Events"),
                 alt.Tooltip("people:Q", title="Callable people"), alt.Tooltip("share:Q", title="Share of events %")],
    ).add_params(pick)
    total = int(frame["events"].sum()) if not frame.empty else 0
    middle = alt.Chart(pd.DataFrame([{"t": str(total)}])).mark_text(
        font="Cormorant Garamond, Georgia, serif", fontSize=34, color=IVORY, dy=-6).encode(text="t:N")
    under = alt.Chart(pd.DataFrame([{"t": "events"}])).mark_text(fontSize=12, color=MUTED, dy=18).encode(text="t:N")
    return alt.layer(arcs, middle, under)


# ---------- Prospects: money by person ----------

def person_bars(rows: list[dict]) -> alt.TopLevelMixin:
    """Stored money_now_crore per shown person, thin bars with a point at the end, coloured by timing."""
    frame = pd.DataFrame(rows)
    pick = alt.selection_point(name="person", fields=["person_key"], on="click", clear="dblclick")
    order = list(frame["label"]) if not frame.empty else []
    colour = alt.Color("legend:N", title=None, scale=alt.Scale(
        domain=list(GROUP_WORDS.values()),
        range=[ROLE_COLOURS[data.GROUP_ROLE[group]] for group in GROUP_WORDS]))
    y = alt.Y("label:N", title=None, sort=order, axis=alt.Axis(labelLimit=190))
    x = alt.X("crore:Q", title="₹ crore (stored money_now_crore)", axis=alt.Axis(format=",.0f", tickCount=4))
    tooltip = [alt.Tooltip("name:N", title="Name"), alt.Tooltip("company:N", title="Company"),
               alt.Tooltip("money_text:N", title="Money now"), alt.Tooltip("trigger:N", title="From"),
               alt.Tooltip("amount_display:N", title="Card amount"), alt.Tooltip("legend:N", title="Timing")]
    base = alt.Chart(frame).encode(y=y, x=x, color=colour, tooltip=tooltip)
    bars = base.mark_bar(size=6, cornerRadiusEnd=3).encode(opacity=alt.condition(pick, alt.value(1), alt.value(0.6)))
    points = base.mark_circle(size=55, opacity=1).add_params(pick)
    return alt.layer(bars, points)


# ---------- Insights: verification funnel ----------

FUNNEL_WORDS = {"kept": "kept: verified on its page", "rejected": "rejected: failed a check",
                "unattributed": "unattributed: name not verified"}


def funnel_chart(rows: list[dict]) -> alt.TopLevelMixin:
    """Per section, the proposed fields split into kept / rejected / unattributed (stored counts)."""
    long = [{"section": row["section"], "part": FUNNEL_WORDS[part], "count": row[part], "proposed": row["proposed"],
             "reasons": row["reasons"], "order": index}
            for row in rows for index, part in enumerate(FUNNEL_WORDS) if row[part]]
    frame = pd.DataFrame(long)
    pick = alt.selection_point(name="section", fields=["section"], on="click", clear="dblclick")
    colour = alt.Color("part:N", title=None, scale=alt.Scale(domain=list(FUNNEL_WORDS.values()),
                                                             range=[LAVENDER, GREY, DIM]))
    return alt.Chart(frame).mark_bar(size=12, cornerRadiusEnd=2).encode(
        y=alt.Y("section:N", title=None, sort=[row["section"] for row in rows]),
        x=alt.X("count:Q", title="fields", stack="zero", axis=alt.Axis(tickCount=4, format="d")),
        color=colour, order=alt.Order("order:Q"),
        opacity=alt.condition(pick, alt.value(1), alt.value(0.55)),
        tooltip=[alt.Tooltip("section:N", title="Section"), alt.Tooltip("part:N", title="Part"),
                 alt.Tooltip("count:Q", title="Fields"), alt.Tooltip("proposed:Q", title="Proposed"),
                 alt.Tooltip("reasons:N", title="Rejection reasons")],
    ).add_params(pick)


# ---------- Reports: cost and time ----------

COST_WORDS = {"this run": "this run (cached calls cost 0)", "no cache": "no cache (estimate from earlier uncached calls)"}


def cost_chart(rows: list[dict]) -> alt.TopLevelMixin:
    """Per event: this run's cost and the no-cache cost, both as stored in cost.json."""
    long = [{"company": row["company"], "measure": COST_WORDS[measure], "usd": row[measure] or 0.0,
             "usd_text": f"${(row[measure] or 0.0):.6f}", "per_text": f"${(row[f'per callable ({measure})'] or 0.0):.6f}",
             "run_id": row["run_id"] or "unknown"}
            for row in rows for measure in ("this run", "no cache")]
    frame = pd.DataFrame(long)
    pick = alt.selection_point(name="event", fields=["company"], on="click", clear="dblclick")
    colour = alt.Color("measure:N", title=None, scale=alt.Scale(domain=list(COST_WORDS.values()), range=[LAVENDER, TEAL]))
    return alt.Chart(frame).mark_bar(size=14, cornerRadiusEnd=2).encode(
        x=alt.X("company:N", title=None, axis=alt.Axis(labelAngle=0, labelLimit=150)),
        xOffset="measure:N", y=alt.Y("usd:Q", title="US$", axis=alt.Axis(format="$.3f", tickCount=4)),
        color=colour, opacity=alt.condition(pick, alt.value(1), alt.value(0.55)),
        tooltip=[alt.Tooltip("company:N", title="Event"), alt.Tooltip("measure:N", title="Cost"),
                 alt.Tooltip("usd_text:N", title="Stored"), alt.Tooltip("per_text:N", title="Per callable person"),
                 alt.Tooltip("run_id:N", title="Run")],
    ).add_params(pick)


STEP_COLOURS = ["#c9b6f2", "#a99bd6", "#e9cfa5", "#cfb48c", "#6cc5b8", "#4f9c91"]


def time_chart(rows: list[dict]) -> alt.TopLevelMixin:
    """Per event, the last full run's seconds per step, stacked."""
    frame = pd.DataFrame([{**row, "seconds_text": f"{row['seconds']:.1f} s"} for row in rows])
    steps = list(dict.fromkeys(row["step"] for row in rows))
    pick = alt.selection_point(name="event", fields=["company"], on="click", clear="dblclick")
    return alt.Chart(frame).mark_bar(size=14, cornerRadiusEnd=2).encode(
        y=alt.Y("company:N", title=None, axis=alt.Axis(labelLimit=170)),
        x=alt.X("seconds:Q", title="seconds", stack="zero", axis=alt.Axis(tickCount=4)),
        color=alt.Color("step:N", title=None, scale=alt.Scale(domain=steps, range=STEP_COLOURS[:len(steps)]), sort=steps),
        order=alt.Order("step_order:Q"), opacity=alt.condition(pick, alt.value(1), alt.value(0.55)),
        tooltip=[alt.Tooltip("company:N", title="Event"), alt.Tooltip("step:N", title="Step"),
                 alt.Tooltip("seconds_text:N", title="Time"), alt.Tooltip("calls:Q", title="Model calls"),
                 alt.Tooltip("cached:Q", title="Cached")],
    ).transform_calculate(step_order=f"indexof({steps!r}, datum.step)").add_params(pick)
