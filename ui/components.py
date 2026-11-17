"""HTML pieces for the app: cards, badges, pills, evidence chips. No Streamlit here.

Every function returns an Html string. Any other value put into HTML goes through
esc(), which applies html.escape, so a name, role or quote copied from a document
can never become markup. A link is used only when its scheme is http or https.
Nothing here computes a figure: amounts, dates and costs are shown as stored in
outputs/, and the only choice made is which stored entry to show (largest_entry).

Each fragment is one line with no blank lines, so st.markdown treats it as one HTML
block and does not read Markdown or "$...$" maths inside it.
"""

from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from agents.report import also_seen_in, completeness_lines


_SPACES = re.compile(r"\s+")


class Html(str):
    """A fragment built in this module. esc() leaves it as it is; any other str is escaped."""


def esc(value: object) -> Html:
    """value as safe HTML text on one line. "$" becomes &#36; so Markdown never reads maths in it.

    Runs of whitespace (a quote copied across lines) become one space, as HTML would show
    them anyway; a blank line would otherwise end the HTML block early.
    """
    if isinstance(value, Html):
        return value
    return Html(html.escape(_SPACES.sub(" ", str(value)), quote=True).replace("$", "&#36;"))


def join(parts: list) -> Html:
    """Fragments side by side, each escaped unless it is already Html."""
    return Html("".join(esc(part) for part in parts))


def tag(name: str, body: object = "", cls: str | None = None, **attrs: object) -> Html:
    """<name class=... attrs>body</name>, with every attribute value escaped."""
    pairs = ([f' class="{esc(cls)}"'] if cls else []) + [
        f' {key.rstrip("_").replace("_", "-")}="{esc(value)}"' for key, value in attrs.items() if value is not None
    ]
    return Html(f"<{name}{''.join(pairs)}>{esc(body)}</{name}>")


def safe_url(url: object) -> str | None:
    """The url when its scheme is http or https, else None."""
    text = str(url or "").strip()
    return text if urlparse(text).scheme in ("http", "https") else None


def link(url: object, body: object, cls: str | None = None, title: object = None) -> Html:
    """A link that opens in a new tab, or plain text when the url is not http(s)."""
    target = safe_url(url)
    if target is None:
        return tag("span", body, cls=cls, title=title)
    return tag("a", body, cls=cls, href=target, target="_blank", rel="noopener noreferrer", title=title)


# ---------- unknown values, badges, pills ----------

def unknown(reason: object = None) -> Html:
    """"unknown" in muted text, with the reason as its tooltip."""
    return tag("span", "unknown", cls="mc-unknown", title=reason or "no reason recorded")


def text_or_unknown(value: object, reason: object) -> Html:
    """The value, or unknown(reason) when it is missing or blank."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return unknown(reason)
    return esc(value)


def badge(text: object, tone: str = "neutral", title: object = None) -> Html:
    """A small rounded label. tone is one of the mc-tone-* classes in ui/styles.py."""
    return tag("span", text, cls=f"mc-badge mc-tone-{tone}", title=title)


# Timing status -> (words on the pill, tone). The words are always shown, so colour
# never carries the meaning alone.
TIMING_PILLS = {
    "in_hand": ("In hand", "green"),
    "at_listing": ("At listing", "accent"),
    "unlocked": ("Unlocked", "accent"),
    "scheduled": ("Scheduled", "amber"),
    "after_date": ("After a printed date", "amber"),
    "settles": ("Settles", "amber"),
    "locked_in": ("Locked in", "grey"),
    "partly_unlocked": ("Partly unlocked", "grey"),
    "not_applicable": ("Not applicable", "neutral"),
}
UNKNOWN_PILL = ("Timing unknown", "red-outline")
CONFIDENCE_TONES = {"high": "accent", "medium": "neutral", "low": "amber"}


def timing_pill(status: object, words: object = None) -> Html:
    """The timing pill: its words and tone from TIMING_PILLS; the full timing text as tooltip."""
    label, tone = TIMING_PILLS.get(str(status), UNKNOWN_PILL)
    return badge(label, tone, title=words)


def confidence_badge(level: object) -> Html:
    """"High confidence" and so on. Confidence is kept apart from the amount."""
    name = str(level or "unknown")
    return badge(f"{name.capitalize()} confidence", CONFIDENCE_TONES.get(name, "red-outline"))


def role_badge(role: object) -> Html:
    """The role as printed, or unknown."""
    if role is None or not str(role).strip():
        return unknown("role not verified on the page")
    return badge(role, "neutral")


# ---------- evidence chips ----------

def page_label(node: dict) -> str:
    """"p. 16" when the printed page is known, else "pdf 20"."""
    printed = node.get("printed_page")
    return f"p. {printed}" if printed not in (None, "") else f"pdf {node.get('pdf_index')}"


def page_link(node: dict) -> str | None:
    """url#page=N for one page reference, or None when the node is not one."""
    if node.get("link"):
        return str(node["link"])
    base = node.get("url") or node.get("source_url")
    if base and node.get("pdf_index") is not None:
        return f"{base}#page={node['pdf_index']}"
    return None


