"""Stock-exchange offer-for-sale rules: proceeds at the floor price, and timing after the sale date.

Amount: shares offered × floor price, labelled "at floor price; actual sale price
not verified; may be higher". A green-shoe the notice prints for the seller is a
separate figure. A seller whose own shares are not printed (only a total for all
sellers) gets "unknown", with that reason.
Timing: "settles after <sale date>", quoting the notice's printed settlement words.
No settlement rule is filled in from memory; the T+N wording is not turned into a date.
"""

from __future__ import annotations

from datetime import date

from agents.dates import age_text, fmt_date, parse_printed_date
from agents.figures import computed_figure, crore_range, fmt, input_ref, kept_evidence, shown, unknown, up_to
from agents.rules_ipo import share_count_text
from agents.verify import printed_number

FLOOR_LABEL = "at floor price; actual sale price not verified; may be higher"
SELLER_SECTION = "ofs_sellers"


def context(extracted: dict, as_of: date) -> dict:
    """Floor price, total offer and sale dates, each verified or unknown."""
    offer = extracted.get("offer_facts") or {}
    sale = parse_printed_date(str(offer.get("sale_date") or ""))
    return {
        "offer": offer,
        "floor": printed_number(offer.get("floor_price")),
        "total": offer.get("total_shares_offered"),
        "sale_on": sale,
        "as_of": as_of,
    }


def summary(context: dict) -> dict:
    """Top-level people.json keys: the floor price and sale facts the figures used."""
    offer, floor, sale = context["offer"], context["floor"], context["sale_on"]
    return {
        "price_basis": (
            {"kind": "floor_price", "low": str(floor), "high": str(floor), "inputs": [input_ref("floor_price", offer)]}
            if floor is not None else {"kind": "unknown", "reason": "no verified floor price"}
        ),
        "sale": {
            "sale_date": offer.get("sale_date") or "unknown",
            "sale_date_parsed": sale.isoformat() if sale else None,
            "sale_date_retail": offer.get("sale_date_retail") or "unknown",
            "settlement_as_printed": offer.get("settlement_as_printed") or "unknown",
            "total_shares_offered": offer.get("total_shares_offered") or "unknown",
            "greenshoe_total": offer.get("greenshoe_total") or "unknown",
        },
    }


def apply(person: dict, members: list[dict], context: dict) -> None:
    """Set seller_status, amounts and timing on one person."""
    named = any(item.get("section") == SELLER_SECTION for item in kept_evidence(person))
    person["seller_status"] = "verified" if named else "no"
    person["amounts"] = {"proceeds": proceeds(person, context)}
    greenshoe = greenshoe_proceeds(person, context)
    if greenshoe is not None:
        person["amounts"]["greenshoe"] = greenshoe
    person["timing"] = {"proceeds": sale_timing(person, context)}


def proceeds(person: dict, context: dict) -> dict:
    """shares_offered × floor price, labelled as a floor-price figure."""
    if person.get("seller_status") != "verified":
        return {"status": "not_applicable", "reason": "not named as a seller in the notice"}
    floor = context["floor"]
    if floor is None:
        return unknown("floor price not verified")
    shares = printed_number(person.get("shares_offered"))
    if shares is None:
        total = context["total"]
        if total:
            total_text = share_count_text({"total": total}, "total")
            return unknown(f"the notice prints {total_text} for all sellers together, not this seller's own shares")
        return unknown("shares offered by this seller not verified")
    value = shares * floor
    working = f"{shown(person.get('shares_offered'), shares)} × ₹{fmt(floor)} floor = {crore_range(value, value)}"
    prefix = "up to " if up_to(person) else ""
    display = f"{prefix}{crore_range(value, value)} ({FLOOR_LABEL})"
    basis = {"kind": "floor_price", "inputs": [input_ref("floor_price", context["offer"])]}
    return {**computed_figure(value, value, display, working, basis, [input_ref("shares_offered", person)]),
            "label": FLOOR_LABEL}


def greenshoe_proceeds(person: dict, context: dict) -> dict | None:
    """A separate figure for this seller's green-shoe shares, when the notice prints a number for it."""
    shares = printed_number(person.get("greenshoe_shares"))
    floor = context["floor"]
    if shares is None or floor is None or shares == 0:
        return None
    value = shares * floor
    working = f"{shown(person.get('greenshoe_shares'), shares)} × ₹{fmt(floor)} floor = {crore_range(value, value)}"
    display = f"up to {crore_range(value, value)} more if the green-shoe is used ({FLOOR_LABEL})"
    basis = {"kind": "floor_price", "inputs": [input_ref("floor_price", context["offer"])]}
    return {**computed_figure(value, value, display, working, basis, [input_ref("greenshoe_shares", person)]),
            "label": FLOOR_LABEL}


def sale_timing(person: dict, context: dict) -> dict:
    """Settlement after the printed sale date, with the notice's own settlement words."""
    if person.get("seller_status") != "verified":
        return {"status": "not_applicable", "reason": "not named as a seller in the notice"}
    offer, sale = context["offer"], context["sale_on"]
    if sale is None:
        printed = offer.get("sale_date")
        reason = f"sale date '{printed}' is not in a date form the code reads" if printed else "sale date not verified"
        return unknown(reason)
    when = f"settles after the sale on {fmt_date(sale)}"
    if sale <= context["as_of"]:
        when += f" ({age_text(sale, context['as_of'])})"
    settlement = offer.get("settlement_as_printed")
    result = {"status": "after_date", "when": when, "sources": [input_ref("sale_date", offer)]}
    if settlement:
        result["settlement_as_printed"] = settlement
        result["sources"].append(input_ref("settlement_as_printed", offer))
        result["note"] = "settlement words as printed; the trading-day count is not turned into a date"
    if sale <= context["as_of"]:
        result["days_since"] = (context["as_of"] - sale).days
    return result


def why_money(person: dict) -> str:
    """One phrase: why this seller gets money."""
    if person.get("seller_status") != "verified":
        return "not named as a seller in the notice"
    if person.get("shares_offered") is None:
        return "sells in the offer for sale through the stock exchange; own shares not printed"
    return f"sells {share_count_text(person, 'shares_offered')} in the offer for sale through the stock exchange"


def amount_display(person: dict) -> str:
    """The headline amount, or the reason it is unknown."""
    figure = person["amounts"]["proceeds"]
    if figure.get("status") == "computed":
        return figure["display"]
    return f"unknown: {figure.get('reason', 'not verified')}"


def timing_display(person: dict) -> str:
    """When the sale settles."""
    return _display_timing(person)[0]


def timing_display_status(person: dict) -> str:
    """The status of the timing that timing_display shows, or "unknown". The app's pill uses it."""
    return _display_timing(person)[1]


def _display_timing(person: dict) -> tuple[str, str]:
    """(words, status) for the sale's settlement."""
    timing = person["timing"]["proceeds"]
    if timing.get("when"):
        return timing["when"], timing.get("status") or "unknown"
    return f"unknown: {timing.get('reason', 'not verified')}", "unknown"
