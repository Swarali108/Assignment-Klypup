"""Find each timing rule's wording in this event's own pages. Code only, no model call.

For every lock-in period in config/lock_in.py, and the proceeds-at-listing rule,
the pages are searched in this order: the lock_in pages locate ranked, then every
page in document order. The first page that holds all of a period's anchor
phrases is cited with url#page=N and the sentence around each anchor. A period
with no such page is {"found": False}.

An anchor may be a tuple of phrases (any one counts). A rule with scope
"sentence" (the proceeds-at-listing rule) needs every anchor in one sentence that
holds none of its exclude words.
"""

from __future__ import annotations

import re

from config.lock_in import LOCK_IN_RULES, OFS_PROCEEDS_RULE

_QUOTE_LIMIT = 300
_SENTENCE_END = re.compile(r"(?<=[.;])\s+")
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18, "twenty": 20,
    "twenty-four": 24, "thirty-six": 36,
}
_WORDS_BY_NUMBER = {number: word for word, number in _NUMBER_WORDS.items() if "-" not in word}
_SYNONYMS = {"offer": ("offer", "issue")}


def find_rule_sources(pages: list[dict], lock_in_hits: list[dict] | None = None) -> dict:
    """{rule_id: {"variant": id, "periods": {label: source}}} for lock-in rules, plus the proceeds rule's source."""
    ordered = search_order(pages, lock_in_hits or [])
    found: dict = {}
    for rule in LOCK_IN_RULES:
        found[rule["id"]] = find_rule_variant(rule, ordered)
    found[OFS_PROCEEDS_RULE["id"]] = find_sentence_anchors(
        OFS_PROCEEDS_RULE["anchors"], ordered, OFS_PROCEEDS_RULE.get("exclude") or ()
    )
    return found


def rule_variants(rule: dict) -> list[dict]:
    """The rule's own wording ("default"), then each variant, as {id, period, split_note, periods}."""
    default = {"id": "default", "period": rule["period"], "split_note": rule["split_note"], "periods": rule["periods"]}
    return [default] + list(rule.get("variants") or ())


def find_rule_variant(rule: dict, pages: list[dict]) -> dict:
    """The first wording whose every period is found, with its sources. Else the default, not found."""
    tried = []
    for variant in rule_variants(rule):
        periods = {period["label"]: find_period(period["anchors"], pages) for period in variant["periods"]}
        tried.append({"variant": variant["id"], "periods": periods})
        if all(source["found"] for source in periods.values()):
            return tried[-1]
    return tried[0]


def find_period(anchors: tuple, pages: list[dict]) -> dict:
    """One lock-in period's source: a sentence holding every anchor, else a page holding them all.

    The sentence is the stronger citation (the period and its shares stated together);
    the page match stays as the fallback for a rule split over sentences.
    """
    found = find_sentence_anchors(anchors, pages)
    return found if found["found"] else find_anchors(anchors, pages)


def search_order(pages: list[dict], lock_in_hits: list[dict]) -> list[dict]:
    """Pages locate ranked for lock_in first, then the rest in document order, each once."""
    by_key = {(page.get("source_url"), page.get("pdf_index")): page for page in pages}
    first = [by_key[key] for key in ((hit.get("source_url"), hit.get("pdf_index")) for hit in lock_in_hits) if key in by_key]
    seen = {id(page) for page in first}
    rest = sorted((page for page in pages if id(page) not in seen),
                  key=lambda page: (page.get("source_url") or "", page.get("pdf_index") or 0))
    return first + rest


def find_anchors(anchors: tuple, pages: list[dict]) -> dict:
    """The first page holding every anchor, with one quote per anchor. Else {"found": False}."""
    patterns = [anchor_pattern(anchor) for anchor in anchors]
    anchors = tuple(anchor_text(anchor) for anchor in anchors)
    for page in pages:
        text = " ".join((page.get("text") or "").split())
        matches = [pattern.search(text) for pattern in patterns]
        if all(matches):
            url = page.get("source_url")
            return {
                "found": True,
                "url": url,
                "pdf_index": page.get("pdf_index"),
                "printed_page": page.get("printed_page"),
                "link": f"{url}#page={page.get('pdf_index')}" if url else None,
                "anchors": list(anchors),
                "quotes": [_sentence(text, match.start(), match.end()) for match in matches],
            }
    return {"found": False, "anchors": list(anchors)}


