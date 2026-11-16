"""What each event type locates, extracts, computes and times. No company is named here.

For each event_type:
  locate_sections   sections locate() scores on ranked documents (terms in config/sections.py).
  ranked_sections   section -> extraction schema, for sections read from locate's top pages.
                    One model call each, in this order.
  whole_document    doc_types read whole (first max_pages pages), with section -> schema.
                    One call per section per such document.
  merge_fields      holder fields merged across sections (the schema's own fields).
  offer_fields      offer-level fields merged across sections.
  person_fields     fields copied from the merged row onto each person.
  role_priority     sections whose printed role becomes the primary role, first match wins.
  seller_section    the section whose verified name makes someone a seller.
  seller_label      how reasons name that section.
  holding_field     the field that should agree across sections, or None.
  rules             module in agents/ with the amount and timing rules (rules_<name>.py).
  prompt_rules      which system-rule set agents/extract.py sends.
  rule_sources      True when timing rules must be found in the event's own pages (lock-in).
  completeness      section -> share field to sum against the printed total (and an offer-size field).
  structured        True for events built from exchange records (no document, no model for facts):
                    run.py skips fetch/locate/extract and agents/rules_structured.py builds the people.
  record_kinds      structured only: the record "kind" values this event type accepts.
"""

from __future__ import annotations

_IPO_HOLDER_FIELDS = (
    "name_as_printed", "role_as_printed", "shares_offered", "shares_held_pre_offer", "waca_per_share", "qualifier",
    "amount_as_printed",
)
_BUYBACK_HOLDER_FIELDS = (
    "name_as_printed", "role_as_printed", "shares_held_pre_offer", "shares_intended", "qualifier", "intention_as_printed",
)
_OFS_HOLDER_FIELDS = ("name_as_printed", "role_as_printed", "shares_offered", "greenshoe_shares", "qualifier")

EVENT_TYPES: dict[str, dict] = {
    "ipo": {
        "locate_sections": (
            "selling_shareholders", "offer_structure", "waca", "promoter_holding", "shareholding_pattern",
            "kmp", "esop", "lock_in", "price", "buyback_entitlement", "timetable",
        ),
        "ranked_sections": {
            "selling_shareholders": "SectionHolders",
            # What the document prints each seller's offered shares come to, from the seller pages.
            "seller_amounts": "SectionHolders",
            "waca": "SectionHolders",
            "promoter_holding": "SectionHolders",
            "shareholding_pattern": "SectionHolders",
            "offer_structure": "OfferFacts",
            "price": "OfferFacts",
            # The scheduled listing date. An announcement's verified listing date wins over it.
            "timetable": "TimetableFacts",
        },
        "whole_document": {
            "doc_types": ("announcement",),
            "max_pages": 4,
            "sections": {"announcement": "AnnouncementFacts", "allotment": "AllotmentFacts"},
        },
        "merge_fields": _IPO_HOLDER_FIELDS,
        # A section that reads the pages another section located, instead of its own.
        "pages_from": {"seller_amounts": "selling_shareholders"},
        "offer_fields": (
            "fresh_issue_size", "ofs_size", "price_band_low", "price_band_high", "offer_price", "face_value",
            "listing_date", "allotment_date", "listing_date_scheduled",
        ),
        "person_fields": ("shares_offered", "qualifier", "shares_held_pre_offer", "waca_per_share", "amount_as_printed"),
        "role_priority": ("selling_shareholders", "promoter_holding", "shareholding_pattern"),
        "seller_section": "selling_shareholders",
        "seller_label": "the seller table",
        "holding_field": "shares_held_pre_offer",
        "rules": "ipo",
        "prompt_rules": "ipo",
        # Look for config/lock_in.py's anchor phrases in this event's pages.
        "rule_sources": True,
        # Sum each holder table and compare it with its printed total (agents/completeness.py).
        "completeness": {"selling_shareholders": {"share_field": "shares_offered", "offer_size_field": "ofs_size"}},
    },
    "buyback": {
        "locate_sections": ("buyback_terms", "promoter_intention"),
        "ranked_sections": {
            "promoter_intention": "IntentionHolders",
            "buyback_terms": "BuybackTerms",
        },
        # A results announcement may print shares accepted per holder or an acceptance ratio.
        "whole_document": {
            "doc_types": ("announcement",),
            "max_pages": 6,
            "sections": {"buyback_results": "ResultHolders", "buyback_acceptance": "AcceptanceFacts"},
        },
        "merge_fields": _BUYBACK_HOLDER_FIELDS + ("shares_accepted",),
        "offer_fields": (
            "buyback_price", "maximum_shares", "record_date", "opening_date", "closing_date", "payment_date",
            "acceptance_ratio", "entitlement_ratio",
        ),
        "person_fields": ("shares_held_pre_offer", "shares_intended", "qualifier", "intention_as_printed", "shares_accepted"),
        "role_priority": ("promoter_intention",),
        "seller_section": "promoter_intention",
        "seller_label": "the promoter intention disclosure",
        "holding_field": "shares_held_pre_offer",
        "completeness": {"promoter_intention": {"share_field": "shares_held_pre_offer",
                                                "other_share_fields": ("shares_intended",)}},
        "rules": "buyback",
        "prompt_rules": "general",
    },
    "ofs_stock_exchange": {
        "locate_sections": (),
        "ranked_sections": {},
        # The notice is short and is read whole, like an announcement.
        "whole_document": {
            "doc_types": ("announcement",),
            "max_pages": 20,
            "sections": {"ofs_sellers": "OfsSellerHolders", "ofs_terms": "OfsTerms"},
        },
        "merge_fields": _OFS_HOLDER_FIELDS,
        "offer_fields": (
            "floor_price", "total_shares_offered", "greenshoe_total", "sale_date", "sale_date_retail",
            "settlement_as_printed",
        ),
        "person_fields": ("shares_offered", "greenshoe_shares", "qualifier"),
        "role_priority": ("ofs_sellers",),
        "seller_section": "ofs_sellers",
        "seller_label": "the seller list in the notice",
        "holding_field": None,
        "rules": "ofs",
        "prompt_rules": "general",
    },
}


