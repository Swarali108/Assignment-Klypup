"""RM view models: turn stored pipeline fields into the JSON the web app shows.

Every number comes from a stored field (crore_high, days_since, cost totals) or plain code
arithmetic on such fields (a sum of stored crore values). Text is the stored display text,
cleaned for an RM reader; no field or file names reach the response.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote as urlquote

from agents.names import name_tokens
from agents.rank import fund_like
from api import prefs, store
from config.ranking import ORG_PLACE_TOKENS, ORG_STRONG_TOKENS

TIER_ORDER = {"cash_now": 0, "unlock": 1, "holding": 2}
TIER_LABELS = {"cash_now": "Cash in hand", "unlock": "Shares just unlocked", "holding": "Holds shares"}
# Proceeds timing statuses that mean the money has been paid or is paid at listing/settlement.
CASH_STATUSES = ("in_hand", "at_listing", "settles", "after_date")
# A scheduled payment this many days ahead (or any day in the past) counts as cash now.
CASH_SOON_DAYS = 30
# An unlock this recent (days) is a fresh reason to call; older unlocks are plain holdings.
FRESH_UNLOCK_DAYS = 120
TYPE_LABELS = {"ipo": "IPO", "buyback": "Buyback", "ofs_stock_exchange": "Offer for sale (exchange)",
               "block_deal": "Block deal", "insider_sale": "Insider sale"}
DOC_LABELS = {"rhp": "Red herring prospectus", "prospectus": "Prospectus", "letter_of_offer": "Letter of offer",
              "public_announcement": "Public announcement", "announcement": "Exchange notice", "news": "News article"}
INPUT_LABELS = {"shares_offered": "Shares offered", "offer_price": "Offer price", "price_band": "Price band",
                "waca_per_share": "Average cost per share", "shares_held_pre_offer": "Shares held before the offer",
                "buyback_price": "Buyback price", "shares_accepted": "Shares accepted", "floor_price": "Floor price",
                "shares_intended": "Shares offered in the buyback", "acceptance_ratio": "Acceptance ratio",
                "entitlement_ratio": "Buyback entitlement (general category)",
                "listing_date": "Listing date", "allotment_date": "Allotment date", "payment_date": "Payment date",
                "sale_date": "Sale date", "greenshoe_shares": "Extra (green-shoe) shares"}
AMOUNT_LABELS = {"proceeds": "Cash from the sale", "gain": "Gain over cost", "retained": "Value of shares kept"}
SECTION_LABELS = {"selling_shareholders": "Selling shareholders", "seller_amounts": "Seller amounts",
                  "waca": "Average cost of shares", "promoter_holding": "Promoter holdings",
                  "shareholding_pattern": "Shareholding pattern", "offer_structure": "Offer structure",
                  "price": "Offer price", "timetable": "Timetable", "buyback_terms": "Buyback terms",
                  "promoter_intention": "Promoter intention", "ofs_terms": "Sale terms", "ofs_sellers": "Sellers",
                  "lock_in": "Lock-in"}
FIELD_LABELS = {**INPUT_LABELS, "name_as_printed": "Name", "role_as_printed": "Role",
                "table_total_as_printed": "Table total", "intention_as_printed": "Intention statement",
                "record_date": "Record date", "fresh_issue_size": "Fresh issue size", "qualifier": "Share qualifier",
                "opening_date": "Opening date", "greenshoe_total": "Green-shoe total",
                "sale_date_retail": "Retail sale date"}
REJECTION_WORDS = {
    "no evidence": "No supporting quote was given",
    "not in this person's row": "The number was not in this person's row of the table",
    "value not in quote": "The value was not inside the quoted text",
    "heading not above name": "The role heading was not above this name",
    "quote not on page": "The quote was not found on the cited page",
    "name not on page": "The name was not found on the cited page",
    "name not near quote": "The name was not next to the quoted value",
}
STEP_LABELS = {"locate": "Find the right pages", "extract": "Read the tables", "people": "Match people and families",
               "rank": "Rank who to call", "brief": "Write call briefs", "report": "Assemble the call list",
               "check": "Check the documents"}


# ---------- small helpers ----------

def as_of() -> date:
    """Today, or AURELIA_AS_OF (YYYY-MM-DD) for a fixed demo date."""
    fixed = os.environ.get("AURELIA_AS_OF")
    return date.fromisoformat(fixed) if fixed else date.today()


def dec(value: object) -> Decimal | None:
    """A stored number as Decimal, or None."""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def crore(value: Decimal | None) -> float | None:
    """A crore amount as a float rounded to 2 places for JSON."""
    return None if value is None else float(round(value, 2))


def indian(number: Decimal, places: int = 2) -> str:
    """1234567.8 -> '12,34,567.80' (Indian digit grouping)."""
    text = f"{abs(number):.{places}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    sign = "-" if number < 0 else ""
    return sign + whole + (f".{frac}" if frac else "")


def cr_text(value: Decimal | None) -> str:
    """'₹1,234.56 Cr' or ''."""
    return "" if value is None else f"₹{indian(value)} Cr"


def money_text(figure: dict) -> str:
    """'₹63.88 Cr'; under ₹10 lakh the stored rupee figure in Indian format ('₹1,35,200'), never '₹0.00 Cr'."""
    high, rupees = dec(figure.get("crore_high")), dec(figure.get("rupees_high"))
    if high is not None and high < Decimal("0.1") and rupees is not None:
        return f"₹{indian(rupees, 0)}"
    return cr_text(high)


def value_cr(figure: dict) -> float | None:
    """The stored crore_high as a float; a tiny amount (stored as 0.00 crore) uses rupees_high / 1 crore instead."""
    high, rupees = dec(figure.get("crore_high")), dec(figure.get("rupees_high"))
    if high is not None and high < Decimal("0.1") and rupees is not None:
        return float(round(rupees / Decimal(10_000_000), 6))
    return crore(high)


def working_text(figure: dict) -> str | None:
    """The stored working line; a result that rounds to '₹0.00 crore' is shown in rupees instead ('100 × ₹151 = ₹15,100')."""
    text = figure.get("working")
    high, rupees = dec(figure.get("crore_high")), dec(figure.get("rupees_high"))
    if text and high is not None and high < Decimal("0.005") and rupees:
        return re.sub(r"₹0\.00 crore", f"₹{indian(rupees, 0)}", text)
    return text


def tidy_lines(lines: list[str], person: dict) -> list[str]:
    """Brief lines as stored, with a '₹0.00 crore' amount shown in rupees and a doubled 'in hand since' fixed."""
    out = []
    rupees = dec(((person.get("amounts") or {}).get("proceeds") or {}).get("rupees_high"))
    for line in lines:
        if rupees:
            line = line.replace("₹0.00 crore", f"₹{indian(rupees, 0)}")
        out.append(line.replace("in hand since in hand since", "in hand since"))
    return out


def _age_phrase(days: int) -> str:
    """'today' / '25 days ago', the wording the pipeline stores in why, rank reasons and briefs."""
    return "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"


def age_swaps(event: dict, entry: dict, person: dict) -> dict[str, str]:
    """{stored '(N days ago)' phrase: the same phrase counted to as_of()} for one ranked person.

    The pipeline writes how long ago something happened into why, rank reasons and brief lines on the day it ran;
    the date behind each phrase is stored (an unlock's ends_on, the event's money date), so the count is redone
    here and every screen agrees with the live timing label. Nothing is guessed: no date, no change."""
    swaps: dict[str, str] = {}
    proceeds = (person.get("timing") or {}).get("proceeds") or {}
    for trigger in entry.get("triggers") or [entry.get("trigger") or {}]:
        stored = trigger.get("days_since")
        if trigger.get("kind") == "unlock":
            iso = trigger.get("ends_on")
        elif trigger.get("kind") == "proceeds" and proceeds.get("status") != "settles":
            iso = money_date(event)["date_iso"]
        else:
            iso = None
        if not stored or not iso:  # undated, or "today" (a bare word that would also match other uses)
            continue
        try:
            fresh = (as_of() - date.fromisoformat(iso[:10])).days
        except ValueError:
            continue
        if fresh >= 0 and fresh != stored:
            swaps[f"{stored} days ago"] = _age_phrase(fresh)
    return swaps


def with_fresh_ages(text: str, swaps: dict[str, str]) -> str:
    """Text with each stored age phrase in `swaps` replaced in one pass (so 25 -> 26 and 26 -> 27 cannot chain)."""
    if not swaps or not text:
        return text
    pattern = re.compile(r"(?<![\d,.])(?:" + "|".join(re.escape(k) for k in sorted(swaps, key=len, reverse=True)) + r")\b")
    return pattern.sub(lambda m: swaps[m.group(0)], text)


def fresh_brief_lines(brief: dict, swaps: dict[str, str]) -> list[str]:
    """The brief's lines with the age phrases counted to as_of(). A model brief is filled again from its stored
    template and placeholder values (only code-written values change); a template brief is code text. A brief
    whose stored template does not reproduce its lines is left as stored."""
    lines = list(brief.get("lines") or [])
    if not swaps or not lines:
        return lines
    if brief.get("brief_source") != "llm":
        return [with_fresh_ages(line, swaps) for line in lines]
    from agents.brief import fill_placeholders  # lazy: the model client behind agents.brief is not needed elsewhere
    accepted = next((a for a in reversed(brief.get("attempts") or []) if a.get("problem") is None and a.get("raw_lines")), None)
    values = brief.get("placeholders") or {}
    try:
        if not accepted or fill_placeholders(accepted["raw_lines"], values) != lines:
            return lines
        return fill_placeholders(accepted["raw_lines"], {k: with_fresh_ages(str(v), swaps) for k, v in values.items()})
    except (KeyError, TypeError):
        return lines


def nice_date(iso: str | None) -> str:
    """'2026-03-11' -> '11 Mar 2026'."""
    if not iso:
        return ""
    try:
        day = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return f"{day.day} {day.strftime('%b %Y')}"


def ago(iso: str | None) -> str:
    """'in 11 days' / '23 days ago' / 'today' relative to as_of()."""
    if not iso:
        return ""
    try:
        days = (as_of() - date.fromisoformat(iso[:10])).days
    except ValueError:
        return ""
    if days == 0:
        return "today"
    if days < 0:
        return f"in {-days} day{'s' if days != -1 else ''}"
    return f"{days} day{'s' if days != 1 else ''} ago"


_DOUBLES = [(re.compile(r"\b(up to)\s+up to\b", re.I), r"\1"), (re.compile(r"\b(shares)\s+shares\b", re.I), r"\1"),
            (re.compile(r"\b(scheduled for|due on)\s+on or about\b", re.I), r"\1 on or about"),
            (re.compile(r"\s+"), " ")]

# Stored internal wording -> RM wording. Applied once, in clean(), so every screen gets the same words.
# Order matters: the longer phrase first.
_UNSURE_WORDS = "We could not confirm whether this holder is a person or an organisation"
_RM_WORDING = [
    (re.compile(r"(?:holder type unsure\s*[:;]?\s*)?no entity marker and \d+ words?", re.I), _UNSURE_WORDS),
    (re.compile(r"holder type unsure", re.I), _UNSURE_WORDS),
    (re.compile(r"no entity or family marker", re.I), "The name alone does not show whether this is a person, a family or a company"),
    (re.compile(r"^Which (.+?) is not extracted\.?$", re.I), r"The filing does not say which \1."),
    (re.compile(r"\bnot extracted\b", re.I), "not stated in the filing"),
    (re.compile(r"\bextracted\b", re.I), "read"),
]


def clean(text: object) -> str:
    """Stored text for an RM: internal wording replaced, doubled words removed, first letter upper-case."""
    if not text:
        return ""
    out = str(text)
    for pattern, repl in _RM_WORDING:
        out = pattern.sub(repl, out)
    for pattern, repl in _DOUBLES:
        out = pattern.sub(repl, out)
    out = out.strip()
    return out[:1].upper() + out[1:]


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(cell: object) -> object:
    """A CSV cell safe for spreadsheets: text that starts (after any spaces) with a formula character gets a leading '."""
    if isinstance(cell, str) and (cell.startswith(_FORMULA_START) or cell.lstrip().startswith(_FORMULA_START)):
        return "'" + cell
    return cell