def evidence_refs(node: object, field: str | None = None) -> list[dict]:
    """Every page reference under node (inputs, evidence, sources), each link and field once."""
    found: list[dict] = []
    _walk(node, field, found)
    unique: dict[tuple, dict] = {}
    for ref in found:
        unique.setdefault((ref["link"], ref["field"]), ref)
    return list(unique.values())


def _walk(node: object, field: str | None, found: list[dict]) -> None:
    """Collect page references depth first, carrying the nearest field name down."""
    if isinstance(node, list):
        for item in node:
            _walk(item, field, found)
        return
    if not isinstance(node, dict):
        return
    field = node.get("field") or field
    target = page_link(node)
    if target:
        quote = node.get("quote") or " … ".join(node.get("quotes") or [])
        found.append({"link": target, "field": field, "label": page_label(node), "quote": quote})
        return
    for key in ("inputs", "evidence", "sources"):
        if key in node:
            _walk(node[key], field, found)


def chip(ref: dict) -> Html:
    """One evidence chip: field and page, opening the PDF at that page; the quote as tooltip."""
    name = str(ref.get("field") or "").replace("_", " ")
    body = f"{name} · {ref['label']} ↗" if name else f"{ref['label']} ↗"
    return link(ref["link"], body, cls="mc-chip", title=ref.get("quote") or None)


def chips(node: object, empty: str = "no page link") -> Html:
    """Every evidence chip under node, or a muted note when there is none."""
    refs = evidence_refs(node)
    if not refs:
        return tag("span", empty, cls="mc-note")
    return join([chip(ref) for ref in refs])


# ---------- header and KPIs ----------

EVENT_TYPE_LABELS = {"ipo": "IPO", "buyback": "Buyback", "ofs_stock_exchange": "OFS through the stock exchange"}


def doc_label(doc_type: str) -> str:
    """"RHP" for short codes, "Prospectus" for words."""
    return doc_type.upper() if len(doc_type) <= 3 else doc_type.replace("_", " ").capitalize()


def documents_html(documents: list[dict]) -> Html:
    """Each document as "<type> · open PDF", opening in a new tab; the note as tooltip."""
    items = []
    for document in documents:
        url = str(document.get("url") or "")
        kind = "open PDF" if urlparse(url).path.lower().endswith(".pdf") else "open document"
        items.append(link(url, f"{doc_label(str(document.get('doc_type') or 'document'))} · {kind} ↗",
                          title=document.get("note")))
    return tag("div", join(items) if items else unknown("no documents listed"), cls="mc-docs")


def rupees(value: object) -> str:
    """A stored rupee amount with thousands separators, or the text as stored."""
    try:
        return f"₹{Decimal(str(value)):,}"
    except InvalidOperation:
        return str(value)


def price_html(price: dict | None) -> Html:
    """The price basis as stored, with its kind and evidence chips; else unknown."""
    price = price or {}
    if price.get("kind") in (None, "unknown") or not price.get("low"):
        return unknown(price.get("reason") or "price not verified")
    low, high = rupees(price["low"]), rupees(price["high"])
    value = low if low == high else f"{low} to {high}"
    kind = str(price["kind"]).replace("_", " ")
    return join([tag("span", value, cls="mc-value"), " ", tag("span", f"({kind})", cls="mc-note"), " ", chips(price)])


def listing_html(listing: dict | None) -> Html:
    """The listing date as printed, its scheduled status, unknown with reason, or not applicable."""
    if not listing:
        return tag("span", "not applicable", cls="mc-note")
    status = listing.get("status")
    if status == "verified":
        return join([tag("span", listing["date_as_printed"], cls="mc-value"), " ", chips(listing)])
    if status == "scheduled":
        words = f"{listing['date_as_printed']} per the offer document's timetable; not confirmed by a listing notice"
        return join([timing_pill("scheduled", words), " ", tag("span", listing["date_as_printed"], cls="mc-value"),
                     " ", tag("span", "not confirmed by a listing notice", cls="mc-note"), " ", chips(listing)])
    return unknown(listing.get("reason") or "listing date not verified")


def meta_item(label: str, value: Html) -> Html:
    """One labelled value in the event block."""
    return tag("div", join([tag("div", label, cls="mc-label"), tag("div", value, cls="mc-value")]))


