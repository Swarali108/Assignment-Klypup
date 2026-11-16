"""Map an event type to its rules module. config/event_types.py names the module.

Each rules module provides the same functions:
  context(extracted, as_of)        offer-level facts the figures use
  summary(context)                 top-level keys for people.json
  apply(person, members, context)  set seller_status, amounts and timing on a person
  why_money(person), amount_display(person), timing_display(person)   words for the call list
  timing_display_status(person)    the status of the timing timing_display shows (the app's pill)
rules_structured (block_deal, insider_sale) builds people itself from exchange records, so it has
no context/summary/apply; it provides the four call-list word functions above.
"""

from __future__ import annotations

from types import ModuleType

from agents import rules_buyback, rules_ipo, rules_ofs, rules_structured
from config.event_types import event_config

_MODULES: dict[str, ModuleType] = {"ipo": rules_ipo, "buyback": rules_buyback, "ofs": rules_ofs,
                                 "structured": rules_structured}


def rules_for(event_type: str) -> ModuleType:
    """The rules module for this event type."""
    name = event_config(event_type)["rules"]
    return _MODULES[name]
