"""Rank holders into an RM call list. Code only, no model call.

Every holder gets a call tier (config/ranking.py CALL_TIERS), in call order:
  1. cash_now: they receive cash from this event (offer-for-sale proceeds, buyback
     tender, exchange offer-for-sale) that is still to come or came in the last
     CASH_NOW_DAYS days. Ranked on the proceeds trigger.
  2. unlock: not selling, but a lock-in ended in the last FRESH_UNLOCK_DAYS days.
     Valued where the share of the holding that unlocked is known; else ranked by
     the holding, discounted by UNKNOWN_SPLIT_WEIGHT.
  3. holding: everyone else, by later_score = retained value × confidence × retained-timing weight,
     or by the proceeds score for a seller whose cash came more than CASH_NOW_DAYS ago.
Within a tier: a known amount before an unknown one, then score, then retained
value, then the cleaned name, so the order never depends on input order.

A trigger's score is money × confidence weight × timing weight × recency weight.
A timetable listing date that has passed counts as past ("listed_per_timetable").

Lists: callable (people and family vehicles), entities (funds and companies,
including "unsure" holders whose name reads as a fund), and context (holders who
get no money from this event: buyback non-tenderers, deal buyers, or any person
whose rules module set context_reason), each with context_reason.
Each entry carries why_money, amount_display and timing_display from the event
type's rules module, so the report and the app show the same words.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agents.dates import fmt_date
from agents.event_rules import rules_for
from agents.names import name_tokens
from config.ranking import (
    CALL_TIERS,
    CALLABLE_TYPES,
    CASH_IN_HAND_STATUSES,
    CASH_NOW_DAYS,
    CONFIDENCE_WEIGHTS,
    FRESH_UNLOCK_DAYS,
    FRESH_UNLOCK_WEIGHT,
    FUND_LIKE_TOKENS,
    RECENCY_WEIGHTS,
    TIMING_WEIGHTS,
    UNDATED_RECENCY,
    UNKNOWN_SPLIT_WEIGHT,
)

ZERO = Decimal(0)
NOT_TENDERING_REASON = "States they will not tender shares in the buyback, so they get no money from this event."


def rank_people(people: list[dict], event_type: str = "ipo") -> dict:
    """{"callable": [...], "entities": [...], "context": [...]}, each list ranked from 1."""
    rules = rules_for(event_type)
    entries = [_entry(person, rules) for person in people]
    context = [entry for entry in entries if entry.get("context_reason")]
    rest = [entry for entry in entries if not entry.get("context_reason")]
    callable_ = [entry for entry in rest if _callable(entry)]
    entities = [entry for entry in rest if not _callable(entry)]
    return {"callable": _ranked(callable_), "entities": _ranked(entities, entity=True),
            "context": _ranked(context, context=True)}


def fund_like(name: str) -> bool:
    """True when a word of the name marks a fund or company (config FUND_LIKE_TOKENS)."""
    return any(token in FUND_LIKE_TOKENS for token in name_tokens(name or ""))


def _callable(entry: dict) -> bool:
    """A person or family vehicle; an "unsure" holder only when the name does not read as a fund."""
    if entry["holder_type"] not in CALLABLE_TYPES:
        return False
    return not (entry["holder_type"] == "unsure" and fund_like(entry["name_as_printed"]))


def money_now(person: dict) -> Decimal:
    """Upper proceeds figure in crore. 0 when proceeds are unknown or not applicable."""
    figure = person["amounts"]["proceeds"]
    if figure.get("status") != "computed":
        return ZERO
    return Decimal(figure["crore_high"])


def later_value(person: dict) -> Decimal:
    """Upper retained value in crore. 0 when it is unknown or nothing is retained."""
    figure = person["amounts"].get("retained") or {}
    if figure.get("status") != "computed":
        return ZERO
    return Decimal(figure["crore_high"])


def recency_weight(days: int | None) -> tuple[Decimal, str]:
    """The RECENCY_WEIGHTS band for a trigger this many days old. None (not yet happened) is UNDATED_RECENCY."""
    if days is None:
        return UNDATED_RECENCY
    for limit, weight, reason in RECENCY_WEIGHTS:
        if limit is None or days <= limit:
            return weight, reason
    return RECENCY_WEIGHTS[-1][1], RECENCY_WEIGHTS[-1][2]


def triggers(person: dict, confidence_weight: Decimal) -> list[dict]:
    """The person's money triggers, each with its score parts."""
    found: list[dict] = []
    if person.get("seller_status") in ("verified", "unverified"):
        timing = person["timing"]["proceeds"]
        status = proceeds_status(timing)
        weight = TIMING_WEIGHTS.get(status, TIMING_WEIGHTS["unknown"])[0]
        recency, _reason = recency_weight(timing.get("days_since"))
        label = "proceeds, timing unknown"
        if status == "listed_per_timetable":
            label = f"proceeds since the timetable listing date ({timing['days_since']} days ago)"
        elif timing.get("when"):
            label = f"proceeds {timing['when']}"
        found.append(_trigger("proceeds", label, money_now(person), confidence_weight, status, weight, recency,
                              timing.get("days_since")))
    kept_nothing = (person["amounts"].get("retained") or {}).get("status") == "none"
    for period in [] if kept_nothing else (person["timing"].get("retained") or {}).get("periods") or []:
        if period.get("status") != "unlocked_since" or period.get("days_since", FRESH_UNLOCK_DAYS + 1) > FRESH_UNLOCK_DAYS:
            continue
        known = period.get("share_of_retained") == "all"
        money = later_value(person) if known else ZERO
        label = f"shares unlocked on {fmt_date(date.fromisoformat(period['ends_on']))}; shares, not cash"
        if not known:
            label += f" ({period['label']}; how many shares is not printed)"
        recency, _reason = recency_weight(period.get("days_since"))
        unlock = _trigger("unlock", label, money, confidence_weight, "unlocked", FRESH_UNLOCK_WEIGHT[0], recency,
                          period.get("days_since"))
        unlock["ends_on"] = period["ends_on"]
        unlock["value_known"] = known
        if not known:
            # Ranked by the holding: the unlocked part is somewhere between none and all of it.
            holding = later_value(person)
            unlock["rank_value_crore"] = str(holding)
            unlock["score"] = str(holding * UNKNOWN_SPLIT_WEIGHT[0] * confidence_weight * FRESH_UNLOCK_WEIGHT[0] * recency)
        found.append(unlock)
    return found


