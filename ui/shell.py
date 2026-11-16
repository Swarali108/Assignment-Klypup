"""The app shell: sidebar navigation, header (greeting, search, notifications, profile), page state.

Plain Streamlit widgets: buttons with help tooltips for navigation (keyboard and screen
reader friendly, and the sidebar becomes a drawer on small screens), popovers for the
notification and profile menus. Only the search box is custom (ui/widgets.py).
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta, timezone

import streamlit as st

from ui import components as c
from ui import widgets

PAGES = {
    "home": ("Home", ":material/home:", "Today's calls: counts, money becoming available, event mix, top calls."),
    "feed": ("Live feed", ":material/rss_feed:",
             "Money events found in official sources (SEBI), newest first, with what was done with each."),
    "prospects": ("Prospects", ":material/group:",
                  "Call lists: who to call, why, how much, when, with the brief and every source page."),
    "insights": ("Insights", ":material/insights:",
                 "Can I trust it? What was verified, what was rejected, and why."),
    "network": ("Network", ":material/hub:", "Family links and people seen in more than one processed event."),
    "reports": ("Reports", ":material/description:", "Report files, cost per run and per person, run history, the pipeline."),
}
ALL_EVENTS = "__all__"


def init_state() -> None:
    """Defaults for the page and filters, and the page from the URL (?page=prospects) on first load."""
    if "page" not in st.session_state:
        wanted = st.query_params.get("page")
        st.session_state["page"] = wanted if wanted in PAGES else "home"
    st.session_state.setdefault("prospects_event", ALL_EVENTS)
    st.session_state.setdefault("prospects_filter", "all")
    st.session_state.setdefault("focus_person", None)
    st.session_state.setdefault("scroll_token", None)
    st.session_state.setdefault("seen_notes", [])
    for key in ("money_v", "mix_v", "bars_v", "funnel_v", "cost_v", "time_v"):
        st.session_state.setdefault(key, 0)


def go(page: str, event: str | None = None, people_filter: str | None = None, person: str | None = None) -> None:
    """Switch page, carrying the event, the filter and the person to open. Used as a callback.

    A click-through clears the other Prospects filters, so the target cannot be hidden;
    whatever it carries shows as a removable chip there. person opens and scrolls to that card.
    """
    st.session_state["page"] = page
    if event is not None:
        st.session_state["prospects_event"] = event
        if event != ALL_EVENTS:
            st.session_state["insights_event"] = event
            st.session_state["reports_event"] = event
    if people_filter is not None:
        st.session_state["prospects_filter"] = people_filter
    if event is not None or people_filter is not None:
        st.session_state["prospects_timing"] = []
        st.session_state["prospects_conf"] = []
        st.session_state["prospects_people_only"] = False
    focus = f"{event}|{person}" if person and event and event != ALL_EVENTS else None
    st.session_state["focus_person"] = focus
    st.session_state["scroll_token"] = f"{focus}|{datetime.now().timestamp()}" if focus else None
    st.query_params["page"] = page


def bump(key: str) -> None:
    """Clear a chart's selection by giving the chart a new key. Used by the filter chips."""
    st.session_state[key] = st.session_state.get(key, 0) + 1


def clear_focus() -> None:
    """Close the opened person (the "Opened" chip)."""
    st.session_state["focus_person"] = None
    st.session_state["scroll_token"] = None


def queue_toast(text: str, icon: str | None = None) -> None:
    """Remember a toast for the next run. Used by callbacks, such as a download button's."""
    st.session_state.setdefault("toasts", []).append((text, icon))


def show_toasts() -> None:
    """Show and forget the queued toasts."""
    for text, icon in st.session_state.pop("toasts", []):
        st.toast(text, icon=icon)


def set_state(key: str, value: object) -> None:
    """Set one filter back to its default. Used by the filter chips."""
    st.session_state[key] = value


def chips(items: list[tuple[str, object, tuple]], key: str) -> None:
    """Active filters as removable chips: (label, callback, args). Nothing is drawn when there are none."""
    if not items:
        return
    with st.container(horizontal=True, key=f"chips-{key}"):
        for index, (label, callback, args) in enumerate(items):
            st.button(f"{label}  ✕", key=f"chip-{key}-{index}", on_click=callback, args=args,
                      help="Remove this filter")


def sidebar(event_count: int) -> None:
    """Brand, the five pages with tooltips, and where the data comes from."""
    with st.sidebar:
        c_html(c.brand_html())
        current = st.session_state["page"]
        for page, (label, icon, tip) in PAGES.items():
            st.button(label, key=f"nav-{page}", icon=icon, help=tip, width="stretch",
                      type="primary" if page == current else "tertiary", on_click=go, args=(page,))
        st.divider()
        st.caption(f"{event_count} processed events, read from outputs/. Nothing on these pages is recomputed; "
                   "every figure links to its source page.")