def event_block(company: str, event_type: str, event_id: str, documents: list[dict], people_doc: dict | None) -> Html:
    """Company, event-type badge, documents, price basis and listing date, on one glass panel."""
    people_doc = people_doc or {}
    title = tag("div", join([tag("h1", company), badge(EVENT_TYPE_LABELS.get(event_type, event_type), "accent")]),
                cls="mc-event-title")
    meta = tag("div", join([
        meta_item("Documents", documents_html(documents)),
        meta_item("Price basis", price_html(people_doc.get("price_basis"))),
        meta_item("Listing date", listing_html(people_doc.get("listing"))),
        meta_item("Event id", esc(event_id)),
    ]), cls="mc-meta")
    return tag("div", join([title, meta]), cls="mc-panel mc-glass")


def kpi_card(label: str, value: object, sub: object = "") -> Html:
    """One KPI card: label, large value, small line under it."""
    return tag("div", join([tag("div", label, cls="mc-label"), tag("div", value, cls="mc-kpi-value"),
                            tag("div", sub, cls="mc-kpi-sub")]), cls="mc-kpi mc-glass")


def largest_entry(entries: list[dict]) -> dict | None:
    """The stored entry with the largest money_now_crore above zero. A choice, not a calculation."""
    best, best_value = None, Decimal(0)
    for entry in entries:
        try:
            value = Decimal(str(entry.get("money_now_crore") or 0))
        except InvalidOperation:
            continue
        if value > best_value:
            best, best_value = entry, value
    return best


def usd(value: object) -> Html:
    """A stored dollar cost to six places, or unknown."""
    if value is None:
        return unknown("not in cost.json")
    return esc(f"${float(value):.6f}")


def kpi_cards(ranked: dict | None, cost: dict | None) -> list[Html]:
    """Callable people, entities, largest single amount, and this run's cost."""
    ranked, totals = ranked or {}, (cost or {}).get("totals") or {}
    callable_people, entities = ranked.get("callable") or [], ranked.get("entities") or []
    top = largest_entry(callable_people + entities)
    if top is None:
        amount = kpi_card("Largest amount now", unknown("no holder has a computed amount of money now"))
    else:
        where = "call list" if any(entry is top for entry in callable_people) else "entities"
        amount = kpi_card("Largest amount now", amount_text(top["amount_display"]),
                          f"{top['name_as_printed']} · rank {top['rank']} in {where}")
    if not totals:
        cost_card = kpi_card("Cost of this run", unknown("cost.json not written yet"))
    else:
        per = join(["per callable person ", usd(totals.get("cost_per_callable_usd"))]) \
            if totals.get("callable_people") else unknown("no callable people")
        cost_card = kpi_card("Cost of this run", usd(totals.get("cost_usd")),
                             join(["without cache ", usd(totals.get("fresh_usd")), " · ", per]))
    return [
        kpi_card("Callable people", str(len(callable_people)), "people an RM can call"),
        kpi_card("Entities", str(len(entities)), "holders that are not called directly"),
        amount,
        cost_card,
    ]


# ---------- call-list cards ----------

def amount_text(display: object) -> Html:
    """An amount display as stored; "unknown: <reason>" becomes unknown with the reason as tooltip."""
    text = str(display or "")
    if not text.strip():
        return unknown("no amount stored")
    if text.startswith("unknown: "):
        return unknown(text[len("unknown: "):])
    return esc(text)


def card_html(entry: dict) -> Html:
    """Card head: rank, name, role badge, why money, amount; then timing pill and confidence."""
    kind = [] if entry.get("holder_type") == "person" else [" ", badge(entry.get("holder_type") or "entity", "grey")]
    who = tag("div", join([
        tag("span", f"#{entry['rank']}", cls="mc-rank"),
        tag("div", join([tag("span", entry["name_as_printed"], cls="mc-name"), role_badge(entry.get("role_as_printed")),
                         *kind, tag("div", entry.get("why_money") or unknown("why money not recorded"), cls="mc-why")])),
    ]), cls="mc-who")
    head = tag("div", join([who, tag("div", amount_text(entry.get("amount_display")), cls="mc-amount")]), cls="mc-card-head")
    # The pill describes the words beside it, so it uses the status of the displayed timing,
    # not the ranking trigger's (a seller can rank on unlocked shares while showing proceeds).
    status, words = entry.get("timing_display_status"), str(entry.get("timing_display") or "")
    if status in TIMING_PILLS:
        shown = words.removeprefix("not applicable: ") if status == "not_applicable" else words
        timing = join([timing_pill(status, words), tag("span", shown, cls="mc-timing-words")])
    else:
        timing = timing_pill(status, words.removeprefix("unknown: ") or "no timing stored")
    foot = tag("div", join([timing, confidence_badge(entry.get("confidence"))]), cls="mc-card-foot")
    return join([head, foot])