def plain_sections(text: object) -> str:
    """Replace section ids ('promoter_holding') with their RM words ('promoter holdings')."""
    out = str(text or "")
    for key, words in SECTION_LABELS.items():
        out = re.sub(rf"\b{key}\b", words.lower(), out)
    return out


def reason_words(text: object) -> str:
    """A stored 'why unknown' reason in RM words."""
    out = clean(text)
    if out.lower().startswith("states:"):
        return "The filing states: \u201c" + out[7:].strip() + "\u201d"
    return re.sub(r"\bnot verified\b", "not confirmed in the filing", out)


def type_label(event_type: str) -> str:
    """'IPO', 'Buyback', ..."""
    return TYPE_LABELS.get(event_type, event_type.replace("_", " ").title())


def spec_type_label(spec) -> str:
    """The event's type in words. A bulk deal is stored as a block deal; its id says which it is, and every screen
    (Today, events, calendar, event page) uses this one label for it."""
    if spec.event_type == "block_deal" and "bulk_deal" in spec.event_id:
        return "Bulk deal"
    return type_label(spec.event_type)


def event_ref(event: dict) -> dict:
    """{id, company, type, type_label} for nesting in other responses."""
    spec = event["spec"]
    return {"id": spec.event_id, "company": spec.company, "type": spec.event_type, "type_label": spec_type_label(spec)}


def people_by_id(event: dict) -> dict[str, dict]:
    """person_id -> people.json person."""
    return {p["person_id"]: p for p in (event["out"]["people"] or {}).get("people") or []}


def briefs_by_id(event: dict) -> dict[str, dict]:
    """person_id -> brief."""
    return {b["person_id"]: b for b in (event["out"]["briefs"] or {}).get("briefs") or []}


# ---------- evidence ----------

def doc_labels(event: dict) -> dict[str, str]:
    """source url -> 'Red herring prospectus' style label from the event file."""
    return {doc.url: DOC_LABELS.get(doc.doc_type, "Source document") for doc in event["spec"].documents}


def _fresh_fields(sha: str) -> dict:
    """{fetched_at, age_days, stale} of one source document (api/freshness.py), added to every evidence ref."""
    from api import freshness

    found = freshness.doc_freshness(sha)
    return {"fetched_at": found["fetched_at"], "age_days": found["age_days"], "stale": found["stale"]}


def evidence_ref(ref: dict, labels: dict[str, str]) -> dict | None:
    """One stored evidence object as {doc_sha, doc_label, pdf_index, printed_page, quote, url, image_url}."""
    url = ref.get("source_url") or ref.get("url")
    if not url:
        return None
    sha = store.url_sha(url)
    index = ref.get("pdf_index")
    quote = ref.get("quote") or ((ref.get("quotes") or [None])[0])
    if index is None:
        # An exchange record (a deal or disclosure row), not a PDF page: link to the exchange page and show the row.
        return {"doc_sha": sha, "doc_label": labels.get(url, "Exchange record"), "pdf_index": None,
                "printed_page": ref.get("printed_page") or ref.get("row_ref") or None, "quote": quote,
                "url": url, "source_url": url, "image_url": None, "cached": False}
    image = f"/api/evidence/page.png?doc_sha={sha}&pdf_index={index}"
    if quote:
        image += f"&quote={urlquote(str(quote))}"
    return {"doc_sha": sha, "doc_label": labels.get(url, "Source document"), "pdf_index": index,
            "printed_page": ref.get("printed_page") or None, "quote": quote,
            "url": f"/api/docs/{sha}.pdf#page={index}", "source_url": url, "image_url": image,
            "cached": store.pdf_path(sha) is not None, **_fresh_fields(sha)}


RUPEE_PER_SHARE_FIELDS = ("waca_per_share", "offer_price", "buyback_price", "floor_price")
_BARE_NUMBER = re.compile(r"^\d[\d,]*(\.\d+)?$")


def inputs_view(inputs: list[dict] | None, labels: dict[str, str]) -> list[dict]:
    """Stored figure inputs with RM labels and evidence refs; a bare per-share price gets its rupee sign."""
    rows = []
    for item in inputs or []:
        evidence = [e for e in (evidence_ref(ref, labels) for ref in item.get("evidence") or []) if e]
        value = clean(item.get("value"))
        if item.get("field") in RUPEE_PER_SHARE_FIELDS and isinstance(value, str) and _BARE_NUMBER.match(value.strip()):
            value = "₹" + value.strip()
        rows.append({"label": INPUT_LABELS.get(item.get("field"), clean(str(item.get("field", "")).replace("_", " "))),
                     "value": value, "evidence": evidence})
    return rows


# ---------- event-level dates ----------

def money_date(event: dict) -> dict:
    """The event's money date as stored: {kind, label, date_iso, confirmed}; date_iso None when unknown."""
    doc = event["out"]["people"] or {}
    listing = doc.get("listing") or {}
    if listing.get("listed_on") and listing.get("status") in ("verified", "scheduled"):
        confirmed = listing["status"] == "verified"
        return {"kind": "listing", "label": "Listed" if confirmed else "Listing due", "date_iso": listing["listed_on"],
                "confirmed": confirmed}
    dates = doc.get("buyback_dates") or {}
    for key, word in (("payment", "Buyback payment"), ("closing", "Buyback closes")):
        value = dates.get(key) or {}
        if value.get("status") == "verified" and value.get("date"):
            return {"kind": f"buyback_{key}", "label": word, "date_iso": value["date"], "confirmed": True}
    sale = doc.get("sale") or {}
    if sale.get("sale_date_parsed"):
        label = "Trade date" if event["spec"].event_type in ("block_deal", "insider_sale") else "Sale on the exchange"
        return {"kind": "ofs_sale", "label": label, "date_iso": sale["sale_date_parsed"], "confirmed": True}
    return {"kind": "unknown", "label": "Date not confirmed", "date_iso": None, "confirmed": False}


# ---------- tiers ----------

def _proceeds_cash(person: dict) -> bool:
    """Proceeds that are (or were) paid: a verified seller with cash timing, or a schedule within CASH_SOON_DAYS."""
    proceeds = (person.get("amounts") or {}).get("proceeds") or {}
    timing = (person.get("timing") or {}).get("proceeds") or {}
    if proceeds.get("status") not in ("computed", "unknown"):
        return False
    if proceeds.get("status") == "unknown" and person.get("seller_status") != "verified":
        return False
    status = timing.get("status")
    if status in CASH_STATUSES:
        return True
    days = timing.get("days_since")
    return status == "scheduled" and days is not None and days >= -CASH_SOON_DAYS


def fresh_unlock_days(entry: dict, person: dict) -> int | None:
    """Days since the most recent unlock, when it is within FRESH_UNLOCK_DAYS."""
    found = []
    for trigger in entry.get("triggers") or []:
        if trigger.get("kind") == "unlock" and trigger.get("days_since") is not None:
            found.append(trigger["days_since"])
    for period in ((person.get("timing") or {}).get("retained") or {}).get("periods") or []:
        if str(period.get("status", "")).startswith("unlocked") and period.get("days_since") is not None:
            found.append(period["days_since"])
    found = [days for days in found if 0 <= days <= FRESH_UNLOCK_DAYS]
    return min(found) if found else None


def tier_of(entry: dict, person: dict) -> tuple[str, str]:
    """(tier, label): the pipeline's call_tier when present, else a fallback from stored fields."""
    if entry.get("call_tier") in TIER_ORDER:
        return entry["call_tier"], entry.get("call_tier_label") or TIER_LABELS[entry["call_tier"]]
    if _proceeds_cash(person):
        days = ((person.get("timing") or {}).get("proceeds") or {}).get("days_since")
        label = "Cash due soon" if days is not None and days < 0 else TIER_LABELS["cash_now"]
        return "cash_now", label
    if fresh_unlock_days(entry, person) is not None:
        return "unlock", TIER_LABELS["unlock"]
    return "holding", TIER_LABELS["holding"]