def proceeds_status(timing: dict) -> str:
    """The proceeds timing status, with a passed timetable listing date read as listed_per_timetable."""
    status = timing.get("status", "unknown")
    if status == "scheduled" and timing.get("days_since") is not None:
        return "listed_per_timetable"
    return status


def _trigger(kind: str, label: str, money: Decimal, confidence_weight: Decimal, status: str,
             timing_weight: Decimal, recency: Decimal, days_since: int | None) -> dict:
    """One trigger and its score. days_since is None when it has not happened yet or is undated."""
    return {
        "kind": kind,
        "days_since": days_since,
        "label": label,
        "money_crore": str(money),
        "timing_status": status,
        "timing_weight": str(timing_weight),
        "recency_weight": str(recency),
        "score": str(money * confidence_weight * timing_weight * recency),
    }


def _entry(person: dict, rules) -> dict:
    """Score one person, put them in a call tier, and keep the parts of the score."""
    seller = person.get("seller_status") in ("verified", "unverified")
    level = person["confidence"]["level"]
    confidence_weight = CONFIDENCE_WEIGHTS[level][0]
    found = triggers(person, confidence_weight)
    proceeds = [item for item in found if item["kind"] == "proceeds"]
    unlocks = [item for item in found if item["kind"] == "unlock"]
    retained_status = (person["timing"].get("retained") or {}).get("status", "unknown")
    retained_weight = TIMING_WEIGHTS.get(retained_status, TIMING_WEIGHTS["unknown"])[0]
    later = later_value(person)
    later_score = later * confidence_weight * retained_weight
    fresh_cash = [item for item in proceeds if item["days_since"] is None or item["days_since"] <= CASH_NOW_DAYS]
    if fresh_cash:
        call_tier, best = "cash_now", fresh_cash[0]
    elif unlocks:
        # Tier from the unlock; score from the stronger of the unlock and any earlier cash.
        call_tier, best = "unlock", max(unlocks + proceeds, key=lambda item: (Decimal(item["score"]), item["kind"] == "unlock"))
    elif proceeds and Decimal(proceeds[0]["score"]) >= later_score:
        call_tier, best = "holding", proceeds[0]
    else:
        call_tier, best = "holding", None
    timing_status = best["timing_status"] if best else retained_status
    entry = {
        "person_id": person["person_id"],
        "name_as_printed": person["name_as_printed"],
        "name_clean": person["name_clean"],
        "holder_type": person["holder_type"],
        "role_as_printed": person.get("role_as_printed"),
        "tier": "seller" if (seller or found) else "non_seller",
        "call_tier": call_tier,
        "call_tier_label": _tier_label(call_tier, person),
        "amount_known": _amount_known(call_tier, person),
        "money_now_crore": str(money_now(person)) if call_tier == "cash_now" else (best["money_crore"] if best else str(ZERO)),
        "confidence": level,
        "confidence_weight": str(confidence_weight),
        "timing_status": timing_status,
        "timing_weight": best["timing_weight"] if best else str(retained_weight),
        "recency_weight": best["recency_weight"] if best else "1.0",
        "score": best["score"] if best else str(later_score),
        "trigger": best,
        "triggers": found,
        "later_value_crore": str(later),
        "later_score": str(later_score),
        "why_money": rules.why_money(person),
        "amount_display": rules.amount_display(person),
        "timing_display": rules.timing_display(person),
        "timing_display_status": rules.timing_display_status(person),
        "family_group": person.get("family_group"),
        "household_id": (person.get("family_group") or {}).get("id"),
        "holding_display": _holding_display(person),
    }
    if person.get("participation") == "not tendering":
        entry["context_reason"] = NOT_TENDERING_REASON
    elif person.get("context_reason"):
        # A rules module that already knows this holder gets no money (a buyer in a deal report).
        entry["context_reason"] = person["context_reason"]
    return entry


