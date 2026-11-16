"""Weights and tiers for the call list. score = money × confidence weight × timing weight × recency weight.

Each weight has a one-line reason. Change a number here, not in agents/rank.py.
"""

from __future__ import annotations

from decimal import Decimal

# Holder types an RM can call. Entities (funds, companies, trusts) go in a separate list.
CALLABLE_TYPES = {
    "person": "an individual: the RM can call them directly",
    "family_vehicle": "an HUF or family trust: the RM calls the family that runs it",
    "unsure": "the type is unsure, so it stays callable and flagged rather than hidden",
}

CONFIDENCE_WEIGHTS = {
    "high": (Decimal("1.0"), "name and holdings checked in more than one table"),
    "medium": (Decimal("0.7"), "verified, but in fewer tables; worth a call, less sure of size"),
    "low": (Decimal("0.4"), "identity or type unsure; check before calling"),
}

TIMING_WEIGHTS = {
    "at_listing": (Decimal("1.0"), "money reaches them at listing: the reason to call now"),
    "in_hand": (Decimal("1.0"), "money is already with them"),
    "locked_in": (Decimal("0.3"), "shares are locked in, so cash is months away"),
    # Unknown sits at or below every known weight, so losing a date can never raise a score.
    "unknown": (Decimal("0.25"), "timing not verified: ranked below every known timing"),
    "not_applicable": (Decimal("0.25"), "no timing applies: treated like unknown"),
    "none": (Decimal("0.25"), "nothing retained: treated like unknown"),
    "unlocked": (Decimal("1.0"), "every lock-in period has ended: the shares can be sold"),
    "partly_unlocked": (Decimal("0.6"), "some shares are free to sell, the rest are still locked"),
    "settles": (Decimal("1.0"), "cash is paid on a printed date: as good as in hand"),
    "after_date": (Decimal("0.8"), "cash follows a printed date, but no payment date is printed"),
    # Same weight as after_date: the date is printed, but only as a plan. No listing
    # notice confirms that trading started, so it is less sure than at_listing or in_hand.
    "scheduled": (Decimal("0.8"), "listing date is the offer document's timetable, not confirmed by a listing notice"),
    # A timetable listing date that has passed: the shares have most likely listed and paid out.
    "listed_per_timetable": (Decimal("0.9"), "the timetable listing date has passed; no listing notice read yet"),
}

# How old the trigger is, in days, as (upper bound, weight, reason). The first band that fits wins.
RECENCY_WEIGHTS = (
    (30, Decimal("1.0"), "0 to 30 days: the money is new and the holder is deciding what to do"),
    (90, Decimal("0.6"), "31 to 90 days: some of it may already be placed"),
    (None, Decimal("0.3"), "over 90 days: the trigger is old news"),
)

# Recency for a trigger that has not happened yet or has no date: no discount, because the
# money is still to come. An unknown date is discounted by its timing weight ("unknown" 0.25),
# which sits below every known timing, so losing a date never raises a score.
UNDATED_RECENCY = (Decimal("1.0"), "not happened yet or date unknown: no recency discount")

# A lock-in that ended this many days ago or less is a fresh trigger.
FRESH_UNLOCK_DAYS = 90
FRESH_UNLOCK_WEIGHT = (Decimal("0.5"), "unlocked shares are not cash; the holder may keep them")
# When the document does not print how much of a holding a lock-in covered, the unlock is
# ranked on the whole holding at half weight: the unlocked part lies between none and all.
UNKNOWN_SPLIT_WEIGHT = (Decimal("0.5"), "share of the holding that unlocked is not printed: half the holding")

# Dashboard counts. They only select from ranked.json; no score changes.
# "New signal": the money event behind this person's rank happened at most this many days
# ago. Same cut-off as a fresh unlock and as the briefs' "recent", so the three agree.
NEW_SIGNAL_DAYS = FRESH_UNLOCK_DAYS
# "High priority": high confidence, and the money is in hand, paid at listing, or due on a
# printed timetable date. These are the calls with cash now or on a known date, about a
# holder whose facts agree across the documents.
HIGH_PRIORITY_CONFIDENCE = ("high",)
HIGH_PRIORITY_TIMING = ("in_hand", "at_listing", "scheduled")

# Call tiers, in call order. A tier beats any score in a lower tier; within a tier a
# known amount comes before an unknown one, then score, then the retained value, then name.
CALL_TIERS = ("cash_now", "unlock", "holding")
CALL_TIER_REASONS = {
    "cash_now": "they receive cash from this event: the strongest reason to call",
    "unlock": "shares unlocked in the last few months: free to sell, but not cash yet",
    "holding": "holds shares and gets no new cash from this event (or got it more than CASH_NOW_DAYS ago)",
}
# Cash counts as "cash now" when it arrived at most this many days ago, or is still to come.
# Older cash goes to the holding tier ("Cash received earlier"): a fresh unlock is the newer reason to call.
CASH_NOW_DAYS = 30
# Proceeds timing statuses where the cash has already reached the holder.
CASH_IN_HAND_STATUSES = ("in_hand", "listed_per_timetable")
# Words that mark a fund or company when the holder type is "unsure". Applied at rank
# time only, so the person's stored holder type does not change. Whole tokens, lower case.
FUND_LIKE_TOKENS = (
    "venture", "partners", "capital", "lp", "inc", "pte", "mauritius", "opportunities",
    "advisors", "advisers", "equity", "asset", "assets", "management", "investment", "fii", "fpi",
    "gmbh", "plc", "bv", "corp", "growth", "master", "offshore",
)

# Words that mark an organisation even when the stored holder type says "person": a legal form, a fund word,
# or a country/place at the end of the name ("<Fund> Singapore"). Used by the RM views to keep an organisation
# out of the call list. Whole tokens, lower case. Not names of any company or person.
ORG_STRONG_TOKENS = (
    "llp", "lp", "fund", "funds", "ltd", "limited", "pte", "inc", "gmbh", "plc", "bv", "corp", "ventures",
    "partners", "capital", "holdings", "investments", "investment", "fii", "fpi", "mauritius",
)
ORG_PLACE_TOKENS = (
    "india", "singapore", "mauritius", "cayman", "luxembourg", "ireland", "bvi", "uk", "usa", "hk", "hongkong",
    "netherlands", "jersey", "guernsey", "dubai", "uae", "japan", "europe", "asia", "global", "international",
)
