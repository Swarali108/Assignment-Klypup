"""Spend settings for one pipeline run. Numbers here are limits, never facts.

BUDGET_MODE (environment):
  normal (default)  every callable person gets a model-written brief; unsure name pairs go to
                    the strong model.
  lean              for a $0.50-per-event ceiling. Cut in this order, cheapest loss first:
                      1. unsure name pairs are not sent to the strong model (they stay two people,
                         flagged unsure); the strong model was up to half of one event's spend.
                      2. only the top LEAN_MODEL_BRIEFS people get a model brief; the rest get the
                         code template (same checked numbers, plainer words).
                    Reading the tables is never cut: every number comes from it.

Both modes stop asking for model briefs once the run has spent BRIEF_STOP_SHARE of the event
budget, so a run can never overshoot it on briefs.
"""

from __future__ import annotations

import os

EVENT_BUDGET_USD = {"normal": 2.00, "lean": 0.50}
LEAN_MODEL_BRIEFS = 5
BRIEF_STOP_SHARE = 0.9


def budget_mode() -> str:
    """normal or lean (anything else reads as normal)."""
    mode = (os.environ.get("BUDGET_MODE") or "normal").strip().lower()
    return mode if mode in EVENT_BUDGET_USD else "normal"


def event_budget_usd() -> float:
    """The most one run of one event may spend."""
    return EVENT_BUDGET_USD[budget_mode()]


def model_brief_allowed(rank_index: int, spent_usd: float) -> str | None:
    """None when this person (0-based rank) may get a model brief, else the plain reason why not."""
    if spent_usd >= event_budget_usd() * BRIEF_STOP_SHARE:
        return f"event budget nearly spent (${spent_usd:.4f} of ${event_budget_usd():.2f}): template brief"
    if budget_mode() == "lean" and rank_index >= LEAN_MODEL_BRIEFS:
        return f"BUDGET_MODE=lean: model briefs for the top {LEAN_MODEL_BRIEFS} only; template brief"
    return None


def strong_model_for_names() -> bool:
    """False in lean mode: unsure name pairs stay separate instead of asking the strong model."""
    return budget_mode() != "lean"