def is_context(entry: dict, person: dict) -> bool:
    """A holder who gets no money from this event (buyback non-tendering)."""
    proceeds = (person.get("amounts") or {}).get("proceeds") or {}
    return proceeds.get("status") == "not_tendering" or person.get("participation") == "not tendering"


# ---------- amount / timing / confidence ----------

def figure_view(key: str, figure: dict, labels: dict[str, str]) -> dict:
    """One stored amount (proceeds, gain, retained) with value_cr, display, working and evidence."""
    status = figure.get("status")
    high, low = dec(figure.get("crore_high")), dec(figure.get("crore_low"))
    computed = status == "computed" and high is not None
    view = {"key": key, "label": AMOUNT_LABELS.get(key, clean(key)), "status": status,
            "value_cr": value_cr(figure) if computed else None,
            "low_cr": crore(low) if computed and low is not None else None,
            "display": clean(figure.get("display")) if computed else _unknown_display(figure),
            "short": money_text(figure) if computed else "",
            "working": working_text(figure) if computed else None,
            "reason": None if computed else reason_words(figure.get("reason")) or None,
            "inputs": inputs_view(figure.get("inputs"), labels),
            "caveats": [clean(c.get("text")) for c in figure.get("caveats") or [] if c.get("text")]}
    if key == "retained" and figure.get("shares_display"):
        view["shares_display"] = clean(figure["shares_display"])
    return view


def _unknown_display(figure: dict) -> str:
    """RM words for an amount that was not computed."""
    status = figure.get("status")
    if status == "not_applicable":
        return "Not applicable"
    if status == "not_tendering":
        return "Not tendering"
    if status == "shares_only":
        return "Value not disclosed"
    if status == "none":
        return "No shares kept"
    return "Amount not disclosed"


def _is_estimate(figure: dict, kind: str) -> bool:
    """Shares are always an estimate; cash is an estimate when the stored range is open or says 'up to'."""
    if kind == "shares":
        return True
    text = str(figure.get("display") or "").lower()
    return figure.get("crore_low") != figure.get("crore_high") or "up to" in text or "estimate" in text


def headline_amount(tier: str, person: dict) -> dict:
    """{value_cr|null, display, kind, estimate, reason} for the tier's money."""
    amounts = person.get("amounts") or {}
    key = "proceeds" if tier == "cash_now" else "retained"
    figure = amounts.get(key) or {}
    proceeds = amounts.get("proceeds") or {}
    if key == "retained" and figure.get("status") != "computed" and (proceeds.get("status") == "computed" or not figure):
        key, figure = "proceeds", proceeds
    kind = "cash" if key == "proceeds" else "shares"
    high = dec(figure.get("crore_high"))
    if figure.get("status") == "computed" and high is not None:
        tiny = high < Decimal("0.1")
        return {"value_cr": value_cr(figure), "low_cr": crore(dec(figure.get("crore_low"))) if not tiny else value_cr(figure),
                "display": money_text(figure), "detail": money_text(figure) if tiny else clean(figure.get("display")), "kind": kind, "estimate": _is_estimate(figure, kind),
                "reason": None, "source": key}
    reason = reason_words(figure.get("reason")) or "The filing does not print this holder's amount"
    if figure.get("status") == "shares_only" and figure.get("shares_display"):
        reason = f"{clean(figure['shares_display'])}; no price yet to value them"
    return {"value_cr": None, "low_cr": None, "display": _unknown_display(figure), "detail": None, "kind": kind,
            "estimate": False, "reason": reason, "source": key}


def cash_date(proceeds: dict, when: dict) -> str | None:
    """The day the cash arrives: an exchange sale's stored settlement day (T+1), else the event's money date."""
    if proceeds.get("status") == "settles" and proceeds.get("settles_on"):
        return proceeds["settles_on"]
    return when["date_iso"]


def headline_timing(tier: str, entry: dict, person: dict, event: dict) -> dict:
    """{label, status, date_iso, past} for the tier's money."""
    timing = person.get("timing") or {}
    when = money_date(event)
    if tier == "cash_now":
        proceeds = timing.get("proceeds") or {}
        status = proceeds.get("status") or entry.get("timing_display_status") or "unknown"
        date_iso = cash_date(proceeds, when)
        days = proceeds.get("days_since")
        if status == "scheduled" and days is not None and days > 0:
            label = f"Listing was due {nice_date(date_iso)} ({ago(date_iso)}); listing notice not yet seen"
            status = "due_past"
        elif status == "scheduled":
            label = f"Listing due {nice_date(date_iso)} ({ago(date_iso)})" if date_iso else clean(proceeds.get("when"))
        else:
            label = clean(proceeds.get("when")) or clean(entry.get("timing_display"))
        return {"label": label, "status": status, "date_iso": date_iso,
                "past": bool(date_iso and date_iso <= as_of().isoformat())}
    retained = timing.get("retained") or {}
    if not retained and timing.get("proceeds"):
        node = timing["proceeds"]
        status = node.get("status") or "unknown"
        if status == "not_applicable":
            label = "No payment from this event"
        elif status == "unknown":
            label = "Payment date not confirmed"
        else:
            label = clean(node.get("when")) or "Payment date not confirmed"
        when_iso = cash_date(node, when)
        return {"label": label, "status": status, "date_iso": when_iso if status != "not_applicable" else None,
                "past": bool(when_iso and when_iso <= as_of().isoformat())}
    periods = retained.get("periods") or []
    ends = [p.get("ends_on") for p in periods if p.get("ends_on")]
    date_iso = max(ends) if ends else None
    status = retained.get("status") or entry.get("timing_display_status") or "unknown"
    label = clean(retained.get("display")) or clean(entry.get("timing_display")) or "Lock-in end date not confirmed"
    if status == "unknown" or label.lower().startswith("unknown"):
        why = re.sub(r"^unknown:?\s*", "", str(retained.get("reason") or retained.get("display") or ""), flags=re.I).strip()
        label = "Lock-in end date not confirmed" + (f" ({why})" if why else "")
    if tier == "unlock":
        unlocked = [p["ends_on"] for p in periods if p.get("ends_on") and str(p.get("status", "")).startswith("unlocked")]
        date_iso = max(unlocked) if unlocked else date_iso
        if date_iso:
            label = f"Shares unlocked {nice_date(date_iso)} ({ago(date_iso)})"
    return {"label": label, "status": status, "date_iso": date_iso,
            "past": bool(date_iso and date_iso <= as_of().isoformat())}


def confidence_view(person: dict, entry: dict) -> dict:
    """{level, reason}."""
    conf = person.get("confidence") or {}
    level = conf.get("level") or entry.get("confidence") or "unknown"
    reasons = list(dict.fromkeys(clean(plain_sections(r)) for r in conf.get("reasons") or []))
    return {"level": level, "reason": "; ".join(reasons) if reasons else "No reason recorded", "reasons": reasons}


def why_line(entry: dict, tier: str, swaps: dict[str, str] | None = None) -> str:
    """One plain line: the pipeline's first rank reason when it writes RM words, else the stored why-money."""
    reasons = entry.get("rank_reasons") or []
    readable = [with_fresh_ages(r, swaps or {}) for r in rank_reason_words(reasons)]
    if entry.get("call_tier") and readable:
        return readable[0]
    return clean(entry.get("why_money")) or (readable[0] if readable else "")


def household_key(event_id: str, entry: dict) -> str | None:
    """A stable household id across the app: '<event_id>:<family id>'."""
    hid = entry.get("household_id") or (entry.get("family_group") or {}).get("id")
    return f"{event_id}:{hid}" if hid else None


def flag_words(flags: list[str]) -> list[str]:
    """Stored flags in RM words."""
    out = []
    for flag in flags or []:
        if flag.startswith("holder type unsure"):
            out.append("Could be a person or an organisation; check before calling")
        elif flag == "share count not verified":
            out.append("Share count could not be confirmed in the filing")
        else:
            out.append(clean(flag))
    return out


# ---------- call items ----------

def is_organisation(name: str | None, holder_type: str | None) -> bool:
    """A fund or company printed as a holder: its name reads as one (fund words, or a country at the end).

    Family vehicles are callable by design and are not organisations here."""
    if holder_type == "family_vehicle" or not name:
        return False
    tokens = name_tokens(name)
    if holder_type == "unsure" and fund_like(name):
        return True
    return any(t in ORG_STRONG_TOKENS for t in tokens) or bool(tokens and tokens[-1] in ORG_PLACE_TOKENS and len(tokens) <= 4)


def kind_label(name: str | None, holder_type: str | None) -> str | None:
    """'Family trust' / 'Family (HUF)' for a family vehicle; None for an ordinary person."""
    if holder_type != "family_vehicle":
        return None
    return "Family (HUF)" if re.search(r"\bhuf\b", name or "", re.I) and not re.search(r"\btrust\b", name or "", re.I) else "Family trust"


def call_item(event: dict, entry: dict, person: dict, brief: dict | None, rm: dict | None) -> dict:
    """One person in a call list."""
    tier, tier_label = tier_of(entry, person)
    eid = event["spec"].event_id
    swaps = age_swaps(event, entry, person)
    lines = tidy_lines(fresh_brief_lines(brief or {}, swaps), person)
    return {
        "id": f"{eid}/{entry['person_id']}",
        "event": event_ref(event),
        "person": {"id": entry["person_id"], "name": entry.get("name_as_printed") or person.get("name_as_printed"),
                   "role": entry.get("role_as_printed") or person.get("role_as_printed") or None,
                   "holder_type": entry.get("holder_type") or person.get("holder_type"),
                   "kind_label": kind_label(entry.get("name_as_printed") or person.get("name_as_printed"),
                                            entry.get("holder_type") or person.get("holder_type"))},
        "tier": tier, "tier_label": tier_label,
        "amount": headline_amount(tier, person),
        "timing": headline_timing(tier, entry, person, event),
        "confidence": confidence_view(person, entry),
        "why": why_line(entry, tier, swaps),
        "brief_first_line": lines[0] if lines else None,
        "household": None,
        "household_id": household_key(eid, entry),
        "rank": entry.get("rank"),
        "score": float(dec(entry.get("score")) or 0),
        "flags": flag_words(person.get("flags") or []),
        "rm": rm_brief(rm),
        "in_book": prefs.in_book(entry.get("name_as_printed") or person.get("name_as_printed")),
    }