def _holding_display(person: dict) -> str | None:
    """The retained value's display text, when it is a computed figure."""
    figure = person["amounts"].get("retained") or {}
    return figure.get("display") if figure.get("status") == "computed" else None


def _amount_known(call_tier: str, person: dict) -> bool:
    """True when the tier's headline amount is a computed rupee figure.

    Cash now: the proceeds. Otherwise the holding, or for a seller whose cash came
    earlier, the proceeds or the holding.
    """
    computed = {key for key, figure in person["amounts"].items() if (figure or {}).get("status") == "computed"}
    if call_tier == "cash_now":
        return "proceeds" in computed
    seller = person.get("seller_status") in ("verified", "unverified")
    return "retained" in computed or (seller and "proceeds" in computed)


def _tier_label(call_tier: str, person: dict) -> str:
    """The tier in RM words. Cash is "in hand" only when its date has passed."""
    if call_tier == "unlock":
        return "Shares just unlocked"
    seller = person.get("seller_status") in ("verified", "unverified")
    if call_tier == "holding":
        return "Cash received earlier" if seller else "Holds shares"
    timing = person["timing"]["proceeds"]
    status = proceeds_status(timing)
    if status in CASH_IN_HAND_STATUSES or (status in ("settles", "after_date") and timing.get("days_since") is not None):
        return "Cash in hand"
    if status == "unknown":
        return "Cash due, date not confirmed"
    return "Cash due soon"


def _ranked(entries: list[dict], entity: bool = False, context: bool = False) -> list[dict]:
    """Sort, number from 1, and explain each position."""
    ordered = sorted(entries, key=_sort_key)
    for position, entry in enumerate(ordered, start=1):
        entry["rank"] = position
        entry["rank_reasons"] = _reasons(entry, ordered, position, entity, context)
    return ordered


