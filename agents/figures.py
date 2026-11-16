"""Shared pieces of a computed figure: evidence links, rupee and crore text. Code only."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from agents.verify import printed_number

CRORE = Decimal(10_000_000)
_TWO_PLACES = Decimal("0.01")


def kept_evidence(record: dict, field: str | None = None) -> list[dict]:
    """Evidence whose value verify kept. Old files without the flag count as kept."""
    return [
        item
        for item in record.get("evidence") or []
        if item.get("field_kept", True) and (field is None or item.get("field") == field)
    ]


def input_ref(field: str, record: dict) -> dict:
    """One input value with links to the pages that verified it."""
    links = []
    for item in kept_evidence(record, field):
        url = item.get("source_url")
        links.append({
            "source_url": url,
            "pdf_index": item.get("pdf_index"),
            "printed_page": item.get("printed_page"),
            "link": f"{url}#page={item.get('pdf_index')}" if url else None,
            "quote": item.get("quote"),
        })
    return {"field": field, "value": record.get(field), "evidence": links}


def computed_figure(low: Decimal, high: Decimal, display: str, working: str, price: dict, inputs: list[dict]) -> dict:
    """A computed amount in rupees and crore, with its working and every input's evidence."""
    return {
        "status": "computed",
        "rupees_low": str(low),
        "rupees_high": str(high),
        "crore_low": str(crore(low)),
        "crore_high": str(crore(high)),
        "display": display,
        "working": working,
        "price_kind": price["kind"],
        "inputs": inputs + price["inputs"],
    }


def unknown(reason: str) -> dict:
    """A figure or timing that cannot be worked out from verified values."""
    return {"status": "unknown", "reason": reason}


def crore(rupees: Decimal) -> Decimal:
    """Rupees to crore, two decimals, half up."""
    return (rupees / CRORE).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def crore_range(low: Decimal, high: Decimal) -> str:
    """"₹6.08 crore", or "₹5.79 to ₹6.08 crore" for a band."""
    if crore(low) == crore(high):
        return f"₹{fmt(crore(low))} crore"
    return f"₹{fmt(crore(low))} to ₹{fmt(crore(high))} crore"


def rupees_range(price: dict) -> str:
    """"₹1,250", or "₹1,200 to ₹1,250" for a band."""
    if price["low"] == price["high"]:
        return f"₹{fmt(price['low'])}"
    return f"₹{fmt(price['low'])} to ₹{fmt(price['high'])}"


def fmt(value: Decimal) -> str:
    """Comma-grouped digits, keeping the decimals as printed: 12,000 and 12.50."""
    return f"{value:,}"


def up_to(person: dict) -> bool:
    """True when the printed qualifier is "up to"."""
    return " ".join(str(person.get("qualifier") or "").lower().split()) == "up to"


def shown(text: object, value: Decimal) -> str:
    """The number as the document printed it ("30,00,000"), when the field is only that number."""
    printed = str(text or "").strip()
    if re.fullmatch(r"\d[\d,]*(\.\d+)?", printed):
        return printed
    return fmt(value)


# Rupee units printed after an amount, as multipliers. Longer words first, so "crores"
# is not read as "cr". A unit must not sit inside a longer word ("across").
_UNITS = re.compile(r"(?<![a-z])(crores?|cr\.?|lakhs?|lacs?|millions?|mn|billions?|bn)(?![a-z])")
UNIT_RUPEES = {"crore": Decimal(10_000_000), "cr": Decimal(10_000_000), "lakh": Decimal(100_000),
               "lac": Decimal(100_000), "million": Decimal(1_000_000), "mn": Decimal(1_000_000),
               "billion": Decimal(1_000_000_000), "bn": Decimal(1_000_000_000)}


def rupees_from_printed(text: object) -> Decimal | None:
    """A printed amount as rupees: "₹ 3,000.00 million" is 3000000000. None without one number and one unit."""
    folded = str(text or "").lower()
    units = _UNITS.findall(folded)
    number = printed_number(folded)
    if number is None or len(units) != 1:
        return None
    unit = units[0].rstrip(".")
    unit = unit[:-1] if unit.endswith("s") else unit
    return number * UNIT_RUPEES[unit]


def printed_half_step(text: object) -> Decimal | None:
    """Half the smallest unit an amount is printed to, in rupees: "₹ 0.02 million" is ₹5,000.

    A printed amount is rounded to its last digit, so it cannot say more than this.
    """
    folded = str(text or "").lower()
    rupees = rupees_from_printed(folded)
    if rupees is None:
        return None
    digits = re.search(r"\d[\d,]*(?:\.(\d+))?", folded)
    places = len(digits.group(1) or "") if digits else 0
    unit = rupees / printed_number(folded) if printed_number(folded) else Decimal(1)
    return unit * Decimal(1).scaleb(-places) / 2
