"""IPO rules: offer-for-sale proceeds, gain, retained value, listing and lock-in timing.

config/event_types.py points event_type "ipo" here. people.py and rank.py call the
interface functions: context, summary, apply, why_money, amount_display, timing_display.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from agents.dates import add_months, age_text, fmt_date, parse_printed_date
from agents.figures import (computed_figure, crore, crore_range, fmt, input_ref, kept_evidence, printed_half_step,
                            rupees_from_printed,
                            rupees_range, shown, unknown, up_to)
from agents.identity import identity_tokens
from agents.verify import printed_number
from agents.rule_sources import rule_variants
from config.lock_in import LOCK_IN_RULES, NOT_FOUND, OFS_PROCEEDS_RULE

# Computed proceeds and the document's own printed amount agree when this close (in %).
PRINTED_MATCH_PCT = Decimal("0.1")
EMPLOYEE_DISCOUNT_CAVEAT = (
    "Offer price shown; employee-portion shares sold at a discount, so actual proceeds are slightly lower."
)
SELLER_SECTION = "selling_shareholders"
# The number as printed, digit grouping kept ("12,50,000" stays Indian-grouped).
_SHARE_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?")
_TIMETABLE_DATE = re.compile(r"scheduled for (.+?) per the offer")
_UNVERIFIED_SELLER = "named as a selling shareholder, but no seller-table row for this name passed verification"


def context(extracted: dict, as_of: date) -> dict:
    """Offer-level facts every person's figures use: price, listing, allotment, failed sellers."""
    offer = extracted.get("offer_facts") or {}
    return {
        "price": price_basis(offer),
        "listing": listing_basis(offer, as_of),
        "allotment": allotment_basis(offer),
        "as_of": as_of,
        "failed_sellers": _failed_seller_keys(extracted.get("unattributed") or []),
        "rule_sources": extracted.get("rule_sources") or {},
    }


def summary(context: dict) -> dict:
    """Top-level people.json keys for this event type."""
    return {
        "price_basis": _price_summary(context["price"]),
        "listing": context["listing"],
        "allotment": context["allotment"],
    }


def apply(person: dict, members: list[dict], context: dict) -> None:
    """Set seller_status, amounts and timing on one person."""
    person["seller_status"] = _seller_status(person, members, context["failed_sellers"])
    if person["seller_status"] == "unverified":
        person["flags"].append(_UNVERIFIED_SELLER)
    person["amounts"] = amounts(person, context["price"])
    person["timing"] = timing(person, context["listing"], context["allotment"], context["as_of"], context["rule_sources"])


def price_basis(offer: dict) -> dict:
    """The verified offer price, else the verified price band, else unknown.

    Each price must be a single printed number. A band needs both ends.
    """
    offer_price = printed_number(offer.get("offer_price"))
    if offer_price is not None:
        return {"kind": "offer_price", "low": offer_price, "high": offer_price,
                "inputs": [input_ref("offer_price", offer)], "caveats": _price_caveats(offer)}
    low = printed_number(offer.get("price_band_low"))
    high = printed_number(offer.get("price_band_high"))
    if low is not None and high is not None and low <= high:
        return {"kind": "price_band", "low": low, "high": high,
                "inputs": [input_ref("price_band_low", offer), input_ref("price_band_high", offer)]}
    return {"kind": "unknown", "reason": "no verified offer price or price band"}


def _price_caveats(offer: dict) -> list[dict]:
    """A caveat for every proceeds figure when verified page text names an employee discount."""
    notes = [note for note in offer.get("notes") or [] if note.get("kind") == "employee_discount"]
    if not notes:
        return []
    note = notes[0]
    url = note.get("source_url")
    source = {**note, "link": f"{url}#page={note.get('pdf_index')}" if url else None}
    return [{"text": EMPLOYEE_DISCOUNT_CAVEAT, "source": source}]