def rm_brief(rm: dict | None) -> dict:
    """{status, follow_up, note} with defaults."""
    rm = rm or {}
    return {"status": rm.get("status") or "to_call", "follow_up": rm.get("follow_up_date"),
            "note": rm.get("note") or ""}


def sort_key(item: dict) -> tuple:
    """Tier, known amount before unknown, then stored rank within an event / score across events, then name."""
    return (TIER_ORDER.get(item["tier"], 9), item["amount"]["value_cr"] is None, -item["score"],
            item["person"]["name"] or "")


def event_lists(event: dict, rm_lookup: dict | None = None) -> dict:
    """{callable, entities, context} items for one event, callable in call order."""
    rm_lookup = rm_lookup or {}
    ranked = event["out"]["ranked"] or {}
    people, briefs = people_by_id(event), briefs_by_id(event)
    eid = event["spec"].event_id
    out = {"callable": [], "entities": [], "context": []}

    def build(entry: dict) -> dict:
        person = people.get(entry["person_id"]) or {}
        return call_item(event, entry, person, briefs.get(entry["person_id"]), rm_lookup.get((eid, entry["person_id"])))

    for entry in ranked.get("callable") or []:
        person = people.get(entry["person_id"]) or {}
        if is_organisation(entry.get("name_as_printed"), entry.get("holder_type")):
            out["entities"].append(build(entry))  # a fund or company is never a callable person
        elif "context" not in ranked and is_context(entry, person):
            item = build(entry)
            item["context_reason"] = _context_reason(person)
            out["context"].append(item)
        else:
            out["callable"].append(build(entry))
    for entry in ranked.get("entities") or []:
        out["entities"].append(build(entry))
    for entry in ranked.get("context") or []:
        item = build(entry)
        item["context_reason"] = clean(entry.get("context_reason")) or _context_reason(people.get(entry["person_id"]) or {})
        out["context"].append(item)
    if ranked.get("callable") and not any(e.get("call_tier") for e in ranked["callable"]):
        out["callable"].sort(key=lambda item: (TIER_ORDER.get(item["tier"], 9), item["amount"]["value_cr"] is None,
                                               item["rank"] or 0))
    for position, item in enumerate(out["callable"], start=1):
        item["position"] = position
    _attach_households(event, out["callable"])
    return out


def _context_reason(person: dict) -> str:
    """Why a holder gets no money from this event."""
    if (person.get("amounts") or {}).get("proceeds", {}).get("status") == "not_tendering":
        return "Not tendering shares in this buyback, so no money from it"
    return "No money from this event"


def _attach_households(event: dict, items: list[dict]) -> None:
    """Fill item['household'] = {id, label, members[], reason} for members of a stored family group."""
    groups = {g.get("id"): g for g in (event["out"]["people"] or {}).get("family_groups") or []}
    by_house: dict[str, list[dict]] = {}
    for item in items:
        if item["household_id"]:
            by_house.setdefault(item["household_id"], []).append(item)
    for hid, members in by_house.items():
        group = groups.get(hid.split(":", 1)[1]) or {}
        surname = (members[0]["person"]["name"] or "").split()[-1:] or [""]
        info = {"id": hid, "label": f"{surname[0].title()} household",
                "reason": clean("; ".join(group.get("reasons") or [])) or "Family link in the filing",
                "members": [{"id": m["id"], "name": m["person"]["name"], "role": m["person"]["role"],
                             "tier": m["tier"], "amount": m["amount"]} for m in members],
                "printed_members": group.get("members") or []}
        for member in members:
            member["household"] = info


def empty_reason(event: dict, lists: dict, docs: list[dict]) -> str | None:
    """Why an event has no one to call, in RM words; None when there is someone."""
    if lists["callable"]:
        return None
    if not event["processed"]:
        if any(doc["scanned"] for doc in docs):
            return "Scanned filing: text not readable yet, so no names could be read from it."
        if event["spec"].event_type not in store.SUPPORTED_TYPES:
            return "This kind of event is not supported yet."
        return "This event has not been processed yet."
    if lists["context"] and event["spec"].event_type == "buyback":
        count = len(lists["context"])
        rest = ", and the other holders named are companies or funds" if lists["entities"] else ""
        return (f"No individual gets money from this buyback: {count} named holder{'s' if count != 1 else ''} "
                f"said they will not tender{rest}. They are listed below for context.")
    if lists["context"]:  # block/bulk/insider deals and IPOs: the context rows are buyers or non-sellers
        count = len(lists["context"])
        holders = f"{count} other holder{'s' if count != 1 else ''} named {'gets' if count == 1 else 'get'}"
        if lists["entities"]:
            names = ", ".join(item["person"]["name"] for item in lists["entities"][:3])
            more = "" if len(lists["entities"]) <= 3 else f" and {len(lists['entities']) - 3} more"
            return (f"No individual to call: the money from this event goes to companies or funds ({names}{more}), "
                    f"and {holders} no money from it. They are listed below for context.")
        return f"No individual gets money from this event: {holders} no money from it. They are listed below for context."
    if lists["entities"]:
        names = ", ".join(item["person"]["name"] for item in lists["entities"][:3])
        more = "" if len(lists["entities"]) <= 3 else f" and {len(lists['entities']) - 3} more"
        return f"Every holder named is a company or fund ({names}{more}); there is no individual to call."
    return ("The documents were read, but they do not name any individual shareholder "
            "who gets money from this event.")


# ---------- events ----------

def documents_view(event: dict) -> list[dict]:
    """The event's documents with label, cache state and the scanned flag."""
    checks = {d.get("url"): d for d in (event["out"].get("check") or {}).get("documents") or []}
    docs = []
    for doc in event["spec"].documents:
        sha = store.url_sha(doc.url)
        state = store.scanned_state(sha, checks.get(doc.url))
        docs.append({"doc_sha": sha, "label": DOC_LABELS.get(doc.doc_type, "Source document"), "doc_type": doc.doc_type,
                     "note": doc.note, "source_url": doc.url, "url": f"/api/docs/{sha}.pdf" if state["cached"] else None,
                     "pages": state["pages"], "scanned": state["scanned"], **_fresh_fields(sha),
                     "scanned_label": "Scanned filing: text not readable yet" if state["scanned"] else None})
    return docs


def event_status(event: dict, docs: list[dict], running: set[str], failures: dict[str, str]) -> tuple[str, str]:
    """(status, plain reason): ready | processing | failed | scanned | not_supported | not_processed."""
    eid = event["spec"].event_id
    if eid in running:
        return "processing", "Processing now"
    if event["spec"].event_type not in store.SUPPORTED_TYPES:
        return "not_supported", "This kind of event is not supported yet"
    if not event["processed"] and any(doc["scanned"] for doc in docs):
        return "scanned", "Scanned filing: text not readable yet"
    if eid in failures and not event["processed"]:
        return "failed", failures[eid]
    if not event["processed"]:
        return "not_processed", "Not processed yet"
    return "ready", "Call list ready"


def failure_reasons() -> dict[str, str]:
    """event_id -> the latest failed discovery-run reason (RM words)."""
    found = {}
    for entry in store.discovery_log():
        if entry.get("status") == "failed":
            found[entry.get("event_id")] = clean(entry.get("reason")) or "Processing failed"
        elif entry.get("event_id") in found:
            found.pop(entry.get("event_id"))
    return found


PAID_EARLIER = "Cash received earlier"


def bucket(item: dict) -> str:
    """The section an item is counted under. Sale money paid out earlier counts as cash in hand, so a paid buyback
    reads as paid; the pipeline's own tier stays as it is for ranking."""
    return "cash_now" if item["tier"] == "holding" and item.get("tier_label") == PAID_EARLIER else item["tier"]


def cash_total(items: list[dict]) -> Decimal:
    """Sum of known cash amounts (stored crore values) for people in the cash-in-hand bucket."""
    return sum((Decimal(str(i["amount"]["value_cr"])) for i in items
                if bucket(i) == "cash_now" and i["amount"]["value_cr"] is not None and i["amount"]["kind"] == "cash"),
               Decimal(0))


def event_summary(event: dict, running: set[str], failures: dict[str, str], rm_lookup: dict | None = None) -> dict:
    """One row of the events index."""
    docs = documents_view(event)
    status, reason = event_status(event, docs, running, failures)
    lists = event_lists(event, rm_lookup) if event["processed"] else {"callable": [], "entities": [], "context": []}
    when = money_date(event) if event["processed"] else {"kind": "unknown", "label": "Date not confirmed",
                                                          "date_iso": None, "confirmed": False}
    tiers = {tier: sum(1 for i in lists["callable"] if bucket(i) == tier) for tier in TIER_ORDER}
    discovered = (event["raw"].get("discovery") or {})
    return {**event_ref(event), "status": status, "status_reason": reason,
            "people_count": len(lists["callable"]), "entities_count": len(lists["entities"]),
            "context_count": len(lists["context"]), "tier_counts": tiers,
            "cash_cr": crore(cash_total(lists["callable"])) if any(
                bucket(i) == "cash_now" and i["amount"]["value_cr"] is not None for i in lists["callable"]) else None,
            "listing_date": when["date_iso"] if when["kind"] == "listing" else None,
            "money_date": {**when, "display": nice_date(when["date_iso"]), "relative": ago(when["date_iso"])},
            "empty_reason": empty_reason(event, lists, docs),
            "docs": docs, "source": "discovered" if event["auto"] else "added",
            "discovered_on": str(discovered.get("first_seen") or "")[:10] or None}


