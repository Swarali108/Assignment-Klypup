"""The custom browser pieces, as Streamlit v2 components: background, search, copy, scroll.

Everything else on the page is plain Streamlit. These need JavaScript: the background is
a canvas that must survive reruns, search must update on each key press, the clipboard
can only be written from the browser, and scrolling to a card happens in the browser.
Their code is in ui/web/ so it can be read on its own.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

WEB = Path(__file__).resolve().parent / "web"

# Registered once at import. isolate_styles=False for the background so its canvas can
# sit behind the whole app; the search keeps its CSS in a shadow root.
_BACKGROUND = st.components.v2.component(
    "finsight_background", js=(WEB / "background.js").read_text(encoding="utf-8"), isolate_styles=False,
)
_SEARCH = st.components.v2.component(
    "finsight_search",
    js=(WEB / "search.js").read_text(encoding="utf-8"),
    css=(WEB / "search.css").read_text(encoding="utf-8"),
)


_COPY = st.components.v2.component(
    "finsight_copy", js=(WEB / "copy.js").read_text(encoding="utf-8"), css=(WEB / "copy.css").read_text(encoding="utf-8"),
)
_LABELS = st.components.v2.component("finsight_labels", js=(WEB / "labels.js").read_text(encoding="utf-8"),
                                     isolate_styles=False)
_SCROLL = st.components.v2.component("finsight_scroll", js=(WEB / "scroll.js").read_text(encoding="utf-8"),
                                     isolate_styles=False)


def background(paused: bool) -> None:
    """Mount the portfolio particle background. The canvas is made once per browser tab."""
    _BACKGROUND(key="finsight-bg", data={"paused": paused}, height=0)


def search(index: list[dict]) -> dict | None:
    """The Ctrl+K search box. Returns the picked {page, event, person} on the run it was picked."""
    result = _SEARCH(key="finsight-search", data={"index": index}, on_pick_change=lambda: None)
    return result.get("pick") if result is not None else None


def copy_button(text: str, key: str) -> str | None:
    """A "Copy brief" button. Returns "ok" or "failed" on the run after a click, else None."""
    result = _COPY(key=key, data={"text": text}, on_copied_change=lambda: None)
    return result.get("copied") if result is not None else None


def scroll_to(selector: str, token: str) -> None:
    """Scroll the browser to selector once per token (one chart click)."""
    _SCROLL(key="finsight-scroll", data={"selector": selector, "token": token}, height=0)


def accessible_names(labels: list[dict]) -> None:
    """Give icon-only buttons an aria-label: [{"selector": css, "label": words}]."""
    _LABELS(key="finsight-labels", data={"labels": labels}, height=0)