def listing_basis(offer: dict, as_of: date | None = None) -> dict:
    """The verified listing date as printed, and whether it is before as_of.

    listed_on is the parsed date, or None when the printed form is not one that
    agents.dates reads. An unparsed date is never treated as past.
    """
    value = offer.get("listing_date")
    if value is None or not str(value).strip():
        return _scheduled_listing(offer, as_of)
    listed_on = parse_printed_date(str(value))
    past = listed_on is not None and as_of is not None and listed_on < as_of
    basis = {
        "status": "verified",
        "date_as_printed": str(value),
        "listed_on": listed_on.isoformat() if listed_on else None,
        "past": past,
        "inputs": [input_ref("listing_date", offer)],
    }
    if past:
        basis["days_since"] = (as_of - listed_on).days
        basis["age"] = age_text(listed_on, as_of)
    return basis


def _scheduled_listing(offer: dict, as_of: date | None) -> dict:
    """The offer document's timetable date, used only when no announcement gives the listing date."""
    value = offer.get("listing_date_scheduled")
    if value is None or not str(value).strip():
        return {"status": "unknown", "reason": "listing date not verified"}
    listed_on = parse_printed_date(str(value))
    basis = {
        "status": "scheduled",
        "date_as_printed": str(value),
        "listed_on": listed_on.isoformat() if listed_on else None,
        "inputs": [input_ref("listing_date_scheduled", offer)],
    }
    if listed_on is not None and as_of is not None and listed_on <= as_of:
        basis["days_since"] = (as_of - listed_on).days
        basis["age"] = age_text(listed_on, as_of)
    return basis


def allotment_basis(offer: dict) -> dict:
    """The verified allotment date, printed and parsed. Lock-in periods run from it."""
    value = offer.get("allotment_date")
    if value is None or not str(value).strip():
        return {"status": "unknown", "reason": "allotment date not verified"}
    allotted_on = parse_printed_date(str(value))
    inputs = [input_ref("allotment_date", offer)]
    if allotted_on is None:
        reason = f"allotment date '{value}' is not in a date form the code reads"
        return {"status": "unknown", "reason": reason, "inputs": inputs}
    return {"status": "verified", "date_as_printed": str(value), "allotted_on": allotted_on.isoformat(), "inputs": inputs}


def amounts(person: dict, price: dict) -> dict:
    """Proceeds, gain and retained value for one person. Each says how it was worked out."""
    return {
        "proceeds": proceeds(person, price),
        "gain": gain(person, price),
        "retained": retained(person, price),
    }


def proceeds(person: dict, price: dict) -> dict:
    """shares_offered × price. "Up to" shares make the figure a maximum."""
    blocked = _not_a_verified_seller(person)
    if blocked is not None:
        return blocked
    shares = printed_number(person.get("shares_offered"))
    if shares is None:
        return unknown("shares offered not verified")
    if price["kind"] == "unknown":
        return unknown(price["reason"])
    low, high = shares * price["low"], shares * price["high"]
    working = f"{shown(person.get('shares_offered'), shares)} × {rupees_range(price)} = {crore_range(low, high)}"
    display = crore_range(low, high)
    if up_to(person):
        display = f"up to {display}, if all offered shares are sold"
    figure = computed_figure(low, high, display, working, price, [input_ref("shares_offered", person)])
    figure = {**figure, "caveats": list(price.get("caveats") or [])}
    check = printed_check(person, low, high, figure)
    if check:
        figure["printed_check"] = check
        figure["inputs"] = figure["inputs"] + [input_ref("amount_as_printed", person)]
        if check["status"] == "differs":
            source = (input_ref("amount_as_printed", person)["evidence"] or [{}])[0]
            figure["caveats"].append({"text": check["text"], "source": source, "kind": "printed_amount"})
    return figure