def price_view(event: dict) -> dict:
    """The price basis: {kind, label, display, low, high, evidence[]}."""
    basis = (event["out"]["people"] or {}).get("price_basis") or {}
    labels = doc_labels(event)
    low, high = dec(basis.get("low")), dec(basis.get("high"))
    kind = basis.get("kind") or "unknown"
    words = {"offer_price": "Final offer price", "price_band": "Price band", "buyback_price": "Buyback price",
             "floor_price": "Floor price"}.get(kind, "Price")
    if high is None:
        display = "Price not confirmed"
    elif low is not None and low != high:
        display = f"₹{indian(low, 0 if low == low.to_integral() else 2)} to ₹{indian(high, 0 if high == high.to_integral() else 2)} per share"
    else:
        display = f"₹{indian(high, 0 if high == high.to_integral() else 2)} per share"
    return {"kind": kind, "label": words, "display": display, "low": float(low) if low is not None else None,
            "high": float(high) if high is not None else None, "inputs": inputs_view(basis.get("inputs"), labels),
            "reason": clean(basis.get("reason")) or None}


def _dated(label: str, node: dict | None, date_key: str, labels: dict[str, str]) -> dict | None:
    """A stored date fact: {label, date_iso, display, relative, status, inputs}."""
    node = node or {}
    iso = node.get(date_key)
    if not iso and node.get("status") != "unknown":
        return None
    return {"label": label, "date_iso": iso, "display": nice_date(iso) if iso else "Not confirmed",
            "relative": ago(iso), "status": node.get("status") or "unknown",
            "as_printed": node.get("date_as_printed"), "inputs": inputs_view(node.get("inputs"), labels)}


def event_detail(event: dict, running: set[str], failures: dict[str, str]) -> dict:
    """Facts strip for an event page."""
    summary = event_summary(event, running, failures)
    doc = event["out"]["people"] or {}
    labels = doc_labels(event)
    facts = []
    for label, node, key in (("Listing", doc.get("listing"), "listed_on"), ("Allotment", doc.get("allotment"), "allotted_on")):
        fact = _dated(label, node, key, labels)
        if fact:
            if label == "Listing" and node.get("status") == "scheduled":
                fact["label"] = "Listing (scheduled)" if (node.get("days_since") or 0) <= 0 else "Listing was due"
            facts.append(fact)
    for key, label in (("payment", "Buyback payment"), ("closing", "Buyback closes"), ("opening", "Buyback opens"),
                       ("record", "Record date")):
        node = (doc.get("buyback_dates") or {}).get(key)
        if node:
            facts.append(_dated(label, node, "date", labels))
    sale = doc.get("sale") or {}
    if sale:
        facts.append({"label": ("Trade date" if event["spec"].event_type in ("block_deal", "insider_sale")
                                else "Sale on the exchange"), "date_iso": sale.get("sale_date_parsed"),
                      "display": nice_date(sale.get("sale_date_parsed")) or "Not confirmed",
                      "relative": ago(sale.get("sale_date_parsed")), "status": "verified" if sale.get("sale_date_parsed") else "unknown",
                      "as_printed": sale.get("sale_date"), "inputs": []})
    cost = (event["out"].get("cost") or {}).get("totals") or {}
    timeline = event["out"].get("timeline") or {}
    from api import freshness

    return {**summary, "as_of": doc.get("as_of"), "price": price_view(event) if event["processed"] else None,
            "freshness": freshness.summary(documents_view(event)),
            "dates": [f for f in facts if f], "issue_type": spec_type_label(event["spec"]),
            "offer_size": clean(sale.get("total_shares_offered")) or None,
            "run": {"cost_usd": cost.get("cost_usd"), "fresh_cost_usd": cost.get("fresh_usd"),
                    "seconds": round(timeline.get("total_s") or cost.get("wall_s") or 0, 1) or None,
                    "run_at": _run_time(timeline.get("run_id") or (event["out"].get("cost") or {}).get("run_id"))}}


def _run_time(run_id: str | None) -> str | None:
    """'sedemac_ipo-20261115T095135Z' -> '2026-11-15T09:51:35Z'."""
    match = re.search(r"(\d{8})T(\d{6})Z", run_id or "")
    if not match:
        return None
    d, t = match.groups()
    return f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}Z"


# ---------- person card ----------

def timing_detail(key: str, node: dict, labels: dict[str, str]) -> dict:
    """One timing block with its rule citation and the dated inputs behind it."""
    rule_refs, inputs = [], []
    for source in node.get("sources") or []:
        if "field" in source:
            inputs.extend(inputs_view([source], labels))
        elif source.get("found") and source.get("url"):
            quote = (source.get("quotes") or [None])[0]
            ref = evidence_ref({"source_url": source["url"], "pdf_index": source.get("pdf_index"),
                                "printed_page": source.get("printed_page"), "quote": quote}, labels)
            if ref:
                rule_refs.append(ref)
    periods = [{"label": clean(p.get("label")), "ends_on": p.get("ends_on"), "display": clean(p.get("display")),
                "status": p.get("status"), "share_of_retained": p.get("share_of_retained")}
               for p in node.get("periods") or []]
    return {"key": key, "label": "When the cash arrives" if key == "proceeds" else "When the shares are free",
            "status": node.get("status") or "unknown",
            "display": clean(node.get("when") or node.get("display") or node.get("reason")) or "Not confirmed",
            "note": clean(node.get("note")) or None, "periods": periods, "rule_evidence": rule_refs, "inputs": inputs,
            "rule_found": node.get("rule_found")}


def person_card(event: dict, person_id: str, rm: dict | None, rm_lookup: dict | None = None) -> dict | None:
    """The full call card for one person."""
    lists = event_lists(event, rm_lookup)
    item = next((i for group in lists.values() for i in group if i["person"]["id"] == person_id), None)
    if item is None:
        return None
    person = people_by_id(event).get(person_id) or {}
    entry = next((e for g in ("callable", "entities", "context") for e in (event["out"]["ranked"] or {}).get(g) or []
                  if e["person_id"] == person_id), {})
    brief = briefs_by_id(event).get(person_id) or {}
    labels = doc_labels(event)
    group = "callable" if item in lists["callable"] else ("entities" if item in lists["entities"] else "context")
    amounts = [figure_view(key, figure, labels) for key, figure in (person.get("amounts") or {}).items()
               if figure.get("status") not in ("not_applicable",)]
    timing = [timing_detail(key, node, labels) for key, node in (person.get("timing") or {}).items()
              if node.get("status") != "not_applicable"]
    name_refs = [e for e in (evidence_ref(ref, labels) for ref in (person.get("evidence") or [])
                             if ref.get("field") == "name_as_printed" and ref.get("field_kept", True)) if e]
    swaps = age_swaps(event, entry, person)
    reasons = [with_fresh_ages(r, swaps) for r in rank_reason_words(entry.get("rank_reasons") or [])]
    return {**item, "list": group, "rm": {**rm_brief(rm), "updated_at": (rm or {}).get("updated_at")},
            "brief": {"lines": tidy_lines(fresh_brief_lines(brief, swaps), person), "written_by": "template" if brief.get("brief_source") == "template" else "assistant"},
            "why_now": clean(entry.get("why_money")) or item["why"],
            "tier_reason": _tier_reason(item),
            "amounts": amounts, "timing_detail": timing,
            "name_evidence": name_refs[:3],
            "rank_reasons": reasons, "names_as_printed": person.get("names_as_printed") or [],
            "holder_type_reason": clean(person.get("holder_type_reason")) or None,
            "context_reason": item.get("context_reason"),
            "event_facts": {"price": price_view(event), "money_date": {**money_date(event)}},
            "freshness": _card_freshness(amounts, timing, name_refs, labels)}


def _card_freshness(amounts: list[dict], timing: list[dict], name_refs: list[dict], labels: dict[str, str]) -> dict:
    """Fetched dates of every document this card's facts rest on (api/freshness.py)."""
    from api import freshness

    docs: list[dict] = []
    for ref in name_refs:
        docs.append({"doc_sha": ref["doc_sha"], "label": ref["doc_label"]})
    for node in [*amounts, *timing]:
        for ref in node.get("rule_evidence") or []:
            docs.append({"doc_sha": ref["doc_sha"], "label": ref["doc_label"]})
        for row in node.get("inputs") or []:
            for ref in row.get("evidence") or []:
                docs.append({"doc_sha": ref["doc_sha"], "label": ref["doc_label"]})
    return freshness.summary(docs)


_SCORE_LINE = re.compile(r"^(score|later score|other trigger|money counted as 0)\b", re.I)


def rank_reason_words(reasons: list[str]) -> list[str]:
    """Stored rank reasons an RM can read: score arithmetic dropped, id prefixes removed."""
    out = []
    for reason in reasons:
        text = str(reason or "").strip()
        if not text or _SCORE_LINE.match(text):
            continue
        text = re.sub(r"^family link \([^)]*\):\s*", "Family link: ", text, flags=re.I)
        text = re.sub(r"^(seller|entity):\s*", "", text, flags=re.I)
        out.append(clean(text))
    return out


def _tier_reason(item: dict) -> str:
    """Why this person is in their tier, in one line."""
    if item["tier"] == "cash_now":
        return "Sold shares in this event; the cash is paid or due within a month"
    if item["tier"] == "unlock":
        return "Lock-in ended recently, so the shares can now be sold"
    return "Holds shares; no cash from this event yet"


# ---------- today / summary ----------

# The same sale is often reported twice: as an insider disclosure and as an exchange offer for sale, or as a block
# deal and a bulk deal. Those are separate events in the store, so a person would be counted twice on Today, in the
# calendar and in every total. One sale is one row, with each place it was reported listed on it.
SALE_SOURCE_ORDER = ("insider_sale", "block_deal", "ofs_stock_exchange")
SAME_SALE_DAYS = 3
SAME_SALE_SHARE_GAP = 0.01


def _company_key(name: str) -> str:
    """Company name without 'Limited' / punctuation, so 'X Ltd' and 'X Limited' are one company."""
    words = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
    return " ".join(w for w in words if w not in ("limited", "ltd", "private", "pvt"))