def brief_html(brief: dict | None) -> Html:
    """The brief as a quote block. A template brief is marked, with why the model's brief failed."""
    if not brief:
        return tag("div", "No brief: this holder is not called directly.", cls="mc-note")
    quote = tag("div", join([tag("p", line) for line in brief.get("lines") or []]), cls="mc-brief")
    if brief.get("brief_source") == "template":
        source = join([badge("Template brief", "amber"), " ",
                       tag("span", f"the model's brief failed a check: {brief.get('fallback_reason') or 'unknown'}",
                           cls="mc-note")])
    else:
        source = tag("span", "Written by the model; every number checked against the stored values.", cls="mc-note")
    problem = tag("div", f"Template brief still fails a check: {brief['template_problem']}", cls="mc-flag") \
        if brief.get("template_problem") else ""
    return join([quote, source, problem])


def figure_html(label: str, figure: dict) -> Html:
    """One amount: display, working, chips and caveats; or why it is unknown."""
    status = figure.get("status")
    name = tag("b", label)
    if status == "computed":
        caveats = [tag("div", f"Caveat: {item['text']}", cls="mc-note") for item in figure.get("caveats") or []]
        check = figure.get("printed_check") or {}
        checked = [tag("div", join([badge("Cross-checked", "green"), " ", check["text"]]), cls="mc-note")] \
            if check.get("status") == "matches" else \
            [tag("div", f"Printed amount: {check['text']}", cls="mc-note")] if check.get("status") == "not_compared" else []
        body = join([name, ": ", figure["display"], tag("div", f"Working: {figure['working']}", cls="mc-working"),
                     *checked, tag("div", chips(figure)), *caveats])
    elif status == "none":
        body = join([name, ": none retained"])
    elif status == "not_tendering":
        body = join([name, ": not tendering ", tag("span", f"({figure.get('reason') or 'no reason recorded'})", cls="mc-note")])
    elif status == "shares_only":
        body = join([name, ": ", figure["shares_display"], "; value ", unknown(figure.get("reason")),
                     tag("div", chips(figure))])
    elif status == "not_applicable":
        body = join([name, ": not applicable ", tag("span", f"({figure.get('reason') or ''})", cls="mc-note")])
    else:
        body = join([name, ": ", unknown(figure.get("reason") or "not verified")])
    return tag("div", body, cls="mc-item")


def timing_html(label: str, timing: dict) -> Html:
    """One timing: pill, words, the rule and its citations from this event's own pages."""
    status = timing.get("status")
    name = tag("b", label)
    if status not in TIMING_PILLS:
        return tag("div", join([name, ": ", timing_pill(status, timing.get("reason")), " ",
                                unknown(timing.get("reason") or "not verified")]), cls="mc-item")
    if status == "not_applicable":
        return tag("div", join([name, ": not applicable ", tag("span", f"({timing.get('reason') or ''})", cls="mc-note")]),
                   cls="mc-item")
    words = timing.get("display") or timing.get("when") or timing.get("period") or ""
    parts = [name, ": ", timing_pill(status, words), " ", words]
    if timing.get("settlement_as_printed"):
        parts.append(tag("div", f"Settlement as printed: \"{timing['settlement_as_printed']}\"", cls="mc-quote"))
    if timing.get("rule"):
        parts.append(tag("div", f"Rule: {timing['rule']}", cls="mc-note"))
    parts.append(tag("div", chips(timing.get("sources") or [], empty="no rule citation")))
    for refs in timing.get("sources") or []:
        for quote in refs.get("quotes") or []:
            parts.append(tag("div", f"“{quote}”", cls="mc-quote"))
    if timing.get("note"):
        parts.append(tag("div", timing["note"], cls="mc-note"))
    if timing.get("todo"):
        parts.append(tag("div", f"To check: {timing['todo']}", cls="mc-note"))
    return tag("div", join(parts), cls="mc-item")


def section(title: str, body: object) -> Html:
    """A small upper-case heading and its body."""
    return join([tag("div", title, cls="mc-section"), body])


def bullets(items: list, empty: str = "none") -> Html:
    """A short list, or a muted word when it is empty."""
    if not items:
        return tag("div", empty, cls="mc-note")
    return tag("ul", join([tag("li", item) for item in items]), cls="mc-list")


