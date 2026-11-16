"""Settings for the control tower chat agent (api/chat/). Numbers here are limits, never facts.

Models come from the environment so another provider can be swapped in without code changes:
  LLM_CHAT_FAST    understanding a question and short answers (default openai/gpt-6-luna)
  LLM_CHAT_STRONG  planning multi-step questions and writing their answers (default openai/gpt-6.1-terra)
Prices for both live in tools/llm.PRICES (OpenRouter /models fetched 2026-11-15).
"""

from __future__ import annotations

import os
from contextvars import ContextVar

DEFAULT_FAST = "openai/gpt-6-luna"
DEFAULT_STRONG = "openai/gpt-6.1-terra"


# The model switcher (v3): models an RM may choose per conversation. (id, label, who made it). Prices live in
# tools/llm.PRICES (OpenRouter /models, cache/fetch fetched 2026-11-15); an id missing there is never offered.
ALLOWED_MODELS = (
    ("openai/gpt-6-luna", "GPT-6 Luna", "OpenAI, fast"),
    ("openai/gpt-6.1-terra", "GPT-6.1 Terra", "OpenAI, stronger"),
    ("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "Open-weight"),
    ("z-ai/glm-5.3-flash", "GLM 5.3 Flash", "Open-weight"),
    ("qwen/qwen3.8-flash", "Qwen 3.8 Flash", "Open-weight"),
)
# The model a request chose for itself (set around each step of a turn by api/chat/agent.respond). None: defaults.
_CHOSEN: ContextVar[str | None] = ContextVar("chat_model", default=None)


def allowed_ids() -> list[str]:
    return [m[0] for m in ALLOWED_MODELS]


def choose(model: str | None):
    """Make this model the chat's model for the current thread / task; returns the reset token."""
    return _CHOSEN.set(model if model in allowed_ids() else None)


def chosen_model() -> str | None:
    return _CHOSEN.get()


def fast_model() -> str:
    """The cheap model for routing and simple answers (the conversation's chosen model when there is one)."""
    return _CHOSEN.get() or (os.environ.get("LLM_CHAT_FAST") or DEFAULT_FAST).strip()


def strong_model() -> str:
    """The stronger model for plans and multi-step answers (the conversation's chosen model when there is one)."""
    return _CHOSEN.get() or (os.environ.get("LLM_CHAT_STRONG") or DEFAULT_STRONG).strip()


# Spend a role may approve with one confirm (USD, compared with the estimate's high end). None = no limit.
CONFIRM_LIMIT_USD = {"viewer": 0.0, "rm": 0.50, "head": 0.50, "admin": None}
# Model spend one question may use without a confirm (routing + a short answer).
QUESTION_CAP_USD = 0.05
# A confirm token is good for this long.
CONFIRM_TTL_SECONDS = 10 * 60

# Deep dive (the reverse tree run, starting from one person).
DEEP_DIVE_BUDGET_USD = 0.25
# Most branches followed per kind; the rest are reported as "Stopped: cap reached".
DEEP_DIVE_CAPS = {"same_person": 6, "filing": 5, "family": 4, "process": 2}
# How far from the starting person the tree may go (family member -> their other events).
DEEP_DIVE_MAX_DEPTH = 2
# Recency weight: a branch dated this many days ago counts half as much as one dated today.
RECENCY_HALF_LIFE_DAYS = 45

# Answer length, enforced in code after the model writes.
MAX_ANSWER_WORDS = 120
# Most plan steps the planner may ask for.
MAX_PLAN_STEPS = 5
# Most rows put in a card (the UI can open the full list).
MAX_CARD_ITEMS = 12

# Token sizes used for estimates until enough measured chat calls exist (then measured history wins).
EST_OUTPUT_TOKENS = {"route": 160, "plan": 420, "write": 260}
# A measured range needs at least this many logged calls for that step and model.
MIN_MEASURED_CALLS = 3

# ---------- v2: memory, compression, windows, scripts, streaming (api/CHAT_CONTRACT.md v2) ----------


def _env_int(name: str, default: int) -> int:
    """An integer setting from the environment (for demos and tests), else the default."""
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


# History older than the last KEEP_TURNS turns is summarised once the uncompressed history passes this many
# tokens (about 4 characters a token). CHAT_COMPRESS_TOKENS overrides it.
HISTORY_COMPRESS_TOKENS = _env_int("CHAT_COMPRESS_TOKENS", 3000)
# Raw turns (one RM message + one answer each) always kept word for word in the context.
KEEP_TURNS = _env_int("CHAT_KEEP_TURNS", 4)
# Characters of one rendered message kept in the context (cards are summarised, never pasted whole).
TURN_CHARS = 700
# The rolling summary is cut to this many characters.
SUMMARY_CHARS = 1800
# Most focus entities kept; most earlier entities remembered for name matching ("its about <first name>").
FOCUS_MAX = 3
RECENT_MAX = 12
# People offered as candidates in a clarify.
CANDIDATES_MAX = 5

# Time windows: "upcoming" looks this many days ahead; the fallback shows this many nearest rows.
UPCOMING_DAYS = 60
NEAREST_ROWS = 8

# Streamed prose: output cap for the writer call.
WRITE_MAX_TOKENS = 400
