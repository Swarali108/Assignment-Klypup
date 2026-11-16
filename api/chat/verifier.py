"""Every number in the prose must be in the tool results; any other number is removed. Code only.

A number is every run of digits, with optional thousands commas and one decimal part ("1,23,456.78"), even when
letters touch it ("₹500Cr", "50k").
Commas are ignored when comparing ("45,000" in the prose matches 45000 in the data), and so are trailing
zeros after a decimal point ("6.10" matches 6.1). Substrings never count: "45" does not pass because "450" is
in the data. A removed number takes its currency sign and unit with it, so no "₹ Cr" is left behind.
v2: with words=True (model prose only), a count spelled out as a word ("two" to "twenty") is a number too: it stays
only when its digits are in the data ("All five have..." with no 5 in the data loses the word). "one" is left alone.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

# Every digit run counts, whatever touches it ("₹500Cr", "Rs.500", "50k", "3x", "2nd"); only other digits,
# thousands commas and a decimal part belong to the same number.
_NUMBER = re.compile(r"(?<!\d)\d(?:[\d,]*\d)?(?:\.\d+)?(?!\d)")
# A removed number's surroundings: an optional currency sign before it, an optional unit after it.
_WITH_UNIT = re.compile(r"(?:(?:₹|Rs\.?|INR|\$|USD)\s?)?(?<!\d)(\d(?:[\d,]*\d)?(?:\.\d+)?)(?!\d)"
                        r"(?:\s?(?:%|Cr\b|crores?\b|lakhs?\b|shares\b|per cent\b|k\b|mn\b|bn\b|x\b|st\b|nd\b|rd\b|th\b))?",
                        re.I)


_COUNT_WORDS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split()) if n >= 2}
_COUNT = re.compile(r"\b(" + "|".join(_COUNT_WORDS) + r")\b", re.I)


def _norm(text: str) -> str | None:
    """'1,23,456.50' -> '123456.5'; None when it is not a number."""
    raw = text.replace(",", "").strip(".")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    text = format(value.normalize(), "f")
    return text


def numbers_in(value: object) -> set[str]:
    """Every number in any string or number inside a JSON-like value, normalised."""
    blob = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    found = set()
    for match in _NUMBER.finditer(blob):
        norm = _norm(match.group(0))
        if norm is not None:
            found.add(norm)
    return found


def verify(prose: str, tool_results: object, words: bool = False) -> tuple[str, list[str]]:
    """(prose with unverified numbers removed, the numbers removed as written). words: also check count words."""
    allowed = numbers_in(tool_results)
    removed: list[str] = []

    def keep_or_drop(match: re.Match) -> str:
        norm = _norm(match.group(1))
        if norm is not None and norm in allowed:
            return match.group(0)
        removed.append(match.group(0))
        return ""

    cleaned = _WITH_UNIT.sub(keep_or_drop, prose or "")

    def keep_or_drop_word(match: re.Match) -> str:
        if str(_COUNT_WORDS[match.group(1).lower()]) in allowed:
            return match.group(0)
        removed.append(match.group(0))
        return ""

    if words:
        cleaned = _COUNT.sub(keep_or_drop_word, cleaned)
    if removed:
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
        cleaned = re.sub(r"([,;])(?:\s*[,;])+", r"\1", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, removed


def limit_words(prose: str, max_words: int) -> str:
    """The prose cut to at most max_words words, ending at a sentence when one ends near the cut."""
    words = (prose or "").split()
    if len(words) <= max_words:
        return (prose or "").strip()
    cut = " ".join(words[:max_words])
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > len(cut) * 0.6 else cut.rstrip(",;:") + "…"