def find_sentence_anchors(anchors: tuple, pages: list[dict], exclude: tuple[str, ...] = ()) -> dict:
    """The first sentence holding every anchor and no exclude word, cited like find_anchors. Else {"found": False}."""
    patterns = [anchor_pattern(anchor) for anchor in anchors]
    blocked = [anchor_pattern(word) for word in exclude]
    texts = tuple(anchor_text(anchor) for anchor in anchors)
    for page in pages:
        text = " ".join((page.get("text") or "").split())
        for sentence in _SENTENCE_END.split(text):
            if all(pattern.search(sentence) for pattern in patterns) and not any(word.search(sentence) for word in blocked):
                url = page.get("source_url")
                quote = sentence if len(sentence) <= _QUOTE_LIMIT * 2 else sentence[: _QUOTE_LIMIT * 2] + " …"
                return {
                    "found": True,
                    "url": url,
                    "pdf_index": page.get("pdf_index"),
                    "printed_page": page.get("printed_page"),
                    "link": f"{url}#page={page.get('pdf_index')}" if url else None,
                    "anchors": list(texts),
                    "quotes": [quote for _ in texts],
                }
    return {"found": False, "anchors": list(texts)}


def anchor_text(anchor: str | tuple[str, ...]) -> str:
    """An anchor as one string for the output: alternatives joined by " | "."""
    return anchor if isinstance(anchor, str) else " | ".join(anchor)


def anchor_pattern(anchor: str | tuple[str, ...]) -> re.Pattern[str]:
    """A case-insensitive pattern for the anchor's words, with any spaces or punctuation between them.

    A number matches its digits or its word ("18" or "eighteen", "six" or "6"), with an
    optional bracketed repeat ("6 (six)"). "offer" also matches "issue". A tuple matches
    any one of its phrases.
    """
    phrases = [anchor] if isinstance(anchor, str) else list(anchor)
    bodies = []
    for phrase in phrases:
        words = re.findall(r"\w+%?|%", phrase.lower())
        body = r"[\W_]+".join(_word_pattern(word) for word in words)
        tail = r"(?!\w)" if words and words[-1][-1].isalnum() else ""
        bodies.append(body + tail)
    return re.compile(r"(?<!\w)(?:" + "|".join(bodies) + ")", re.IGNORECASE)


def _word_pattern(word: str) -> str:
    """One anchor word as a pattern: numbers as digits or words, "offer" as offer or issue."""
    number = int(word) if word.isdigit() else _NUMBER_WORDS.get(word)
    if number is not None and number in _WORDS_BY_NUMBER:
        either = f"(?:{number}|{_WORDS_BY_NUMBER[number]})"
        return either + r"(?:[\W_]*\(\s*" + either + r"\s*\))?"
    if word in _SYNONYMS:
        return "(?:" + "|".join(re.escape(option) for option in _SYNONYMS[word]) + ")"
    return re.escape(word)


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence around a match, cut to _QUOTE_LIMIT characters."""
    left = text.rfind(". ", 0, start)
    left = 0 if left < 0 else left + 2
    right = text.find(". ", end)
    right = len(text) if right < 0 else right + 1
    if right - left <= _QUOTE_LIMIT:
        return text[left:right].strip()
    cut_left, cut_right = max(left, start - _QUOTE_LIMIT // 2), min(right, end + _QUOTE_LIMIT // 2)
    if cut_left > left:
        cut_left = text.find(" ", cut_left, start) + 1 or cut_left
    if cut_right < right:
        space = text.rfind(" ", end, cut_right)
        cut_right = space if space > 0 else cut_right
    prefix = "… " if cut_left > left else ""
    suffix = " …" if cut_right < right else ""
    return f"{prefix}{text[cut_left:cut_right].strip()}{suffix}"