def printed_check(person: dict, low: Decimal, high: Decimal, figure: dict) -> dict | None:
    """Compare computed proceeds with the amount the document prints for the same shares.

    Only at one price (low == high). Within PRINTED_MATCH_PCT, or within the rounding of
    the printed figure (printed_half_step), it matches; otherwise the
    text gives both figures and the difference. None when no printed amount was verified.
    """
    printed_text = person.get("amount_as_printed")
    if not printed_text:
        return None
    printed = rupees_from_printed(printed_text)
    page = _page_label(person, "amount_as_printed")
    if printed is None or printed == 0:
        return {"status": "not_compared", "page": page,
                "text": f"the document prints \"{printed_text}\" ({page}); not compared: not one amount with a unit"}
    if low != high:
        return {"status": "not_compared", "page": page,
                "text": f"the document prints {printed_text} ({page}); not compared: the price is a band"}
    difference = ((low - printed) / printed * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    rounding = printed_half_step(printed_text) or Decimal(0)
    if abs(difference) <= PRINTED_MATCH_PCT or abs(low - printed) <= rounding:
        return {"status": "matches", "page": page, "text": f"matches the document's printed amount ({page})"}
    return {"status": "differs", "page": page, "difference_pct": f"{difference:+.2f}",
            "text": (f"The document prints {printed_text} for these shares ({page}), ₹{fmt(crore(printed))} crore; "
                     f"shares × price ({_page_label(person, 'shares_offered')}) gives {crore_range(low, high)}, "
                     f"{difference:+.2f}% different. Both pages are linked below.")}


def _page_label(record: dict, field: str) -> str:
    """"p. 16" or "pdf 20" for the first verified page of a field; "page unknown" without one."""
    evidence = input_ref(field, record)["evidence"]
    if not evidence:
        return "page unknown"
    first = evidence[0]
    printed = first.get("printed_page")
    return f"p. {printed}" if printed not in (None, "") else f"pdf {first.get('pdf_index')}"


def gain(person: dict, price: dict) -> dict:
    """shares_offered × (price − average cost). Only when the average cost is verified."""
    blocked = _not_a_verified_seller(person)
    if blocked is not None:
        return blocked
    shares = printed_number(person.get("shares_offered"))
    cost = printed_number(person.get("waca_per_share"))
    if shares is None:
        return unknown("shares offered not verified")
    if cost is None:
        return unknown("average cost of acquisition not verified")
    if price["kind"] == "unknown":
        return unknown(price["reason"])
    low, high = shares * (price["low"] - cost), shares * (price["high"] - cost)
    working = f"{shown(person.get('shares_offered'), shares)} × ({rupees_range(price)} − ₹{fmt(cost)}) = {crore_range(low, high)}"
    display = crore_range(low, high) + ", before offer expenses and taxes"
    if up_to(person):
        display = f"up to {display}, if all offered shares are sold"
    inputs = [input_ref("shares_offered", person), input_ref("waca_per_share", person)]
    return computed_figure(low, high, display, working, price, inputs)


def retained(person: dict, price: dict) -> dict:
    """shares_held_pre_offer − shares_offered, valued at the price. Always an estimate."""
    held = printed_number(person.get("shares_held_pre_offer"))
    if held is None:
        return unknown("pre-offer holding not verified")
    if seller_status(person) == "unverified":
        return unknown(_UNVERIFIED_SELLER)
    offered = printed_number(person.get("shares_offered"))
    if _is_seller(person) and offered is None:
        return unknown("in the seller table but shares offered not verified")
    offered = offered or Decimal(0)
    left = held - offered
    if left < 0:
        return unknown("shares offered exceed the pre-offer holding; check both tables")
    inputs = [input_ref("shares_held_pre_offer", person)] + ([input_ref("shares_offered", person)] if offered else [])
    if left == 0:
        working = f"{shown(person.get('shares_held_pre_offer'), held)} − {shown(person.get('shares_offered'), offered)} = 0 shares"
        return {"status": "none", "shares": "0", "display": "none retained", "shares_display": "none retained",
                "working": working, "inputs": inputs}
    shares_text = f"{fmt(left)} shares"
    if up_to(person):
        shares_text = f"at least {shares_text}, if all offered shares are sold"
    if price["kind"] == "unknown":
        return {"status": "shares_only", "shares": str(left), "shares_display": shares_text,
                "reason": price["reason"], "inputs": inputs}
    low, high = left * price["low"], left * price["high"]
    held_text = shown(person.get("shares_held_pre_offer"), held)
    count = f"({held_text} − {shown(person.get('shares_offered'), offered)})" if offered else held_text
    working = f"{count} × {rupees_range(price)} = {crore_range(low, high)}"
    label = "estimate, valued at offer price" if price["kind"] == "offer_price" else "estimate, valued at the price band"
    figure = computed_figure(low, high, f"{crore_range(low, high)} ({label})", working, price, inputs)
    return {**figure, "shares": str(left), "shares_display": shares_text, "label": label}


def timing(
    person: dict,
    listing: dict,
    allotment: dict | None = None,
    as_of: date | None = None,
    rule_sources: dict | None = None,
) -> dict:
    """When offer-for-sale money and retained shares become available.

    rule_sources is what agents/rule_sources.py found in this event's pages. A rule
    whose wording was not found there gives "unknown" (lock-in) or "not stated" (listing).
    """
    allotment = allotment or {"status": "unknown", "reason": "allotment date not verified"}
    sources = rule_sources or {}
    return {
        "proceeds": _proceeds_timing(person, listing, sources.get(OFS_PROCEEDS_RULE["id"]) or {}),
        "retained": _retained_timing(person, allotment, as_of or date.today(), sources),
    }


def lock_in_rule(role: str | None) -> dict | None:
    """The first rule in config.lock_in whose role words fit this printed role."""
    if not role:
        return None
    text = role.lower()
    for rule in LOCK_IN_RULES:
        if any(word in text for word in rule["exclude_words"]):
            continue
        if any(word in text for word in rule["role_words"]):
            return rule
    return None


def _proceeds_timing(person: dict, listing: dict, source: dict) -> dict:
    """Offer-for-sale money arrives at listing, once the listing date is verified.

    source is where this event's document states the rule. When it is not found the
    timing says "at listing (not stated in this event's documents)" and keeps the TODO.
    """
    blocked = _not_a_verified_seller(person)
    if blocked is not None:
        return blocked
    if listing["status"] == "scheduled":
        return _scheduled_timing(listing)
    if listing["status"] != "verified":
        return unknown(listing["reason"])
    stated = bool(source.get("found"))
    words = OFS_PROCEEDS_RULE["when"] if stated else OFS_PROCEEDS_RULE["not_found"]
    result = {
        "status": "at_listing",
        "when": f"{words} (trading start printed as {listing['date_as_printed']})",
        "rule": OFS_PROCEEDS_RULE["id"],
        "rule_found": stated,
        "todo": OFS_PROCEEDS_RULE["todo"],
        "sources": ([source] if stated else []) + listing["inputs"],
    }
    if listing.get("past"):
        listed_on = date.fromisoformat(listing["listed_on"])
        since = f"in hand since {fmt_date(listed_on)} ({listing['age']})"
        result.update(
            status="in_hand",
            when=since if stated else f"{since}; {OFS_PROCEEDS_RULE['not_found']}",
            since=listing["listed_on"],
            days_since=listing["days_since"],
        )
    return result


def _scheduled_timing(listing: dict) -> dict:
    """Proceeds timing from the timetable date. Recency counts from that date."""
    when = (f"listing scheduled for {listing['date_as_printed']} per the offer document's timetable; "
            "not confirmed by a listing notice")
    result = {"status": "scheduled", "when": when, "date_as_printed": listing["date_as_printed"], "sources": listing["inputs"]}
    if listing.get("days_since") is not None:
        result["days_since"] = listing["days_since"]
    return result


def _retained_timing(person: dict, allotment: dict, as_of: date, rule_sources: dict | None = None) -> dict:
    """Lock-in for retained shares, from the rule for this person's primary role.

    Each of the rule's periods ends at allotment date + its months. status is
    locked_in (every period still running, or the allotment date unknown),
    unlocked (every period ended) or partly_unlocked.
    """
    role = person.get("role_as_printed")
    rule = lock_in_rule(role)
    if rule is None:
        reason = f"no sourced lock-in rule for role '{role}'" if role else "no role printed"
        return unknown(reason)
    found_rule = (rule_sources or {}).get(rule["id"]) or {}
    variant = _variant(rule, found_rule.get("variant"))
    found = found_rule.get("periods") or {}
    sources = [found.get(period["label"]) or {"found": False} for period in variant["periods"]]
    if not all(source.get("found") for source in sources):
        missing = [period["label"] for period, source in zip(variant["periods"], sources) if not source.get("found")]
        return {**unknown(NOT_FOUND), "rule": rule["id"], "role_used": role, "missing_periods": missing}
    periods = [lock_in_period(period, allotment, as_of) for period in variant["periods"]]
    result = {
        "status": _lock_status(periods),
        "period": variant["period"],
        "periods": periods,
        "display": "; ".join(period["display"] for period in periods),
        "note": variant["split_note"],
        "rule": rule["id"],
        "role_used": role,
        "sources": sources + allotment.get("inputs", []),
    }
    if variant["id"] != "default":
        result["variant"] = variant["id"]
    return result


def _variant(rule: dict, variant_id: str | None) -> dict:
    """The rule wording the sources were found for. Files written before variants mean the default."""
    for variant in rule_variants(rule):
        if variant["id"] == (variant_id or "default"):
            return variant
    return rule_variants(rule)[0]


def lock_in_period(period: dict, allotment: dict, as_of: date) -> dict:
    """One lock-in period: its end date with the working, and whether it has ended by as_of.

    A period that ends on as_of counts as ended.
    """
    label, months = period["label"], period["months"]
    result = {"label": label, "months": months, "share_of_retained": period["share_of_retained"]}
    if allotment.get("status") != "verified":
        reason = allotment.get("reason", "allotment date not verified")
        display = f"{label}: {months} months from the date of Allotment ({reason})"
        return {**result, "status": "end_unknown", "ends_on": None, "display": display}
    allotted_on = date.fromisoformat(allotment["allotted_on"])
    ends_on = add_months(allotted_on, months)
    working = f"allotment {fmt_date(allotted_on)} + {months} months = {fmt_date(ends_on)}"
    result.update(ends_on=ends_on.isoformat(), working=working)
    if ends_on <= as_of:
        display = f"{label}: unlocked since {fmt_date(ends_on)} ({age_text(ends_on, as_of)}; {working})"
        return {**result, "status": "unlocked_since", "days_since": (as_of - ends_on).days, "display": display}
    return {**result, "status": "locked_until", "display": f"{label}: locked until {fmt_date(ends_on)} ({working})"}


def _lock_status(periods: list[dict]) -> str:
    """locked_in, unlocked or partly_unlocked across the rule's periods."""
    ended = [period["status"] == "unlocked_since" for period in periods]
    if ended and all(ended):
        return "unlocked"
    if any(ended):
        return "partly_unlocked"
    return "locked_in"


def seller_status(person: dict) -> str:
    """verified, unverified or no. build_people stores it; a bare dict is worked out here."""
    stored = person.get("seller_status")
    if stored:
        return stored
    return _seller_status(person, [person], set())


def _seller_status(person: dict, members: list[dict], failed_sellers: set[tuple[str, ...]]) -> str:
    """verified when the name passed in the seller table. unverified when a role says
    "selling shareholder" or a seller-table row with this name failed. Otherwise no.
    """
    if _is_seller(person):
        return "verified"
    roles = " ".join(str(role).lower() for role in (person.get("role_by_section") or {}).values())
    roles += " " + str(person.get("role_as_printed") or "").lower()
    if "selling shareholder" in roles:
        return "unverified"
    keys = {_name_key(str(row.get("name_as_printed") or "")) for row in members}
    if keys & failed_sellers:
        return "unverified"
    return "no"


def _not_a_verified_seller(person: dict) -> dict | None:
    """None for a verified seller. Otherwise the not_applicable or unknown result to return."""
    status = seller_status(person)
    if status == "verified":
        return None
    if status == "unverified":
        return unknown(_UNVERIFIED_SELLER)
    return {"status": "not_applicable", "reason": "not in the seller table"}


def _failed_seller_keys(unattributed: list[dict]) -> set[tuple[str, ...]]:
    """Identity keys of seller-table rows whose name failed verification."""
    return {
        _name_key(str(row.get("name_as_printed") or ""))
        for row in unattributed
        if row.get("section") == SELLER_SECTION and row.get("name_as_printed")
    }


def _name_key(name: str) -> tuple[str, ...]:
    """Sorted identity tokens, so "Fund - II" and "Fund II" give the same key."""
    return tuple(sorted(identity_tokens(name)))


def _is_seller(person: dict) -> bool:
    """True when the person's name was verified in the seller table."""
    return any(item.get("section") == SELLER_SECTION for item in kept_evidence(person))


def _price_summary(price: dict) -> dict:
    """The price used, as text, for the top of people.json."""
    if price["kind"] == "unknown":
        return {"kind": "unknown", "reason": price["reason"]}
    return {"kind": price["kind"], "low": str(price["low"]), "high": str(price["high"]), "inputs": price["inputs"]}



def why_money(person: dict) -> str:
    """One phrase: why this holder gets money from the event."""
    status = person.get("seller_status")
    if status == "verified":
        if person.get("shares_offered") is None:
            return "sells in the offer for sale; number of shares not verified"
        return f"sells {share_count_text(person, 'shares_offered')} in the offer for sale"
    if status == "unverified":
        return "named as a selling shareholder; seller-table row not verified"
    if person.get("shares_held_pre_offer") is not None:
        return f"holds {share_count_text(person, 'shares_held_pre_offer', qualifier=False)} before the offer; not selling in it"
    return "holding not verified"


def amount_display(person: dict) -> str:
    """The headline amount: proceeds for a seller, retained value for anyone else.

    A verified seller whose value is unknown still shows the verified shares offered.
    """
    proceeds = person["amounts"]["proceeds"]
    if proceeds.get("status") == "computed":
        return proceeds["display"]
    if person.get("seller_status") in ("verified", "unverified"):
        reason = proceeds.get("reason", "not verified")
        if person.get("seller_status") == "verified" and printed_number(person.get("shares_offered")) is not None:
            return f"{share_count_text(person, 'shares_offered')} offered; value unknown: {reason}"
        return f"unknown: {reason}"
    kept = person["amounts"]["retained"]
    if kept.get("status") == "computed":
        return f"{kept['display']}; shares, not cash"
    if kept.get("status") == "none":
        return "none retained"
    return f"unknown: {kept.get('reason', 'not verified')}"


def timing_display(person: dict) -> str:
    """When the money in amount_display becomes available."""
    return _display_timing(person)[0]


def timing_display_status(person: dict) -> str:
    """The status of the timing that timing_display shows, or "unknown". The app's pill uses it."""
    return _display_timing(person)[1]


def _display_timing(person: dict) -> tuple[str, str]:
    """(words, status) for the timing of the money in amount_display: proceeds for a seller, else retained."""
    if person.get("seller_status") in ("verified", "unverified"):
        timing = person["timing"]["proceeds"]
        if timing.get("status") == "scheduled" and timing.get("days_since") is not None:
            return _past_timetable_words(timing), "listed_per_timetable"
        if timing.get("status") in ("at_listing", "in_hand", "scheduled"):
            return timing["when"], timing["status"]
        return f"unknown: {timing.get('reason', 'not verified')}", "unknown"
    timing = person["timing"]["retained"]
    if timing.get("status") in ("locked_in", "unlocked", "partly_unlocked"):
        return timing.get("display") or f"locked in: {timing['period']}", timing["status"]
    return f"unknown: {timing.get('reason', 'not verified')}", "unknown"


def _past_timetable_words(timing: dict) -> str:
    """A timetable listing date that has passed, in RM words: past tense, never "scheduled"."""
    printed = timing.get("date_as_printed") or _TIMETABLE_DATE.search(timing.get("when") or "")
    printed = printed.group(1) if hasattr(printed, "group") else printed
    listed_on = parse_printed_date(str(printed)) if printed else None
    day = fmt_date(listed_on) if listed_on else (printed or "the timetable date")
    days = timing["days_since"]
    age = "today" if days == 0 else f"{days} days ago"
    return f"in hand since about {day} ({age}), the listing date in the offer timetable"


def share_count_text(person: dict, field: str, qualifier: bool = True) -> str:
    """"up to 12,345 shares" from a printed "Up to 12,345 Equity Shares": one "up to", one "shares".

    The number is kept as printed; "up to" is added once when the qualifier or
    the printed string says it. A string with no readable number is shown as printed.
    """
    raw = str(person.get(field) or "")
    digits = _SHARE_DIGITS.search(raw)
    if printed_number(raw) is None or digits is None:
        return raw
    prefix = "up to " if qualifier and (up_to(person) or raw.strip().lower().startswith("up to")) else ""
    return f"{prefix}{digits.group(0)} shares"