def _holder_key(name: str | None) -> str:
    """A holder's name without case or punctuation, so 'Dinesh R. Agarwal' and 'DINESH R AGARWAL' match."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split())


def _trade_lines(person: dict) -> frozenset:
    """The exchange lines a sale is built from: {(trade date, shares)}. An insider disclosure can hold several (a
    market sale plus a block deal); a block deal holds one."""
    lines = set()
    for line in person.get("trades") or []:
        quantity = re.sub(r"\D", "", str(line.get("quantity") or ""))
        if line.get("trade_date") and quantity:
            lines.add((str(line["trade_date"])[:10], int(quantity)))
    return frozenset(lines)


def _sale_facts(event: dict, item: dict, people: dict[str, dict]) -> tuple | None:
    """(company, person, shares, date, trade lines) that identify one sale, or None when it is not a single dated
    sale."""
    if item["tier"] != "cash_now" or event["spec"].event_type not in SALE_SOURCE_ORDER:
        return None
    person = people.get(item["person"]["id"]) or {}
    shares = re.sub(r"\D", "", str(person.get("shares_offered") or ""))
    when = money_date(event).get("date_iso")
    name = _holder_key(person.get("name_clean") or item["person"]["name"])
    if not shares or not when or not name:
        return None
    return (_company_key(event["spec"].company), name, int(shares), date.fromisoformat(when), _trade_lines(person))


def _same_sale(cluster: list[tuple], facts: tuple) -> bool:
    """True when these facts describe the cluster's sale: the same holder and company, trade dates within a few days
    and share counts within 1%."""
    head = cluster[0][2]
    return head[:2] == facts[:2] and abs((head[3] - facts[3]).days) <= SAME_SALE_DAYS \
        and abs(head[2] - facts[2]) <= SAME_SALE_SHARE_GAP * max(head[2], facts[2])


def _absorb_contained(clusters: list[list[tuple]], rank: dict[str, int]) -> list[list[tuple]]:
    """Clusters with every sale whose exchange lines all sit inside a kept sale's lines folded into that sale (an
    insider disclosure of a market sale plus a block deal contains the block deal reported on its own).

    Sales with more lines are kept first, so a multi-day row absorbs every sale it contains; a sale is absorbed only
    when all its lines are inside one kept sale, never through a chain; partial overlaps stay separate rows."""
    order = sorted(clusters, key=lambda c: (-len(c[0][2][4]), rank.get(c[0][0]["spec"].event_type, 9),
                                            c[0][0]["spec"].event_id))
    kept: list[list[tuple]] = []
    for cluster in order:
        facts = cluster[0][2]
        host = next((k for k in kept if facts[4] and k[0][2][:2] == facts[:2] and facts[4] <= k[0][2][4]), None)
        if host is None:
            kept.append(list(cluster))
        else:
            host.extend(cluster)
    return kept


def _merge_duplicate_sales(per_event: list[tuple[dict, list[dict]]]) -> tuple[list[dict], set[str]]:
    """Callable items of every event with each repeated sale kept once.
    Two items are the same sale when company, person and trade date (within a few days) match and the share counts
    agree (within 1%: a notice says 'up to N', the exchange then prints the exact figure); the kept row is the
    actual trade (insider disclosure, then block/bulk, then the offer notice). Then a sale whose exchange lines
    (date, shares) all sit inside another kept sale's is folded into it (_absorb_contained). The kept row lists
    every source on `sources`. Returns (kept items, ids of the dropped items)."""
    rank = {t: i for i, t in enumerate(SALE_SOURCE_ORDER)}
    candidates, others = [], []
    for event, items in per_event:
        people = people_by_id(event)
        for item in items:
            facts = _sale_facts(event, item, people)
            (candidates if facts else others).append((event, item, facts))
    candidates.sort(key=lambda c: (rank.get(c[0]["spec"].event_type, 9), c[0]["spec"].event_id))
    clusters: list[list[tuple]] = []
    for cand in candidates:
        for cluster in clusters:
            if _same_sale(cluster, cand[2]):
                cluster.append(cand)
                break
        else:
            clusters.append([cand])
    kept, dropped = [item for _, item, _ in others], set()
    for cluster in _absorb_contained(clusters, rank):
        labels = []
        for event, item, _ in cluster:
            label = spec_type_label(event["spec"])
            if label not in labels:
                labels.append(label)
        head = cluster[0][1]
        head["sources"] = labels
        kept.append(head)
        dropped.update(item["id"] for _, item, _ in cluster[1:])
    for item in kept:
        item.setdefault("sources", [item["event"]["type_label"]])
    return kept, dropped


def _per_event_callable(events: list[dict], rm_lookup: dict) -> list[tuple[dict, list[dict]]]:
    return [(event, event_lists(event, rm_lookup)["callable"]) for event in events if event["processed"]]


def all_items(events: list[dict], rm_lookup: dict) -> list[dict]:
    """Every callable item across processed events, in call order, each repeated sale once."""
    kept, _ = _merge_duplicate_sales(_per_event_callable(events, rm_lookup))
    return sorted(kept, key=sort_key)


# One holder often sells at the same company in several weeks, and each week's insider disclosures and block deals
# are a separate event. Every trade keeps its own row on its event page, in the calendar and in the CSV export; on
# Today they are one call, led by the newest trade (its date, amount and call status are the row's), with every
# trade listed on the slot. Households are grouped first, and a family slot is never folded.

def repeat_trade_key(item: dict) -> tuple[str, str] | None:
    """(company, holder) for a cash sale that can repeat week to week; None for anything else."""
    if item["event"]["type"] not in SALE_SOURCE_ORDER or bucket(item) != "cash_now":
        return None
    holder = _holder_key(item["person"]["name"])
    return (_company_key(item["event"]["company"]), holder) if holder else None


def _trade_ref(item: dict) -> dict:
    """One trade on a folded slot: its call id, event, money date, amount and call status."""
    iso = (item.get("timing") or {}).get("date_iso")
    return {"id": item["id"], "event": item["event"], "date_iso": iso, "date_display": nice_date(iso),
            "amount": item["amount"], "sources": item.get("sources") or [item["event"]["type_label"]],
            "rm_status": (item.get("rm") or {}).get("status") or "to_call"}


def _newest(item: dict) -> tuple:
    """Sort key for the lead of a folded slot: the latest money date, then the higher score."""
    return ((item.get("timing") or {}).get("date_iso") or "", item.get("score") or 0, item["id"])


def _fold_key(item: dict) -> tuple[str, str] | None:
    """The repeat-trade key of a slot that may fold. A family slot (household members inside) is that week's family
    call and stays as it is, so its members and 'together' figure are exactly the family's; the holder's own sales
    in other weeks still fold with each other."""
    return None if item.get("members") else repeat_trade_key(item)


def fold_repeat_trades(items: list[dict]) -> list[dict]:
    """Items in call order with each holder's repeat sales at one company folded into the newest one, which keeps
    its own place in the order, amount, timing and call status (a new sale is a new reason to call).

    The slot lists every trade (newest first) on `trades`, adds their known cash on `trades_total_cr` /
    `trades_total_display` and counts trades with no amount on `trades_unpriced`. A holder with one trade is
    unchanged, and folding an already folded list changes nothing."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        key = _fold_key(item)
        if key:
            groups.setdefault(key, []).append(item)
    leads = {key: max(group, key=_newest)["id"] for key, group in groups.items() if len(group) > 1}
    out = []
    for item in items:
        key = _fold_key(item)
        if key not in leads:
            out.append(item)
            continue
        if item["id"] != leads[key]:
            continue
        refs: dict[str, dict] = {}
        for member in groups[key]:
            for ref in member.get("trades") or [_trade_ref(member)]:
                refs.setdefault(ref["id"], ref)
        trades = sorted(refs.values(), key=lambda t: (t["date_iso"] or "", t["id"]), reverse=True)
        known = [Decimal(str(t["amount"]["value_cr"])) for t in trades
                 if t["amount"]["value_cr"] is not None and t["amount"]["kind"] == "cash"]
        total = sum(known, Decimal(0)) if known else None
        out.append({**item, "trades": trades, "trades_total_cr": crore(total),
                    "trades_total_display": _total_text(total), "trades_unpriced": len(trades) - len(known)})
    return out


def _total_text(total: Decimal | None) -> str | None:
    """'₹6.98 Cr'; under ₹10 lakh in rupees ('₹12,96,000'), never '₹0.00 Cr' (as money_text)."""
    if total is None:
        return None
    return f"₹{indian(total * 10_000_000, 0)}" if total < Decimal("0.1") else cr_text(round(total, 2))


def household_slots(items: list[dict]) -> list[dict]:
    """Items in call order with each household folded into one slot: the first member leads, the others inside."""
    queue, seen = [], set()
    for item in items:
        hid = item["household_id"]
        if hid and hid in seen:
            continue
        if hid:
            seen.add(hid)
        slot = dict(item)
        members = (item.get("household") or {}).get("members") or []
        slot["members"] = [m for m in members if m["id"] != item["id"]]
        total = sum((Decimal(str(m["amount"]["value_cr"])) for m in members if m["amount"]["value_cr"] is not None
                     and m["amount"]["kind"] == item["amount"]["kind"]), Decimal(0))
        slot["household_total_cr"] = crore(total) if members else None
        queue.append(slot)
    return queue


def today_queue(events: list[dict], rm_lookup: dict, limit: int | None = None, fold_trades: bool = True) -> list[dict]:
    """The cross-event queue: each household folded into one slot, then one holder's repeat sales at a company
    folded into one slot (unless fold_trades is False, for callers that place each trade by its own date first)."""
    slots = household_slots(all_items(events, rm_lookup))
    queue = fold_repeat_trades(slots) if fold_trades else slots
    return queue[:limit] if limit else queue


def summary(events: list[dict], rm_lookup: dict) -> dict:
    """KPIs for the Today header."""
    items = all_items(events, rm_lookup)
    from api import brief  # one definition of "new this week" for the KPI, the home line and the daily brief

    new_events = brief.since_figures(events, [], None)["new_events"]
    queue = today_queue(events, rm_lookup)
    people = fold_repeat_trades(items)  # a holder who sold in three weeks is one person; their cash counts in full
    open_items = [i for i in queue if i["rm"]["status"] in ("to_call", "follow_up")]
    return {"as_of": as_of().isoformat(), "as_of_display": nice_date(as_of().isoformat()),
            "people_to_call": len(open_items), "people_total": len(people), "households": len(queue),
            "cash_now_cr": crore(cash_total(items)),
            "cash_now_people": sum(1 for i in people if bucket(i) == "cash_now"),
            "unlock_people": sum(1 for i in people if i["tier"] == "unlock"),
            "new_events_this_week": new_events,
            "events_processed": sum(1 for e in events if e["processed"]),
            "events_total": len(events),
            "called": sum(1 for i in queue if i["rm"]["status"] == "called")}


