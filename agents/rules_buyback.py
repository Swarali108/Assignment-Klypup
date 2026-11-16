"""Buyback (tender offer) rules: tender proceeds and payment timing.

Amount, from verified values only:
  - shares accepted (results document) × buyback price: the actual figure;
  - else maximum shares intended × buyback price × acceptance ratio: an estimate;
  - else the general-category entitlement ("N for every M held") × shares held (or intended),
    capped at the shares intended, × buyback price: an estimate, since acceptance can exceed
    the entitlement when other holders do not tender;
  - else maximum shares intended × buyback price: "up to; acceptance is pro rata, so actual may be lower".
A promoter whose verified intention says they will not tender is "not tendering", with no amount.
Timing: the printed payment date if verified; else "after the buyback closes on <date>".
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from agents.dates import age_text, fmt_date, parse_printed_date
from agents.figures import computed_figure, crore_range, fmt, input_ref, shown, unknown
from agents.rules_ipo import share_count_text
from agents.verify import number_tokens, printed_number

PRO_RATA = "up to; acceptance is pro rata, so actual may be lower"
# Words that say a holder will not take part: "not to participate", "will not tender".
_NOT_TENDERING = re.compile(r"\bnot\b(\s+\w+){0,3}\s+(participat\w*|tender\w*)", re.IGNORECASE)
_TENDERING = re.compile(r"\b(participat\w*|tender\w*)\b", re.IGNORECASE)
# "10 Equity Shares for every 197 Equity Shares held", "28 out of every 627".
_FOR_EVERY = re.compile(r"(\d[\d,]*)\D{0,40}?\b(?:for|out\s+of)\s+every\s+(\d[\d,]*)", re.IGNORECASE)
ENTITLEMENT_LABEL = "estimate at the general-category entitlement"


def context(extracted: dict, as_of: date) -> dict:
    """Buyback price, acceptance ratio and dates, each verified or unknown."""
    offer = extracted.get("offer_facts") or {}
    return {
        "offer": offer,
        "price": printed_number(offer.get("buyback_price")),
        "ratio": acceptance_ratio(offer.get("acceptance_ratio")),
        "entitlement": entitlement_ratio(offer.get("entitlement_ratio")),
        "payment": _dated(offer, "payment_date", as_of),
        "closing": _dated(offer, "closing_date", as_of),
        "as_of": as_of,
    }


def summary(context: dict) -> dict:
    """Top-level people.json keys: the price and dates the figures used."""
    offer = context["offer"]
    price = context["price"]
    return {
        "price_basis": (
            {"kind": "buyback_price", "low": str(price), "high": str(price), "inputs": [input_ref("buyback_price", offer)]}
            if price is not None else {"kind": "unknown", "reason": "no verified buyback price"}
        ),
        "buyback_dates": {key: context[key] for key in ("payment", "closing")},
        "acceptance": (
            {"ratio": str(context["ratio"]), "inputs": [input_ref("acceptance_ratio", offer)]}
            if context["ratio"] is not None else {"status": "unknown", "reason": "no verified acceptance ratio"}
        ),
    }


def apply(person: dict, members: list[dict], context: dict) -> None:
    """Set participation, seller_status, amounts and timing on one person."""
    person["participation"] = participation(person)
    person["seller_status"] = "verified" if person["participation"] == "tendering" else "no"
    person["amounts"] = {"proceeds": proceeds(person, context)}
    person["timing"] = {"proceeds": payment_timing(person, context)}


def participation(person: dict) -> str:
    """tendering, not tendering, or unknown, from verified fields only."""
    intention = str(person.get("intention_as_printed") or "")
    if intention and _NOT_TENDERING.search(intention):
        return "not tendering"
    if person.get("shares_intended") or person.get("shares_accepted"):
        return "tendering"
    if intention and _TENDERING.search(intention):
        return "tendering"
    return "unknown"


def acceptance_ratio(text: object) -> Decimal | None:
    """"1:4" is 0.25, "25%" is 0.25, "0.25" is 0.25. Anything else is None."""
    if text is None:
        return None
    raw = str(text)
    numbers = number_tokens(raw)
    if len(numbers) == 2 and ":" in raw and numbers[1] != 0:
        return numbers[0] / numbers[1]
    if len(numbers) == 1 and "%" in raw:
        return numbers[0] / 100
    if len(numbers) == 1 and numbers[0] <= 1:
        return numbers[0]
    return None


def entitlement_ratio(text: object) -> Decimal | None:
    """"10 Equity Shares for every 197 held" is 10/197. A ratio of 1 or more is not an entitlement."""
    if text is None:
        return None
    match = _FOR_EVERY.search(str(text))
    if match is None:
        return None
    taken, every = (printed_number(group) for group in match.groups())
    if taken is None or every is None or every == 0 or taken >= every:
        return None
    return taken / every


def proceeds(person: dict, context: dict) -> dict:
    """Tender proceeds by the rule in the module docstring."""
    status = person.get("participation")
    if status == "not tendering":
        return {"status": "not_tendering", "display": "not tendering",
                "reason": f"states: {person.get('intention_as_printed')}", "inputs": [input_ref("intention_as_printed", person)]}
    price = context["price"]
    if price is None:
        return unknown("buyback price not verified")
    price_basis = {"kind": "buyback_price", "inputs": [input_ref("buyback_price", context["offer"])]}
    accepted = printed_number(person.get("shares_accepted"))
    if accepted is not None:
        value = accepted * price
        working = f"{shown(person.get('shares_accepted'), accepted)} accepted × ₹{fmt(price)} = {crore_range(value, value)}"
        figure = computed_figure(value, value, f"{crore_range(value, value)} (shares accepted, as printed)",
                                 working, price_basis, [input_ref("shares_accepted", person)])
        return {**figure, "label": "actual"}
    intended = printed_number(person.get("shares_intended"))
    if intended is None:
        reason = "tender intention not verified" if status == "unknown" else "maximum shares intended not printed"
        return unknown(reason)
    ratio = context["ratio"]
    if ratio is not None:
        value = intended * ratio * price
        working = f"{shown(person.get('shares_intended'), intended)} × {ratio.normalize()} acceptance × ₹{fmt(price)} = {crore_range(value, value)}"
        display = f"{crore_range(value, value)} (estimate: acceptance ratio applied to the maximum intended)"
        inputs = [input_ref("shares_intended", person), input_ref("acceptance_ratio", context["offer"])]
        return {**computed_figure(value, value, display, working, price_basis, inputs), "label": "estimate"}
    entitled = _entitlement_figure(person, intended, price, price_basis, context)
    if entitled is not None:
        return entitled
    value = intended * price
    working = f"{shown(person.get('shares_intended'), intended)} × ₹{fmt(price)} = {crore_range(value, value)}"
    display = f"up to {crore_range(value, value)}; acceptance is pro rata, so actual may be lower"
    figure = computed_figure(value, value, display, working, price_basis, [input_ref("shares_intended", person)])
    return {**figure, "label": PRO_RATA}


def _entitlement_figure(person: dict, intended: Decimal, price: Decimal, price_basis: dict, context: dict) -> dict | None:
    """Shares held (or intended) × entitlement, capped at the shares intended, × price. None without a ratio."""
    ratio = context.get("entitlement")
    if ratio is None:
        return None
    held = printed_number(person.get("shares_held_pre_offer"))
    base_field, base = ("shares_held_pre_offer", held) if held is not None else ("shares_intended", intended)
    shares = min(intended, (base * ratio).to_integral_value(rounding="ROUND_FLOOR"))
    value = shares * price
    offer = context["offer"]
    working = (f"{shown(person.get(base_field), base)} × {offer.get('entitlement_ratio')} = {indian(shares)} shares "
               f"(capped at {shown(person.get('shares_intended'), intended)} intended) × ₹{fmt(price)} = "
               f"{crore_range(value, value)}. Acceptance can be higher when other holders do not tender.")
    display = f"about {crore_range(value, value)} ({ENTITLEMENT_LABEL})"
    inputs = [input_ref(base_field, person), input_ref("shares_intended", person), input_ref("entitlement_ratio", offer)]
    inputs = [ref for i, ref in enumerate(inputs) if ref not in inputs[:i]]
    return {**computed_figure(value, value, display, working, price_basis, inputs), "label": "estimate"}


def indian(value: Decimal) -> str:
    """A whole number in Indian digit grouping: 1,33,04,144."""
    digits = str(int(value))
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups) + "," + tail


def payment_timing(person: dict, context: dict) -> dict:
    """The printed payment date, else after the printed closing date, else unknown."""
    if person.get("participation") == "not tendering":
        return {"status": "not_applicable", "reason": "not tendering"}
    for key, status, words in (("payment", "settles", "paid by"), ("closing", "after_date", "after the buyback closes on")):
        dated = context[key]
        if dated.get("status") != "verified":
            continue
        when = f"{words} {dated['display']}"
        result = {"status": status, "when": when, "sources": dated["inputs"]}
        if dated.get("days_since") is not None:
            result["days_since"] = dated["days_since"]
        return result
    return unknown("no verified payment or closing date")


def why_money(person: dict) -> str:
    """One phrase: why this holder gets money, or why not."""
    status = person.get("participation")
    if status == "not tendering":
        return "states they will not tender in the buyback"
    if status == "tendering":
        field = "shares_accepted" if person.get("shares_accepted") else "shares_intended"
        if person.get(field):
            return f"tenders {share_count_text(person, field)} in the buyback"
        return "tenders in the buyback; shares not printed"
    if person.get("shares_held_pre_offer"):
        return f"holds {share_count_text(person, 'shares_held_pre_offer', qualifier=False)}; tender intention not printed"
    return "tender intention not printed"


def amount_display(person: dict) -> str:
    """The headline amount, "not tendering", or the reason it is unknown."""
    figure = person["amounts"]["proceeds"]
    if figure.get("status") in ("computed", "not_tendering"):
        return figure["display"]
    return f"unknown: {figure.get('reason', 'not verified')}"


def timing_display(person: dict) -> str:
    """When the buyback money is paid."""
    return _display_timing(person)[0]


def timing_display_status(person: dict) -> str:
    """The status of the timing that timing_display shows, or "unknown". The app's pill uses it."""
    return _display_timing(person)[1]


def _display_timing(person: dict) -> tuple[str, str]:
    """(words, status) for the buyback payment."""
    timing = person["timing"]["proceeds"]
    if timing.get("when"):
        return timing["when"], timing.get("status") or "unknown"
    word = "not applicable" if timing.get("status") == "not_applicable" else "unknown"
    return f"{word}: {timing.get('reason', 'not verified')}", word.replace(" ", "_")


def _dated(offer: dict, field: str, as_of: date) -> dict:
    """One printed date, parsed, with how long ago it was."""
    value = offer.get(field)
    if value is None or not str(value).strip():
        return {"status": "unknown", "reason": f"{field} not verified"}
    parsed = parse_printed_date(str(value))
    if parsed is None:
        return {"status": "unknown", "reason": f"{field} '{value}' is not in a date form the code reads"}
    result = {"status": "verified", "date": parsed.isoformat(), "display": fmt_date(parsed),
              "inputs": [input_ref(field, offer)]}
    if parsed <= as_of:
        result["days_since"] = (as_of - parsed).days
        result["display"] += f" ({age_text(parsed, as_of)})"
    return result