def displayed_timing(entry: dict, person: dict) -> tuple[str, dict] | None:
    """(key, timing) whose stored words are the card's timing_display, or None when it is unknown."""
    for key, timing in (person.get("timing") or {}).items():
        words = timing.get("display") or timing.get("when")
        if words and words == entry.get("timing_display"):
            return key, timing
    return None


def why_now_html(entry: dict, person: dict) -> Html:
    """The timing behind the card's pill, with its rule citation; other timings follow, smaller."""
    shown = displayed_timing(entry, person)
    parts = []
    if shown:
        parts.append(timing_html(shown[0].replace("_", " ").capitalize(), shown[1]))
    else:
        reason = str(entry.get("timing_display") or "").removeprefix("unknown: ") or "no timing stored"
        parts.append(tag("div", join([timing_pill(entry.get("timing_display_status"), reason), " ", unknown(reason)]),
                         cls="mc-item"))
    others = [(key, timing) for key, timing in (person.get("timing") or {}).items() if not shown or key != shown[0]]
    if others:
        parts.append(tag("div", "Other timing", cls="mc-label"))
        parts += [timing_html(key.replace("_", " ").capitalize(), timing) for key, timing in others]
    return join(parts)


def amounts_html(person: dict) -> Html:
    """Every amount with its working and the pages behind it."""
    return join([figure_html(key.replace("_", " ").capitalize(), figure)
                 for key, figure in (person.get("amounts") or {}).items()])


def evidence_nodes(person: dict) -> list:
    """Everything that carries a page reference for this person: computed amounts, then name and role."""
    amounts = [figure for figure in (person.get("amounts") or {}).values() if figure.get("status") == "computed"]
    return amounts + [person.get("evidence") or []]


def evidence_html(person: dict, first_as_chip: bool = True) -> Html:
    """All evidence chips. The first is the main "Open source page" chip, or is left out when the
    page draws it as a button instead (first_as_chip=False)."""
    refs = evidence_refs(evidence_nodes(person))
    if not refs:
        return tag("span", "no page link stored", cls="mc-note")
    rest = [chip(ref) for ref in refs[1:]]
    if not first_as_chip:
        return join(rest) if rest else tag("span", "no other pages", cls="mc-note")
    first = link(refs[0]["link"], f"Open source page · {refs[0]['label']} ↗", cls="mc-chip mc-chip-primary",
                 title=refs[0].get("quote") or None)
    return join([first, *rest])


def prep_sections(entry: dict, person: dict, brief: dict | None, first_as_chip: bool = True) -> dict[str, Html]:
    """The call prep sheet in reading order: brief, why now, amounts, evidence, confidence, family, flags, rank."""
    confidence = person.get("confidence") or {}
    family = person.get("family_group")
    flags = person.get("flags") or []
    return {
        "brief": section("Brief", brief_html(brief)),
        "why_now": section("Why now", why_now_html(entry, person)),
        "amounts": section("Amounts and workings", amounts_html(person)),
        "evidence": section("Evidence", tag("div", evidence_html(person, first_as_chip))),
        "confidence": section("Confidence", join([confidence_badge(confidence.get("level")),
                                                  bullets(confidence.get("reasons") or [])])),
        "family": section("Family and other events", join([
            tag("div", join([tag("b", "Family: "), f"{family['id']}: {family['reason']}" if family else "none found"]),
                cls="mc-item"),
            tag("div", join([tag("b", "Also seen in: "), also_seen_in(person)]), cls="mc-item")])),
        "flags": section("Flags", join([tag("div", flag, cls="mc-flag") for flag in flags]) if flags
                         else tag("div", "none", cls="mc-note")),
        "rank": section("Why this rank", bullets(entry.get("rank_reasons") or [])),
    }


def detail_html(entry: dict, person: dict, brief: dict | None) -> Html:
    """The whole call prep sheet as one block (the table view and tests use it)."""
    return join(list(prep_sections(entry, person, brief).values()))


# ---------- what we didn't trust, run progress ----------

COMPLETENESS_TONES = {"complete": "green", "not checked": "grey", "values unverified": "amber",
                      "rows missing": "red", "sum exceeds printed total": "red"}


def completeness_html(results: dict) -> Html:
    """One coloured line per holder-table check. The line's words say the status too."""
    if not results:
        return tag("div", "No holder table is checked for this event type.", cls="mc-note")
    lines = []
    for key, result in results.items():
        tone = COMPLETENESS_TONES.get(result.get("status"), "red")
        words = completeness_lines({key: result})[0].removeprefix("- ")
        lines.append(tag("div", join([tag("span", "", cls=f"mc-dot mc-dot-{tone}"), tag("span", words)]), cls="mc-status"))
    return join(lines)


