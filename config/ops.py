"""Operations settings: when a fetched document counts as stale, and the spend limits shown on /ops/health.

Numbers here are limits and thresholds, never facts. Everything can be moved with an environment variable.
"""

from __future__ import annotations

import os


def _num(name: str, default: float | None) -> float | None:
    """A positive number from the environment, else the default (None means "not set")."""
    try:
        value = float((os.environ.get(name) or "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def stale_after_days() -> int:
    """A document fetched more than this many days ago is shown with a "stale" badge (STALE_AFTER_DAYS, default 14)."""
    return int(_num("STALE_AFTER_DAYS", 14) or 14)


def model_daily_cap_usd() -> float | None:
    """Model spend allowed per day (MODEL_DAILY_CAP_USD); None when no daily cap is configured."""
    return _num("MODEL_DAILY_CAP_USD", None)


def brightdata_monthly_cap() -> float | None:
    """Bright Data requests allowed per month (BRIGHTDATA_MONTHLY_CAP); None when not configured."""
    return _num("BRIGHTDATA_MONTHLY_CAP", None)