# ---------- calendar ----------

CAL_KINDS = {"listing": "Listing day: sellers paid", "unlock": "Lock-in ends", "buyback_payment": "Buyback payment",
             "buyback_closing": "Buyback closes", "ofs_sale": "Exchange sale settles"}


def calendar(events: list[dict], rm_lookup: dict, start: str | None, end: str | None) -> list[dict]:
    """Dated money items: listings, unlock ends, buyback payments, exchange-sale settlements."""
    groups: dict[tuple, dict] = {}

    def add(event: dict, iso: str, kind: str, confirmed: bool, item: dict, value: float | None, value_kind: str) -> None:
        key = (iso, kind, event["spec"].event_id)
        row = groups.setdefault(key, {"date_iso": iso, "display": nice_date(iso), "relative": ago(iso), "kind": kind,
                                      "label": CAL_KINDS.get(kind, kind), "event": event_ref(event),
                                      "confirmed": confirmed, "past": iso <= as_of().isoformat(), "people": [],
                                      "listing_only": False})
        row["people"].append({"id": item["id"], "person_id": item["person"]["id"], "name": item["person"]["name"],
                              "tier": item["tier"], "value_cr": value, "value_kind": value_kind,
                              "estimate": value_kind == "shares" or bool(item["amount"].get("estimate"))})

    per_event = _per_event_callable(events, rm_lookup)
    _, repeated = _merge_duplicate_sales(per_event)
    for event, callable_items in per_event:
        when = money_date(event)
        people = people_by_id(event)
        for item in callable_items:
            if item["id"] in repeated:
                continue
            person = people.get(item["person"]["id"]) or {}
            proceeds = (person.get("amounts") or {}).get("proceeds") or {}
            paid = (person.get("timing") or {}).get("proceeds") or {}
            iso = cash_date(paid, when)
            # A block/insider sale is placed on its settlement day; one with none (off-market) has no money date.
            if when["kind"] == "ofs_sale" and event["spec"].event_type in ("block_deal", "insider_sale") \
                    and not paid.get("settles_on"):
                iso = None
            if iso and proceeds.get("status") in ("computed", "unknown") and item["tier"] == "cash_now":
                value = value_cr(proceeds) if proceeds.get("status") == "computed" else None
                add(event, iso, when["kind"], when["confirmed"], item, value, "cash")
            retained = (person.get("amounts") or {}).get("retained") or {}
            for period in ((person.get("timing") or {}).get("retained") or {}).get("periods") or []:
                if period.get("ends_on"):
                    whole = period.get("share_of_retained") == "all" and retained.get("status") == "computed"
                    add(event, period["ends_on"], "unlock", True, item,
                        crore(dec(retained.get("crore_high"))) if whole else None, "shares")
    for event in events:
        # An upcoming (or past) listing date is listed even when no one has a known cash amount.
        when = money_date(event) if event["processed"] else {}
        if when.get("kind") == "listing" and when.get("date_iso") and \
                (when["date_iso"], "listing", event["spec"].event_id) not in groups:
            iso = when["date_iso"]
            groups[(iso, "listing", event["spec"].event_id)] = {
                "date_iso": iso, "display": nice_date(iso), "relative": ago(iso), "kind": "listing",
                "label": "Listing day", "event": event_ref(event), "confirmed": when["confirmed"],
                "past": iso <= as_of().isoformat(), "people": [], "listing_only": True}
    rows = []
    for row in groups.values():
        if (start and row["date_iso"] < start) or (end and row["date_iso"] > end):
            continue
        known = [Decimal(str(p["value_cr"])) for p in row["people"] if p["value_cr"] is not None]
        row["total_cr"] = float(round(sum(known, Decimal(0)), 6)) if known else None
        if row["kind"] == "listing" and not known:
            row["label"] = "Listing day"
        row["people_count"] = len(row["people"])
        row["unknown_count"] = len(row["people"]) - len(known)
        row["people"].sort(key=lambda p: -(p["value_cr"] or 0))
        rows.append(row)
    return sorted(rows, key=lambda r: (r["date_iso"], r["event"]["company"]))


# ---------- network ----------

def _cr_float(value: object) -> float:
    """A stored ₹-crore value as a float for comparison; -1 when it is unknown."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1.0


COMPANY_SUFFIXES = {"limited", "ltd", "l", "pvt", "private", "the", "co", "inc"}


def company_tokens(name: str) -> list[str]:
    """A company name as comparable words: lower case, punctuation gone, legal suffixes dropped."""
    tokens = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()
    while tokens and tokens[-1] in COMPANY_SUFFIXES:
        tokens.pop()
    return [t for t in tokens if t != "the"]


def same_company(a: list[str], b: list[str]) -> bool:
    """True when two spellings name one company: same first word and the same number of words, each word
    a prefix of the other ('tech' / 'technologies', 'infrastructure' / 'infrastructures'). Needs two words,
    so 'Tata' never swallows 'Tata Motors'."""
    if len(a) != len(b) or len(a) < 2 or a[0] != b[0]:
        return False
    return all(x.startswith(y) or y.startswith(x) for x, y in zip(a, b))


def network(events: list[dict], rm_lookup: dict) -> dict:
    """The relationship network: holders that connect MORE THAN ONE money event, and family groups.
    Each holder is a single node (a name is merged across events; a company/fund always wins as an
    entity, so it is never drawn as both a person and a company). A holder is linked by a 'holds' edge
    to each event it appears in; 'household' edges link family members. Holders tied to only one event
    and no family are left out, so the graph shows the connections rather than every call-list row."""
    event_nodes: dict[str, dict] = {}
    holders: dict[str, dict] = {}
    all_edges: list[dict] = []
    seen_edge: set = set()
    pid_to_node: dict[str, str] = {}  # keyed by the composite item id ("<event>/<person>"), as households reference it
    household_nodes: set = set()

    names = sorted({e["spec"].company for e in events if e["processed"]},
                   key=lambda n: (-len(n or ""), (n or "").isupper()))  # fullest spelling, mixed case first
    canon: dict[str, list[str]] = {}  # node id -> tokens of the fullest spelling seen
    node_for: dict[str, str] = {}
    labels: dict[str, str] = {}
    for name in names:  # longest spelling first, so a truncated exchange name folds into the full one
        tokens = company_tokens(name)
        match = next((nid for nid, full in canon.items() if same_company(tokens, full)), None)
        if match is None:
            match = "e:" + ("".join(tokens) or "event")
            canon[match] = tokens
            labels[match] = name
        node_for[name] = match

    def company_node_id(name: str) -> str:
        """One event node per company: weekly block/insider deals and an IPO of the same firm merge into it,
        including 'Ltd.' vs 'Limited' and the exchange's truncated spelling ('Medical Tech L')."""
        return node_for.get(name) or "e:" + ("".join(company_tokens(name)) or "event")

    for event in events:
        if not event["processed"]:
            continue
        eid = event["spec"].event_id
        ek = company_node_id(event["spec"].company)
        company = labels.get(ek, event["spec"].company)  # one spelling per company for holders' "also in"
        lists = event_lists(event, rm_lookup)
        enode = event_nodes.get(ek)
        if enode is None:
            enode = event_nodes[ek] = {"id": ek, "type": "event", "label": company, "event": event_ref(event),
                                       "people_count": 0, "event_count": 0, "event_types": set(), "events": [],
                                       "callers": set()}
        enode["event_count"] += 1
        enode["event_types"].add(spec_type_label(event["spec"]))
        # Each money event behind this company dot, with how many individuals it gives someone to call,
        # so the dot opens the event that actually has calls (not merely the first one read).
        enode["events"].append({"event": event_ref(event), "date_iso": money_date(event)["date_iso"],
                                "to_call": len(lists["callable"])})
        people = people_by_id(event)
        for group, items in lists.items():
            for item in items:
                # A fund or company is an entity whichever list it sits on (buyers in a block deal are "context").
                is_entity = group == "entities" or item["person"].get("holder_type") == "entity"
                pid = item["person"]["id"]
                clean = (people.get(pid) or {}).get("name_clean") or (item["person"]["name"] or "").lower()
                node_id = f"p:{clean}"  # one node per holder; a same-named person and fund merge, entity wins
                pid_to_node[item["id"]] = node_id
                value = item["amount"]["value_cr"]
                node = holders.get(node_id)
                if node is None:
                    holders[node_id] = {"id": node_id, "type": "entity" if is_entity else "person",
                        "label": item["person"]["name"], "role": item["person"]["role"], "tier": item["tier"],
                        "list": group, "value_cr": value, "estimate": bool(item["amount"].get("estimate")),
                        "event_id": eid, "person_id": pid, "company": company, "companies": {company}, "eids": {eid}}
                else:
                    if is_entity:
                        node["type"] = "entity"  # a company/fund classification anywhere wins
                    node["companies"].add(company)
                    node["eids"].add(eid)
                    if _cr_float(value) > _cr_float(node["value_cr"]):  # keep the biggest call as the primary
                        node.update(value_cr=value, estimate=bool(item["amount"].get("estimate")),
                                    event_id=eid, person_id=pid, role=item["person"]["role"], tier=item["tier"],
                                    company=company)
                if group == "callable":
                    enode["callers"].add(node_id)
                key = (node_id, ek, "holds")
                if key not in seen_edge:
                    seen_edge.add(key)
                    all_edges.append({"source": node_id, "target": ek, "kind": "holds",
                                      "reason": f"{item['person']['role'] or 'Holder'} in {company}"})
        for item in lists["callable"]:
            house = item.get("household")
            if not house:
                continue
            ids = list(dict.fromkeys(n for n in (pid_to_node.get(m["id"]) for m in house["members"]) if n))
            if len(ids) < 2:  # a "family of one" (other members not on any list) is not a family link
                continue
            household_nodes.update(ids)
            for a, b in zip(ids, ids[1:]):
                key = tuple(sorted((a, b))) + ("household",)
                if a != b and key not in seen_edge:
                    seen_edge.add(key)
                    all_edges.append({"source": a, "target": b, "kind": "household", "reason": house["reason"]})
    for node in holders.values():
        node["event_count"] = len(node["companies"])
        node["also_in"] = sorted(c for c in node["companies"] if c != node["company"])
        node["money_events"] = len(node["eids"])  # e.g. one insider selling in several weekly disclosures
        del node["companies"], node["eids"]
    # Keep the connected story: holders at more than one company, repeat sellers, or family members.
    keep = {nid for nid, n in holders.items()
            if n["event_count"] > 1 or n["money_events"] > 1 or nid in household_nodes}
    node_ids = set(keep)
    kept_events = {e["target"] for e in all_edges if e["kind"] == "holds" and e["source"] in keep}
    node_ids |= kept_events
    edges = [e for e in all_edges if e["source"] in node_ids and e["target"] in node_ids]
    for ek in kept_events:  # a company node's size = how many kept holders connect to it
        linked = {e["source"] for e in edges if e["target"] == ek and e["kind"] == "holds"}
        event_nodes[ek]["people_count"] = len(linked)
        event_nodes[ek]["linked_people"] = sum(1 for nid in linked if holders[nid]["type"] == "person")
        event_nodes[ek]["linked_entities"] = len(linked) - event_nodes[ek]["linked_people"]
    for enode in event_nodes.values():
        enode["event_types"] = sorted(enode["event_types"])
        # Individuals to call across all of this company's events, a name counted once (the call list holds no funds).
        enode["to_call"] = len(enode.pop("callers"))
        enode["events"].sort(key=lambda r: r["date_iso"] or "", reverse=True)  # newest first...
        enode["events"].sort(key=lambda r: r["to_call"], reverse=True)  # ...then most people to call (stable)
        enode["event"] = enode["events"][0]["event"]  # open the event with the most people to call, newest first
    for nid in keep:  # which kinds of money event each holder is tied to (for the event-type filter)
        holders[nid]["event_types"] = sorted({t for e in edges if e["source"] == nid and e["kind"] == "holds"
                                              for t in event_nodes[e["target"]]["event_types"]})
        holders[nid]["in_household"] = nid in household_nodes
    nodes = [event_nodes[ek] for ek in event_nodes if ek in kept_events]
    nodes += [holders[nid] for nid in keep]
    return {"nodes": nodes, "edges": edges,
            "legend": {"event": "Money event", "person": "Person to call", "entity": "Company or fund",
                       "holds": "Holds shares in", "household": "Same household"}}