_STEP_DONE = re.compile(r"^STEP (\S+) done ([\d.]+)s calls=(\d+) cached=(\d+) cost=\$([\d.]+)$")
_TOTAL = re.compile(r"^total\s+([\d.]+)\s+(\d+)\s+(\d+)\s+([\d.]+)$")


def parse_step_line(line: str) -> dict | None:
    """A "STEP <name> done ..." line from run.py as {step, seconds, calls, cached, cost}, else None."""
    match = _STEP_DONE.match(line.strip())
    if not match:
        return None
    step, seconds, calls, cached, cost = match.groups()
    return {"step": step, "seconds": seconds, "calls": calls, "cached": cached, "cost": cost}


def parse_total_line(line: str) -> dict | None:
    """run.py's closing "total" timeline row as {seconds, calls, cached, cost}, else None."""
    match = _TOTAL.match(line.strip())
    if not match:
        return None
    seconds, calls, cached, cost = match.groups()
    return {"seconds": seconds, "calls": calls, "cached": cached, "cost": cost}


def step_html(row: dict) -> Html:
    """One finished step: name, seconds, calls (cached), cost, as run.py printed them."""
    return tag("div", join(["✓ ", tag("b", row.get("step", "total")),
                            f" · {row['seconds']} s · {row['calls']} calls ({row['cached']} cached) · ${row['cost']}"]),
               cls="mc-step")


# ---------- dashboard pieces (FinSight shell) ----------

def _svg(paths: str, size: int = 22) -> Html:
    """A line icon drawn in the current text colour. Decorative, so hidden from screen readers."""
    return Html(f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths}</svg>')


ICONS = {
    "layers": _svg('<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 13 9 5 9-5"/><path d="m3 17.5 9 5 9-5"/>'),
    "flame": _svg('<path d="M12 22c4 0 7-2.7 7-6.6 0-3.6-2.6-5.7-4-8.9-.6 2.2-1.7 3.4-3 4.1C12 7 10.6 4.4 9 2c-.4 '
                  '3.7-4 6.6-4 11.4C5 18.9 8 22 12 22Z"/>'),
    "people": _svg('<circle cx="9" cy="8" r="3.2"/><path d="M3 20c.6-3.4 3-5.4 6-5.4s5.4 2 6 5.4"/>'
                   '<circle cx="17" cy="9" r="2.6"/><path d="M15.6 14.8c2.6-.3 4.8 1.4 5.4 4.6"/>'),
    "IPO": _svg('<path d="M3 17 9 11l4 4 8-8"/><path d="M15 7h6v6"/>', 18),
    "Buyback": _svg('<path d="M4 7h13l-3-3"/><path d="M20 17H7l3 3"/>', 18),
    "OFS (stock exchange)": _svg('<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>', 18),
}
TYPE_TONES = {"IPO": "lavender", "Buyback": "peach", "OFS (stock exchange)": "teal"}


def brand_html() -> Html:
    """The FinSight mark, name and subtitle for the top of the sidebar."""
    mark = Html('<svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">'
                '<path d="M5 30 17 4l12 26" stroke="#e9cfa5" stroke-width="1.6" stroke-linecap="round"/>'
                '<path d="M11.5 21.5c3.8-1.6 7.2-1.6 11 0" stroke="#c9b6f2" stroke-width="1.4" stroke-linecap="round"/></svg>')
    words = tag("div", join([tag("div", "FinSight", cls="mc-brand-name"), tag("div", "Wealth Intelligence", cls="mc-brand-sub")]))
    return tag("div", join([mark, words]), cls="mc-brand")


def greeting_html(greeting: str, summary: str) -> Html:
    """The page greeting and the one-line summary under it."""
    return tag("div", join([tag("h1", greeting), tag("p", summary)]), cls="mc-greeting")


def page_title_html(title: str, sub: str) -> Html:
    """A page heading and its one-line purpose."""
    return join([tag("h1", title, cls="mc-page-title"), tag("p", sub, cls="mc-page-sub")])


def stat_card(icon: str, value: object, label: str, note: str, tone: str) -> Html:
    """A KPI card: round icon, large number, label, and what the number counts."""
    return tag("div", join([
        tag("div", ICONS[icon], cls=f"mc-stat-icon mc-icon-{tone}"),
        tag("div", join([tag("div", str(value), cls="mc-stat-value"), tag("div", label, cls="mc-stat-label"),
                         tag("div", note, cls="mc-stat-note")])),
    ]), cls="mc-stat")


def panel_head(title: str, right: object = "") -> Html:
    """A panel's title row, with an optional note on the right."""
    return tag("div", join([tag("span", title, cls="mc-panel-title"), tag("span", right, cls="mc-filter-chip")]),
               cls="mc-panel-head")


