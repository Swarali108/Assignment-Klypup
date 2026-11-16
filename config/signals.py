"""Signals v2: the extra classes, the SEBI draft-offer watchlist, exchange labels, and the
scheduler / auto-processing defaults. No company is named here.

Exchange connectors (tools/exchanges, NSE and BSE) tag their items with the classes below.
config/discovery.py keeps the SEBI classes; tools/discover.py reads both (CLASSES wins on a
name clash). Items in WATCH_CLASSES are listed in the feed but never become events: an
"IPO coming" is a draft offer document (nothing is sold yet), an "acquisition watch" is a
takeover or Reg 30 acquisition notice this app does not read yet.
"""

from __future__ import annotations

from config.sources import SEBI_LISTING, SEBI_REASON, SEBI_TERMS

# class -> the event it belongs to and the document type it adds (agents/spec.py DOC_TYPES).
# event_type None: listed only. doc_type None: the item carries no document the pipeline reads.
EXTRA_CLASSES = {
    "ipo_allotment": {"event_type": "ipo", "doc_type": "announcement", "label": "IPO basis of allotment"},
    "ipo_listing": {"event_type": "ipo", "doc_type": "announcement", "label": "IPO listing notice"},
    "buyback_announcement": {"event_type": "buyback", "doc_type": "announcement", "label": "Buyback notice"},
    "acquisition": {"event_type": None, "doc_type": None, "label": "Acquisition watch"},
    "ipo_coming": {"event_type": None, "doc_type": None, "label": "IPO coming (draft filed)"},
}
WATCH_CLASSES = ("ipo_coming", "acquisition")
# The feed's one-line reason for a watchlist item.
WATCH_REASONS = {
    "ipo_coming": "Draft offer filed with SEBI; nothing is sold yet, so no one to call yet",
    "acquisition": "Acquisition or open offer notice; listed, not processed yet",
}

# Structured signals: one feed item per structured event (agents/rules_structured.group_records).
STRUCTURED_LABELS = {"block_deal": "Block deal", "bulk_deal": "Bulk deal", "insider_sale": "Insider sale"}
SIGNALS_DIR = "outputs/signals"

# SEBI's own list of draft offer documents: an early warning that an IPO is coming.
# The title rule for "draft" would call these "other"; force_class makes them watchlist items.
WATCH_SOURCES = (
    {"id": "sebi_drhp", "name": "SEBI · Draft offer documents filed with SEBI", "kind": "sebi_list",
     "url": SEBI_LISTING + "&ssid=15&smid=10", "enabled": True, "default_class": None, "force_class": "ipo_coming",
     "details": False, "terms_url": SEBI_TERMS, "reason": SEBI_REASON},
)

# Who owns a source id, for the badge on each feed item and the Sources page.
SOURCE_OWNERS = (("sebi", "SEBI"), ("nse", "NSE"), ("bse", "BSE"))

# Risk labels shown on the Sources page. NSE and BSE are read on the owner's ruling although
# their terms forbid automated collection (decision_log.md, row 15).
RISK = {
    "SEBI": {"level": "low", "label": "Low risk: SEBI's website policy allows linking; titles, dates and links only"},
    "NSE": {"level": "high", "label": "High risk: NSE's terms forbid automated collection; read on the owner's call"},
    "BSE": {"level": "high", "label": "High risk: BSE's terms forbid reproduction; read on the owner's call"},
}
EXCHANGE_TERMS = {
    "NSE": "https://www.nseindia.in/nse-terms-of-use",
    "BSE": "https://www.bseindia.com/rgess/disclaimer.htm",
}

# Scheduler and auto-processing defaults (each can be overridden by the env var of the same name).
DISCOVERY_EVERY_HOURS = 3.0
DISCOVERY_SINCE_DAYS = 30.0
AUTO_PROCESS_DAILY_CAP_USD = 1.00
# The day the cap resets on. cost_log.csv timestamps are UTC; they are converted to this zone.
CAP_TIMEZONE = "Asia/Kolkata"
# Seconds a check-now confirm token stays valid.
CONFIRM_TTL_S = 300
# The longest the scheduler waits after the API starts before its first check (when one is due).
FIRST_CHECK_DELAY_S = 60