# A structured event reads no document: every document-pipeline key is empty, so code that loops over
# them does nothing. People come from exchange records (agents/rules_structured.py), with the record as evidence.
_STRUCTURED_BASE = {
    "structured": True,
    "locate_sections": (),
    "ranked_sections": {},
    "whole_document": {"doc_types": (), "max_pages": 0, "sections": {}},
    "merge_fields": (),
    "offer_fields": (),
    "person_fields": ("shares_offered",),
    "role_priority": (),
    "seller_section": "exchange_record",
    "holding_field": None,
    "rules": "structured",
    "prompt_rules": "general",
}
EVENT_TYPES["block_deal"] = {
    **_STRUCTURED_BASE,
    # A bulk deal is reported like a block deal (client, side, quantity, price) and becomes the same event type;
    # the record's own kind picks the words ("in a bulk deal" / "in a block deal").
    "record_kinds": ("block_deal", "bulk_deal"),
    "seller_label": "the exchange deal report",
}
EVENT_TYPES["insider_sale"] = {
    **_STRUCTURED_BASE,
    "record_kinds": ("insider_sale",),
    "seller_label": "the exchange insider-trading disclosure",
}

# Equity cash-market settlement used for timing: trade date + this many trading days. Weekends are skipped;
# exchange holidays are not checked, and the label says so wherever the date is shown.
SETTLEMENT_TRADING_DAYS = 1
SETTLEMENT_LABEL = "T+1 equity cash-market settlement; exchange holidays not checked"
# Insider-disclosure modes. A printed mode containing one of these stems (lower case, punctuation dropped) moves
# shares without a sale for cash: a gift, a pledge or its creation/release/invocation/revocation, an inheritance,
# an ESOP/ESOS allotment, a conversion or a scheme. Stems, so "Revoke"/"Revocation" and "Invoke"/"Invocation" match.
# The holder is listed for context, not as a seller.
INSIDER_NON_CASH_MODE_WORDS = (
    "gift", "pledge", "encumb", "invoc", "invok", "revoc", "revok", "releas", "transmis", "inherit", "bequest",
    "esop", "esos", "allot", "conver", "bonus", "amalgam", "merger", "scheme", "creation",
)
INSIDER_OFF_MARKET_MODE_WORDS = ("off market", "inter se", "interse", "private")


def event_config(event_type: str) -> dict:
    """The config for one event type. An unknown type is an error, not a silent IPO."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"No config for event_type {event_type!r}. Known: {sorted(EVENT_TYPES)}.")
    return EVENT_TYPES[event_type]
