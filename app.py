"""FinSight · Wealth Intelligence: the Streamlit front end for the call-list engine.

    streamlit run app.py

It reads events/*.json and outputs/<event_id>/*.json and never recomputes a figure.
  ui/shell.py           sidebar, header, notifications, profile, page state
  ui/pages.py           Home, Prospects, Insights, Network, Reports (the RM's questions, in order)
  ui/charts.py          every chart, one style; click selects, double-click clears
  ui/dashboard_data.py  cross-event counts (rules in config/ranking.py)
  ui/components.py      HTML pieces; every value from a document is escaped there
  ui/widgets.py         the JavaScript pieces: background, Ctrl+K search, copy brief, scroll to card
  ui/styles.py          CSS; theme and fonts in .streamlit/config.toml

Viewing needs no password. Running the pipeline or adding an event spends money, so
it needs APP_PASSWORD (profile menu); with no APP_PASSWORD set it is turned off. On a
host, settings come from st.secrets and are copied into os.environ so the run.py
subprocess inherits them. Secrets are never printed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from agents.spec import DOC_TYPES, EVENT_TYPES, EventSpec
from ui import components as c
from ui import dashboard_data as data
from ui import pages, shell, widgets
from ui.shell import password_matches  # noqa: F401  (kept importable for tests and callers)
from ui.styles import page_css

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "events"
OUTPUTS = ROOT / "outputs"
# Copied from st.secrets into os.environ when present. MAX_WORKERS is not secret, but
# on a host st.secrets is where settings are given.
HOST_SETTINGS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_MODEL_STRONG", "APP_PASSWORD", "MAX_WORKERS")


def main() -> None:
    """Shell, then the current page inside its own container (so it fades in on page change)."""
    st.set_page_config(page_title="FinSight · Wealth Intelligence", page_icon=":material/diamond:", layout="wide")
    st.markdown(page_css(), unsafe_allow_html=True)
    load_host_settings()
    shell.init_state()
    shell.show_toasts()
    widgets.background(paused=bool(st.session_state.get("bg_paused")))
    events = data.load_events(EVENTS, OUTPUTS)
    numbers = data.kpis(events)
    notes = data.notifications(events, pd.Timestamp.today().date())
    shell.sidebar(numbers["events"])
    page = st.session_state["page"]
    if page == "home":
        title = c.greeting_html(shell.greeting(), _summary(numbers, notes))
    else:
        label, _icon, tip = shell.PAGES[page]
        title = c.page_title_html(label, tip)
    unlocked = shell.header(title, _crumbs(page, events), data.search_index(events), notes)
    with st.container(key=f"page-{page}"):
        if page == "home":
            pages.home(events, OUTPUTS)
        elif page == "feed":
            pages.live_feed(events, OUTPUTS, unlocked, _run_pipeline)
        elif page == "prospects":
            pages.prospects(events)
        elif page == "insights":
            pages.insights(events)
        elif page == "network":
            pages.network(events)
        else:
            pages.reports(events, OUTPUTS, unlocked, _run_pipeline, _new_event_form)


def _crumbs(page: str, events: list[dict]) -> list[tuple[str, tuple | None]]:
    """Home › page › event › person, from the current selection. Each tuple is (label, go() args)."""
    crumbs: list[tuple[str, tuple | None]] = [("Home", ("home",))]
    if page == "home":
        return crumbs
    crumbs.append((shell.PAGES[page][0], (page,)))
    names = {event["spec"].event_id: event for event in data.processed(events)}
    picker = {"prospects": "prospects_event", "insights": "insights_event", "reports": "reports_event"}.get(page)
    event_id = st.session_state.get(picker) if picker else None
    if event_id in names:
        crumbs.append((names[event_id]["spec"].company, (page, event_id)))
    focus = st.session_state.get("focus_person") if page == "prospects" else None
    if focus:
        focus_event, person_id = focus.split("|", 1)
        person = data.person_lookup(names[focus_event]).get(person_id) if focus_event in names else None
        if person:
            if event_id != focus_event:
                crumbs.append((names[focus_event]["spec"].company, (page, focus_event)))
            crumbs.append((person["name_as_printed"], None))
    return crumbs


def _summary(numbers: dict, notes: list[dict]) -> str:
    """The line under the greeting: what is in the data today."""
    warnings = sum(1 for note in notes if note["level"] == "warning")
    return (f"Your wealth intelligence brief: {numbers['potential']} people to call across {numbers['events']} money "
            f"events, {numbers['high']} high priority, {warnings} warning{'s' if warnings != 1 else ''} to review.")


def load_host_settings() -> None:
    """Copy each HOST_SETTINGS key present in st.secrets into os.environ. Values are never shown.

    With no secrets file (a local run) there is nothing to copy; .env still applies.
    """
    try:
        for key in HOST_SETTINGS:
            if key in st.secrets:
                os.environ[key] = str(st.secrets[key])
    except FileNotFoundError:
        return


def _new_event_form() -> None:
    """Collect an event, validate it with EventSpec, and save events/<event_id>.json."""
    with st.form("new_event"):
        st.markdown("**New event**")
        event_id = st.text_input("event_id (lowercase slug)")
        event_type = st.selectbox("Type", EVENT_TYPES)
        company = st.text_input("Company")
        documents = st.data_editor(
            pd.DataFrame([{"url": "", "doc_type": "rhp", "note": ""}]),
            num_rows="dynamic",
            column_config={"doc_type": st.column_config.SelectboxColumn("doc_type", options=list(DOC_TYPES))},
            key="new_docs",
        )
        overwrite = st.checkbox("Overwrite if the file exists")
        submitted = st.form_submit_button("Save event")
    if submitted:
        _save_event(event_id, event_type, company, documents, overwrite)


def _save_event(event_id: str, event_type: str, company: str, documents: pd.DataFrame, overwrite: bool) -> None:
    """Validate and write the event file. Errors are shown, nothing is saved."""
    docs = [_document(row) for row in documents.fillna("").to_dict("records") if str(row.get("url") or "").strip()]
    payload = {"event_id": event_id.strip(), "event_type": event_type, "company": company.strip(), "documents": docs}
    try:
        spec = EventSpec.model_validate(payload)
    except ValidationError as exc:
        st.error(f"Not saved: {exc}")
        return
    path = EVENTS / f"{spec.event_id}.json"
    if path.exists() and not overwrite:
        st.error(f"{path.name} exists. Tick overwrite to replace it.")
        return
    path.write_text(json.dumps(spec.model_dump(exclude_none=True), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    st.success(f"Saved {path.name}. Choose it above and press Run.")


def _document(row: dict) -> dict:
    """One document row from the form. An empty note is left out."""
    document = {"url": str(row["url"]).strip(), "doc_type": row.get("doc_type") or "rhp"}
    if str(row.get("note") or "").strip():
        document["note"] = str(row["note"]).strip()
    return document


def _run_pipeline(path: Path) -> int:
    """Run --step all as a subprocess; list each step with seconds, calls and cost as it finishes.

    The child gets no APP_PASSWORD. Returns run.py's exit code.
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    env.pop("APP_PASSWORD", None)
    command = [sys.executable, "run.py", "--event", str(path), "--step", "all"]
    tail: list[str] = []
    total = None
    with st.status("Running the pipeline", expanded=True) as status:
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        for line in process.stdout:
            tail = (tail + [line.rstrip()])[-40:]
            total = c.parse_total_line(line) or total
            _show_progress(line.strip(), status)
        code = process.wait()
        if code == 0:
            words = f" in {total['seconds']} s, ${total['cost']}" if total else ""
            status.update(label=f"Pipeline finished{words}", state="complete")
            if total:
                shell.c_html(c.step_html({"step": "total", **total}))
        else:
            status.update(label=f"Pipeline failed (exit {code})", state="error")
            st.code("\n".join(tail))
    return code


def _show_progress(line: str, status) -> None:
    """A "STEP x start" line updates the label; a "STEP x done" line adds that step's row."""
    parts = line.split()
    if len(parts) >= 3 and parts[0] == "STEP" and parts[2] == "start":
        status.update(label=f"Running {parts[1]}…")
        return
    row = c.parse_step_line(line)
    if row:
        shell.c_html(c.step_html(row))


if __name__ == "__main__":
    main()