def legend_html(mix: list[dict], colours: dict[str, str]) -> Html:
    """Donut legend rows: colour dot, type, share. The words carry the meaning, not the colour."""
    cells = []
    for row in mix:
        dot = Html(f'<span class="mc-legend-dot" style="background:{esc(colours.get(row["type"], "#94a3b8"))}"></span>')
        cells += [dot, tag("span", f"{row['type']} ({row['events']})"), tag("span", f"{row['share']}%")]
    return tag("div", join(cells), cls="mc-legend")


def feed_item_html(item: dict) -> Html:
    """One Recent Intelligence row; its preview (source, dates, checks) opens on hover or focus."""
    when = item["date"]
    tone = TYPE_TONES.get(item["type"], "lavender")
    top = item.get("top")
    amount = str((top or {}).get("amount_display") or "")
    amount = "amount unknown" if not amount or amount.startswith("unknown") else amount
    sub = f"{item['callable']} to call · top: {top['name_as_printed']} ({amount})" if top else f"{item['callable']} to call"
    docs = join([link(document.get("url"), f"{doc_label(str(document.get('doc_type') or 'document'))} ↗",
                      title=document.get("note")) for document in item["documents"]]) or unknown("no documents listed")
    preview = tag("dl", join([
        tag("dt", "Source"), tag("dd", docs),
        tag("dt", "Published"), tag("dd", unknown("the document's publication date is not stored")),
        tag("dt", when["kind"].capitalize()), tag("dd", join([text_or_unknown(when["as_printed"], when.get("reason")),
                                                             " · ", when["status"]])),
        tag("dt", "First processed"), tag("dd", text_or_unknown(item["detected"], "no successful run in runs.csv")),
        tag("dt", "Checks"), tag("dd", "; ".join(item["verification"])),
    ]))
    return tag("div", join([
        tag("div", ICONS.get(item["type"], ICONS["IPO"]), cls=f"mc-feed-icon mc-icon-{tone}"),
        tag("div", join([
            tag("div", join([tag("span", f"{item['type']} · {item['company']}", cls="mc-feed-title"),
                             tag("span", when["as_printed"] or "date unknown", cls="mc-feed-when")]), cls="mc-feed-top"),
            tag("div", sub, cls="mc-feed-sub"),
            tag("div", preview, cls="mc-preview"),
        ]), cls="mc-feed-main"),
    ]), cls="mc-feed")


def mix_legend_html(mix: list[dict], colours: dict[str, str]) -> Html:
    """Event Mix legend in words: type, events, callable people, share of events."""
    cells = []
    for row in mix:
        dot = Html(f'<span class="mc-legend-dot" style="background:{esc(colours.get(row["type"], "#94a3b8"))}"></span>')
        people = f"{row['people']} callable {'person' if row['people'] == 1 else 'people'}"
        cells += [dot, tag("span", f"{row['type']} · {row['events']} event{'s' if row['events'] != 1 else ''} · {people}"),
                  tag("span", f"{row['share']}%")]
    return tag("div", join(cells), cls="mc-legend")


def notification_html(note: dict) -> Html:
    """One notification: level badge, title, detail."""
    tone = "amber" if note["level"] == "warning" else "neutral"
    return tag("div", join([badge(note["level"], tone), " ", tag("span", note["title"], cls="mc-note-title"),
                            tag("div", note["detail"], cls="mc-note-detail")]), cls="mc-note-item")


# ---------- RM workflow pieces ----------

def chart_head_html(title: str, subtitle: str) -> Html:
    """A chart's title and its one-line plain-English subtitle."""
    return tag("div", join([tag("div", title, cls="mc-panel-title"), tag("div", subtitle, cls="mc-chart-sub")]),
               cls="mc-chart-head")


def call_row_html(call: dict, position: int) -> Html:
    """One Today's-calls row: position, name, company, amount, timing pill, confidence.

    Hover or focus reveals the brief's first line, the source page and the checks behind it.
    """
    entry, person, brief = call["entry"], call.get("person") or {}, call.get("brief") or {}
    lines = brief.get("lines") or []
    status, words = entry.get("timing_display_status"), str(entry.get("timing_display") or "")
    pill = timing_pill(status, words if status in TIMING_PILLS else words.removeprefix("unknown: ") or None)
    reasons = (person.get("confidence") or {}).get("reasons") or []
    source = call.get("source")
    checks = ("brief by the model, numbers checked" if brief.get("brief_source") == "llm"
              else "template brief" if brief else "no brief")
    preview = tag("dl", join([
        tag("dt", "Brief"), tag("dd", lines[0] if lines else unknown("no brief stored")),
        tag("dt", "Source"), tag("dd", chip(source) if source else unknown("no page link stored")),
        tag("dt", "Checks"), tag("dd", "; ".join([*reasons[:2], checks])),
    ]))
    return tag("div", join([
        tag("div", str(position), cls="mc-call-rank"),
        tag("div", join([
            tag("div", join([tag("span", entry["name_as_printed"], cls="mc-feed-title"),
                             tag("span", call["event"]["spec"].company, cls="mc-call-company")]), cls="mc-call-top"),
            tag("div", amount_text(entry.get("amount_display")), cls="mc-call-amount"),
            tag("div", join([pill, confidence_badge(entry.get("confidence"))]), cls="mc-card-foot"),
            tag("div", preview, cls="mc-preview"),
        ]), cls="mc-feed-main"),
    ]), cls="mc-feed")


