"""Clean a printed name so the same person can be grouped. No model calls.

name_as_printed stays as the document wrote it. name_clean is only the key.
"""

from __future__ import annotations

import re

from agents.locate import normalise
from config.holder_types import (
    ENTITY_TOKENS,
    FAMILY_VEHICLE_PHRASES,
    FAMILY_VEHICLE_TOKENS,
    PERSON_MAX_TOKENS,
    PERSON_MIN_TOKENS,
)

# Footnote marks that sit on a name, and a bracketed note number such as [1] or (2).
_FOOTNOTE = re.compile(r"[\^*#†‡]+|\[\d+\]|\(\d+\)")
# One leading honorific. "mrs" is listed before "mr" so the longer title wins.
_TITLE = re.compile(r"^(?:prof|dr|mrs|mr|ms|shri|smt)\.?\s+", re.IGNORECASE)


def clean_name(name: str) -> str:
    """Drop footnote marks and one leading title, then normalise.

    "Asha Example^" and "Asha Example" become the same key.
    "Ravi Kumar Example" and "Mohan Kumar Example" stay different.
    """
    text = _FOOTNOTE.sub("", name or "")
    text = _TITLE.sub("", text.strip(), count=1)
    return normalise(text)


def name_tokens(name: str) -> list[str]:
    """clean_name() split into words, with punctuation dropped. "S.A.R.L." becomes "sarl"."""
    words = re.sub(r"[-–—/]", " ", clean_name(name)).split(" ")
    tokens = [re.sub(r"[^\w&]", "", word) for word in words]
    return [token for token in tokens if token]


def holder_type(name: str) -> tuple[str, str]:
    """Return (type, reason). type is person, entity, family_vehicle or unsure.

    Family-vehicle words are checked first, then entity words. A name with no
    marker is a person only when it has PERSON_MIN_TOKENS to PERSON_MAX_TOKENS
    words, no digits, and at least one word longer than an initial.
    """
    tokens = name_tokens(name)
    joined = " ".join(tokens)
    for phrase in FAMILY_VEHICLE_PHRASES:
        if f" {phrase} " in f" {joined} ":
            return "family_vehicle", f"contains '{phrase}'"
    for token in tokens:
        if token in FAMILY_VEHICLE_TOKENS:
            return "family_vehicle", f"contains '{token}'"
    for token in tokens:
        if token in ENTITY_TOKENS:
            return "entity", f"contains '{token}'"
    return _person_or_unsure(tokens)


def _person_or_unsure(tokens: list[str]) -> tuple[str, str]:
    """A name with no entity or family marker. Anything odd is unsure, not guessed."""
    if not PERSON_MIN_TOKENS <= len(tokens) <= PERSON_MAX_TOKENS:
        return "unsure", f"no entity marker and {len(tokens)} words"
    if any(re.search(r"\d", token) for token in tokens):
        return "unsure", "no entity marker but has a digit"
    if all(len(token) == 1 for token in tokens):
        return "unsure", "only initials"
    return "person", "no entity or family marker"