def header(title_html: c.Html, crumbs: list[tuple[str, tuple | None]], search_index: list[dict],
           notes: list[dict]) -> bool:
    """Title or greeting with its breadcrumb, search, notifications, profile. True when running is unlocked."""
    left, middle, right = st.columns([5, 3.2, 1.9], vertical_alignment="center")
    with left:
        c_html(title_html)
        breadcrumb(crumbs)
    with middle:
        picked = widgets.search(search_index)
    # A horizontal container keeps the bell and the profile side by side on phones too.
    with right, st.container(horizontal=True, horizontal_alignment="right", wrap=False):
        _notifications(notes)
        unlocked = _profile()
    unread = len([note for note in notes if note["id"] not in set(st.session_state["seen_notes"])])
    widgets.accessible_names([
        {"selector": ".st-key-notes-menu button", "label": f"Notifications, {unread} unread"},
        {"selector": ".st-key-profile-menu button", "label": "Profile and settings"},
    ])
    if picked and picked.get("action") == "add":
        st.session_state["add_open"] = True
        go("feed")
        st.rerun()
    if picked and picked.get("event"):
        go(picked.get("page") or "prospects", event=picked["event"], people_filter="all", person=picked.get("person"))
        st.rerun()
    return unlocked


def breadcrumb(crumbs: list[tuple[str, tuple | None]]) -> None:
    """Home › Prospects › company › person. Each earlier step is a button back to it; the last is text."""
    if len(crumbs) < 2:
        return
    with st.container(horizontal=True, key="crumbs", gap=None, vertical_alignment="center"):
        for index, (label, target) in enumerate(crumbs):
            if index:
                st.markdown('<span class="mc-crumb-sep" aria-hidden="true">›</span>', unsafe_allow_html=True)
            if target is None or index == len(crumbs) - 1:
                c_html(c.tag("span", label, cls="mc-crumb-here"))
            else:
                st.button(label, key=f"crumb-{index}", type="tertiary", on_click=go, args=target)


def greeting(now_utc: datetime | None = None) -> str:
    """"Good morning." by the visitor's own clock (browser offset); "Welcome back." if unknown."""
    offset = getattr(st.context, "timezone_offset", None)
    if offset is None:
        return "Welcome back."
    local = (now_utc or datetime.now(timezone.utc)) - timedelta(minutes=offset)
    hour = local.hour
    if 5 <= hour < 12:
        return "Good morning."
    if 12 <= hour < 17:
        return "Good afternoon."
    return "Good evening."


def _notifications(notes: list[dict]) -> None:
    """The bell: unread count on the button, the warnings inside, and mark-all-read."""
    seen = set(st.session_state["seen_notes"])
    unread = [note for note in notes if note["id"] not in seen]
    label = str(len(unread)) if unread else ""
    with st.popover(label, icon=":material/notifications:", help="Notifications: warnings the pipeline stored",
                    key="notes-menu"):
        st.markdown("**Notifications**")
        if not notes:
            st.caption("No warnings. Every processed event passed its checks.")
            return
        for note in notes:
            c_html(c.notification_html(note))
            target = "feed" if note["event_id"] is None else "insights" if note["level"] == "warning" else "reports"
            st.button(f"Review in {shell_label(target)} →", key=f"note-open-{note['id']}", type="tertiary",
                      on_click=go, args=(target, note["event_id"]))
        if unread:
            st.button("Mark all as read", key="notes-read", on_click=_mark_read, args=([note["id"] for note in notes],))
        else:
            st.caption("All read.")


def shell_label(page: str) -> str:
    """A page's name as shown in the sidebar."""
    return PAGES[page][0]


def _mark_read(ids: list[str]) -> None:
    """Remember these notifications as read for this session."""
    st.session_state["seen_notes"] = sorted(set(st.session_state["seen_notes"]) | set(ids))


def _profile() -> bool:
    """The profile menu: no accounts, the run password, the background switch, shortcuts."""
    with st.popover("", icon=":material/account_circle:", help="Profile and settings", key="profile-menu"):
        st.markdown("**Viewer**")
        st.caption("This demo has no sign-in. Viewing is open to everyone.")
        unlocked = run_unlocked()
        st.toggle("Pause background animation", key="bg_paused")
        st.button("Reports and pipeline", key="profile-reports", icon=":material/description:", type="tertiary",
                  on_click=go, args=("reports",))
    return unlocked


def password_matches(entered: str, password: str) -> bool:
    """Constant-time comparison, so response time does not hint at how much of it matched."""
    return hmac.compare_digest(entered.encode("utf-8"), password.encode("utf-8"))


def run_unlocked() -> bool:
    """True when APP_PASSWORD is set and typed correctly. Running costs money, so it is gated."""
    password = os.environ.get("APP_PASSWORD") or ""
    if not password:
        st.caption("Running the pipeline is turned off on this deployment.")
        return False
    entered = st.text_input("Password to run the pipeline", type="password", key="run_password")
    if not entered:
        return False
    if password_matches(entered, password):
        st.caption("Pipeline unlocked for this session.")
        return True
    st.error("Wrong password.")
    return False


def c_html(fragment: c.Html) -> None:
    """Draw one fragment built by ui/components.py (every document value in it is escaped)."""
    st.markdown(fragment, unsafe_allow_html=True)