CHECK_TONES = {"complete": "green", "not checked": "grey", "values unverified": "amber",
               "rows missing": "red-outline", "sum exceeds printed total": "red-outline"}


def check_pills_html(rows: list[dict]) -> Html:
    """Holder-table checks as pills: event, check, status in words, coloured by status."""
    if not rows:
        return tag("div", "No holder table is checked for these event types.", cls="mc-note")
    pills = [badge(f"{row['Event']} · {row['Check']}: {row['Status']}", CHECK_TONES.get(row["Status"], "red-outline"))
             for row in rows]
    return tag("div", join(pills), cls="mc-pills")


# ---------- live feed ----------

FEED_TONES = {"ready": "green", "failed": "red-outline", "waiting": "amber", "unsupported": "grey"}


def feed_status_chip(row: dict) -> Html:
    """The item's status in words, coloured by status; the reason follows in muted text."""
    chip = badge(row["status_label"], FEED_TONES.get(row["status"], "grey"))
    reason = tag("span", f" {row['reason']}", cls="mc-note") if row.get("reason") else ""
    return join([chip, reason])


def feed_item_row_html(row: dict) -> Html:
    """One discovered item: type, company, date as printed, source link, status chip."""
    item = row["item"]
    when = row.get("event_date") or {}
    upcoming = tag("div", f"{when.get('kind', 'event date')}: {when.get('as_printed')}", cls="mc-call-company") \
        if when.get("as_printed") else ""
    return tag("div", join([
        tag("div", join([badge(item.get("label") or item.get("class") or "other", "accent"), " ",
                         tag("span", item.get("company") or item.get("title"), cls="mc-feed-title")]), cls="mc-call-top"),
        tag("div", join([tag("span", item.get("published") or "date not printed", cls="mc-feed-when"), " · ",
                         link(item.get("link"), f"{item.get('source_name') or item.get('source')} ↗", cls="mc-chip",
                              title=item.get("title")), upcoming]), cls="mc-feed-sub"),
        tag("div", feed_status_chip(row), cls="mc-card-foot"),
    ]), cls="mc-feed-main")


def feed_header_html(header: dict) -> Html:
    """"Sources: ...; last refreshed ...; N items, M events, K call lists"."""
    if not header["refreshed_at"]:
        return tag("div", "Discovery has not run yet.", cls="mc-chart-sub")
    ok = ", ".join(source["name"] for source in header["ok"]) or "none answered"
    off = ", ".join(source["name"].split(" · ")[0] for source in header["disabled"])
    stamp = str(header["refreshed_at"]).replace("T", " ").replace("+00:00", " UTC")
    parts = [f"Sources: {ok}"]
    if off:
        parts.append(f"off by their own terms: {off}")
    parts += [f"last refreshed {stamp}",
              f"{header['items']} items, {header['events']} events, {header['call_lists']} call lists"]
    return tag("div", "; ".join(parts) + ".", cls="mc-chart-sub")


# ---------- provenance, check results ----------

CHECK_LEVEL_TONES = {"pass": "green", "warning": "amber", "fail": "red-outline"}


def provenance_html(found: dict) -> Html:
    """"Discovered from <source> on <date>" with links to the source items, or "Added by hand"."""
    links = [link(item["link"], f"{item['title']} ↗", cls="mc-chip") for item in found.get("links") or [] if item.get("link")]
    tone = "accent" if found.get("kind") == "discovered" else "neutral"
    return tag("div", join([badge(found["text"], tone), " ", *links]), cls="mc-card-foot")


def check_lines_html(lines: list[tuple[str, str]]) -> Html:
    """Check results as lines, each led by its level in words (pass, warning, fail)."""
    return join([tag("div", join([badge(level, CHECK_LEVEL_TONES.get(level, "grey")), " ", words]), cls="mc-status")
                 for level, words in lines])