# ---------- feed ----------

NEXT_ACTIONS = {"ready": "Open call list", "empty": "Open event", "failed": "See why", "waiting": "Process now",
                "unsupported": "Not supported yet", "scanned": "Needs a readable copy"}


def feed(events: list[dict]) -> dict:
    """Discovered filings grouped Today / Upcoming / Recent, each with status and next action."""
    from ui.dashboard_data import feed_header, feed_rows

    from api.discovery_routes import owner_of
    from config.signals import WATCH_CLASSES, WATCH_REASONS

    found = store.discovery()
    log = store.discovery_log()
    last_entry = {entry.get("event_id"): entry for entry in log}
    groups = feed_rows(found, events, log, as_of())
    header = feed_header(found, events)
    by_id = {e["spec"].event_id: e for e in events}
    out = {}
    for name, rows in groups.items():
        out[name] = []
        for row in rows:
            item, event = row["item"], by_id.get(row["event_id"])
            status, reason = row["status"], clean(row["reason"])
            if event and not event["processed"] and any(d["scanned"] for d in documents_view(event)):
                status, reason = "scanned", "Scanned filing: text not readable yet"
            elif event and event["processed"] and status in ("ready", "empty"):
                count = len(event_lists(event)["callable"])
                status = "ready" if count else "empty"
                reason = f"{count} to call" if count else "No one to call; open the event to see why"
            if item.get("class") in WATCH_CLASSES:
                status = "watch"
                reason = WATCH_REASONS.get(item["class"], "Listed, not processed yet")
            elif status == "waiting" and (last_entry.get(row["event_id"]) or {}).get("status") == "needs_approval":
                status, reason = "needs_approval", clean(last_entry[row["event_id"]].get("reason"))
            when = row["event_date"] or {}
            out[name].append({"source_badge": item.get("exchange") or owner_of(item.get("source") or ""),
                              "signal": item.get("class"),"id": item.get("id"), "title": clean(item.get("title")), "company": item.get("company"),
                              "source": item.get("source_name"), "published_iso": item.get("published_iso"),
                              "published_display": nice_date(item.get("published_iso")), "link": item.get("link"),
                              "kind_label": clean(item.get("label")), "event_type": item.get("event_type"),
                              "event_id": row["event_id"] if event else None, "status": status,
                              "status_label": {"scanned": "Scanned filing", "watch": "Watch",
                                               "needs_approval": "Needs approval"}.get(status, row["status_label"]),
                              "reason": reason, "next_action": NEXT_ACTIONS.get(status, "Open"),
                              "processable": row["processable"], "money_date": when.get("date"),
                              "money_date_display": nice_date(when.get("date"))})
    return {"refreshed_at": header["refreshed_at"], "sources_ok": [s.get("name") or s.get("id") for s in header["ok"]],
            "sources_with_problems": [s.get("name") or s.get("id") for s in header["problems"]],
            "items_total": header["items"], "groups": out}


# ---------- ops ----------

def ops(events: list[dict]) -> dict:
    """Per event: cost, run time, step timings, verification counts and rejections."""
    rows = []
    for event in events:
        if not event["processed"]:
            continue
        cost = (event["out"].get("cost") or {}).get("totals") or {}
        timeline = event["out"].get("timeline") or {}
        extract = event["out"].get("extract") or {}
        sections, totals = [], {"proposed": 0, "kept": 0, "rejected": 0}
        for section, counts in (extract.get("counts") or {}).items():
            if isinstance(counts, dict) and "proposed" in counts and counts.get("proposed"):
                sections.append({"section": SECTION_LABELS.get(section, clean(section.replace("_", " "))),
                                 "proposed": counts["proposed"], "kept": counts.get("kept", 0),
                                 "rejected": counts.get("rejected", 0)})
                for key in totals:
                    totals[key] += counts.get(key, 0) or 0
        rejections = [{"who": r.get("row"), "what": FIELD_LABELS.get(r.get("field"), clean(str(r.get("field", "")).replace("_", " "))),
                       "value": r.get("value"), "reason": REJECTION_WORDS.get(r.get("reason"), clean(r.get("reason"))),
                       "section": SECTION_LABELS.get(r.get("section"), clean(str(r.get("section", "")).replace("_", " ")))}
                      for r in extract.get("rejections") or []]
        rows.append({"event": event_ref(event), "cost_usd": cost.get("cost_usd"), "fresh_cost_usd": cost.get("fresh_usd"),
                     "per_person_usd": cost.get("cost_per_callable_usd"),
                     "fresh_per_person_usd": cost.get("fresh_per_callable_usd"),
                     "model_calls": cost.get("calls"), "cached_share": cost.get("cached_share"),
                     "people": cost.get("callable_people"),
                     "run_seconds": round(timeline.get("total_s") or cost.get("wall_s") or 0, 1),
                     "run_at": _run_time(timeline.get("run_id")),
                     "steps": [{"step": s["step"], "label": STEP_LABELS.get(s["step"], clean(s["step"])),
                                "seconds": round(s.get("seconds") or 0, 2), "calls": s.get("calls"),
                                "cached": s.get("cached"), "cost_usd": s.get("cost_usd")}
                               for s in timeline.get("steps") or []],
                     "verification": {"sections": sections, **totals}, "rejections": rejections})
    fresh = [r["fresh_cost_usd"] for r in rows if r["fresh_cost_usd"] is not None]
    recent = []
    for run in store.runs()[-15:][::-1]:
        recent.append({"event_id": run.get("event_id"), "started_at": run.get("started_at"),
                       "seconds": float(run.get("wall_s") or 0), "cost_usd": float(run.get("total_cost_usd") or 0),
                       "status": run.get("status"), "error": clean(run.get("error")) or None})
    return {"target_usd": 2.0, "events": rows,
            "totals": {"events": len(rows), "fresh_cost_usd": round(sum(fresh), 6),
                       "max_fresh_cost_usd": max(fresh) if fresh else None,
                       "avg_fresh_cost_usd": round(sum(fresh) / len(fresh), 6) if fresh else None,
                       "proposed": sum(r["verification"]["proposed"] for r in rows),
                       "kept": sum(r["verification"]["kept"] for r in rows),
                       "rejected": sum(r["verification"]["rejected"] for r in rows)},
            "recent_runs": recent}


# ---------- export ----------

CSV_COLUMNS = ("call_id", "event_id", "company", "event_type", "person_id", "name", "role", "tier", "amount_cr",
               "amount_kind", "amount_is_estimate", "amount_text", "money_date", "timing", "confidence", "why",
               "rm_status", "follow_up_date", "note")


def export_rows(events: list[dict], rm_lookup: dict) -> list[list]:
    """CRM rows: stable ids, numeric ₹ crore, ISO dates."""
    rows = []
    for item in all_items(events, rm_lookup):
        amount = item["amount"]
        rows.append([item["id"], item["event"]["id"], item["event"]["company"], item["event"]["type"], item["person"]["id"],
                     item["person"]["name"], item["person"]["role"] or "", item["tier"],
                     "" if amount["value_cr"] is None else f"{amount['value_cr']:.2f}", amount["kind"],
                     "yes" if amount["estimate"] else "no", amount["detail"] or amount["display"],
                     item["timing"]["date_iso"] or "", item["timing"]["label"], item["confidence"]["level"], item["why"],
                     item["rm"]["status"], item["rm"]["follow_up"] or "", item["rm"]["note"]])
    return rows