def _sort_key(entry: dict) -> tuple:
    """Call tier; known amount first; score; retained value; name."""
    return (CALL_TIERS.index(entry["call_tier"]), not entry["amount_known"], -Decimal(entry["score"]),
            -Decimal(entry["later_score"]), entry["name_clean"])


def why_rank(entry: dict) -> str:
    """One plain-English line: why this holder sits in this tier and place."""
    label = entry["call_tier_label"]
    if entry.get("context_reason"):
        return entry["context_reason"]
    if entry["call_tier"] == "cash_now":
        if entry["amount_known"]:
            return f"{label}: {entry['amount_display']}; {entry['timing_display']}."
        return (f"{label}: receives cash from this event, but the amount is not disclosed, "
                "so they come after holders with a known amount.")
    if entry["call_tier"] == "unlock":
        unlock = max((item for item in entry["triggers"] if item["kind"] == "unlock"), key=lambda item: Decimal(item["score"]))
        ended = fmt_date(date.fromisoformat(unlock["ends_on"]))
        age = f"{unlock['days_since']} days ago" if unlock.get("days_since") else "today"
        split = ("all of it is free to sell" if unlock.get("value_known")
                 else "how much of it unlocked is not printed, so they are ranked by the whole holding")
        holding = f"shares worth {entry['holding_display']}" if entry["holding_display"] else "shares of undisclosed value"
        line = f"{label}: a lock-in ended on {ended} ({age}); holds {holding}; {split}."
        if any(item["kind"] == "proceeds" for item in entry["triggers"]) and entry["amount_display"]:
            line += f" Also sold in the offer: {entry['amount_display']}; {entry['timing_display']}."
        return line
    if label == "Cash received earlier":
        amount = entry["amount_display"] if entry["amount_known"] else "amount not disclosed"
        return (f"{label}: {amount}; {entry['timing_display']}. "
                "Listed after this month's cash and fresh unlocks.")
    if entry["holding_display"]:
        return f"{label} worth {entry['holding_display']}; no cash from this event yet."
    return f"{label}: {entry['why_money']}; no cash from this event confirmed yet, and the value is not disclosed."


def _reasons(entry: dict, ordered: list[dict], position: int, entity: bool, context: bool = False) -> list[str]:
    """Short strings that say why this entry sits where it does. The first is the plain-English one."""
    reasons: list[str] = [why_rank(entry)]
    if entity:
        reasons.append("entity: listed separately, an RM does not call a fund or company directly")
    if context:
        reasons.append("no money from this event: listed for context, not to call")
    best = entry["trigger"]
    if best:
        money = best.get("rank_value_crore") or best["money_crore"]
        split = f" × {UNKNOWN_SPLIT_WEIGHT[0]} (unlocked share not printed)" if best.get("rank_value_crore") else ""
        reasons.append(
            f"score {_short(entry['score'])} = ₹{money} crore ({best['label']}){split} × "
            f"{entry['confidence_weight']} ({entry['confidence']} confidence) × "
            f"{best['timing_weight']} (timing {best['timing_status']}) × {best['recency_weight']} (recency)"
        )
        for other in entry["triggers"]:
            if other is not best:
                reasons.append(f"other trigger: {other['label']}, score {_short(other['score'])}")
    else:
        reasons.append(
            f"later score {_short(entry['later_score'])} = retained ₹{entry['later_value_crore']} crore × "
            f"{entry['confidence_weight']} ({entry['confidence']} confidence) × "
            f"{entry['timing_weight']} (timing {entry['timing_status']})"
        )
    if position < len(ordered):
        below = ordered[position]
        if _sort_key(below)[:4] == _sort_key(entry)[:4]:
            reasons.append(f"tied with {below['name_as_printed']}; name order breaks the tie")
    if entry["family_group"]:
        reasons.append(f"family link ({entry['family_group']['id']}): {entry['family_group']['reason']}")
    return reasons


def _short(value: str) -> str:
    """A score to two decimals for reading. The stored score keeps every digit."""
    return f"{Decimal(value).quantize(Decimal('0.01'))}"
