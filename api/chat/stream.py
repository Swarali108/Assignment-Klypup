"""Verified sentence-level streaming: model deltas in, checked sentences out. Code only.

Raw token streaming could flash a digit the verifier would later remove, so nothing reaches the screen until a
whole sentence has arrived and passed the verifier (every number in it must be in this turn's facts). A sentence
ends at . ! ? or a line break, but only once the next character has arrived and is whitespace, so "₹468." in one
delta and "85 Cr" in the next is never cut; abbreviations ("Dr.", "Ltd.") and decimals never end a sentence.
The word cap is enforced as sentences stream: once it is reached, the rest is dropped.
"""

from __future__ import annotations

import re

from api.chat import verifier

_ABBREV = {"dr", "mr", "mrs", "ms", "prof", "ltd", "pvt", "co", "inc", "no", "rs", "st", "vs", "smt", "shri", "sr",
           "jr", "approx", "e.g", "i.e", "etc", "nos", "corp", "bros", "messrs"}
_END = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s)|\n+")


class Sentences:
    """Feed deltas; get back complete sentences."""

    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, delta: str) -> list[str]:
        """Complete sentences now available (the unfinished tail stays buffered)."""
        self.buffer += delta or ""
        out, start = [], 0
        for match in _END.finditer(self.buffer):
            if match.end() >= len(self.buffer):
                break  # need the following character before deciding
            piece = self.buffer[start:match.end()]
            if match.group(0).startswith(".") and _is_abbreviation(piece):
                continue
            if piece.strip():
                out.append(piece.strip())
            start = match.end()
        self.buffer = self.buffer[start:]
        return out

    def flush(self) -> list[str]:
        """Whatever is left at the end of the stream."""
        rest, self.buffer = self.buffer.strip(), ""
        return [rest] if rest else []


def _is_abbreviation(piece: str) -> bool:
    """True when the piece ends with a known abbreviation's full stop ('... Dr.')."""
    words = piece.rstrip(".").split()
    return bool(words) and words[-1].lower().strip("(\"'") in _ABBREV


def split(text: str) -> list[str]:
    """A finished text as sentences (same rules as streaming)."""
    feeder = Sentences()
    return feeder.feed((text or "") + " ") + feeder.flush()


class Checked:
    """Verifies and caps sentences as they stream. .removed lists every number taken out, .total the numbers seen."""

    def __init__(self, facts: object, max_words: int, words_checked: bool = True):
        self.facts, self.max_words, self.words_checked = facts, max_words, words_checked
        self.words, self.removed, self.total, self.full = 0, [], 0, False
        self.text = ""

    def take(self, sentence: str) -> str | None:
        """The verified sentence to emit, or None (empty after checks, or past the word cap)."""
        if self.full:
            return None
        self.total += len(verifier.numbers_in(sentence))
        clean, removed = verifier.verify(sentence, self.facts, words=self.words_checked)
        self.removed.extend(removed)
        count = len(clean.split())
        if not clean.strip() or re.fullmatch(r"[\W_]*", clean):
            return None
        if self.words + count > self.max_words:
            self.full = True
            if self.words:
                return None
            clean = verifier.limit_words(clean, self.max_words)
            count = len(clean.split())
        self.words += count
        self.text += clean + " "
        return clean
