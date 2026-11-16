"""Where event discovery may look, and why each source is on or off.

A source is enabled only when its owner's published terms allow automated reading
and its robots.txt does not disallow the page. Disabled sources stay listed with the
sentence from their terms that rules them out, so the app can say why they are off.
Checked on 2026-11-15:

- SEBI (sebi.gov.in): robots.txt disallows only script and style folders. The website
  policy says "We do not object to you linking directly to the information that is
  hosted on this Website and no prior permission is required for the same." Discovery
  stores titles, dates and links and points to SEBI; it does not republish documents.
- NSE (nseindia.com, which redirects to its own nseindia.in): the Terms of Use forbid
  automated collection (quoted below), so its RSS feeds are not read.
- BSE (bseindia.com): its disclaimer forbids reproduction or redistribution (quoted
  below), so its RSS feeds are not read.

Owner ruling 2026-11-16: NSE and BSE are read anyway, by tools/exchanges, under the guardrails in
config/exchanges.py and only while EXCHANGE_SOURCES is on (EXCHANGE_SOURCES below). Each entry
keeps its terms link and says it is against the site's terms (owner's call).
"""

from __future__ import annotations

SEBI_LISTING = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3"
SEBI_TERMS = "https://www.sebi.gov.in/website-policy.html"
SEBI_REASON = ("SEBI website policy: linking needs no permission; robots.txt allows the page. "
               "Titles, dates and links only.")

# kind: "sebi_list" (an HTML filings table) or "rss".
# default_class: the class for an item whose title carries no document words
#   ("by_documents": decide from the document file names on the item's page).
# details: fetch each in-window item's page for its document links.
SOURCES = (
    {"id": "sebi_rhp", "name": "SEBI · Red herring documents filed with ROC", "kind": "sebi_list",
     "url": SEBI_LISTING + "&ssid=15&smid=11", "enabled": True, "default_class": None, "details": True,
     "terms_url": SEBI_TERMS, "reason": SEBI_REASON},
    {"id": "sebi_prospectus", "name": "SEBI · Final offer documents filed with ROC", "kind": "sebi_list",
     "url": SEBI_LISTING + "&ssid=15&smid=12", "enabled": True, "default_class": None, "details": True,
     "terms_url": SEBI_TERMS, "reason": SEBI_REASON},
    {"id": "sebi_buyback_tender", "name": "SEBI · Buybacks: tender offers", "kind": "sebi_list",
     "url": SEBI_LISTING + "&ssid=22&smid=17", "enabled": True, "default_class": "by_documents", "details": True,
     "terms_url": SEBI_TERMS, "reason": SEBI_REASON},
    {"id": "sebi_takeover_lof", "name": "SEBI · Takeovers: letters of offer", "kind": "sebi_list",
     "url": SEBI_LISTING + "&ssid=20&smid=15", "enabled": True, "default_class": "other:takeover open offer",
     "details": False, "terms_url": SEBI_TERMS, "reason": SEBI_REASON},
    {"id": "sebi_rss", "name": "SEBI · RSS", "kind": "rss", "url": "https://www.sebi.gov.in/sebirss.xml",
     "enabled": True, "default_class": None, "details": False, "terms_url": SEBI_TERMS, "reason": SEBI_REASON},
    {"id": "nse_rss", "name": "NSE · RSS feeds (announcements, offer documents, buybacks)", "kind": "rss",
     "url": "https://www.nseindia.com/rss-feed", "enabled": False, "default_class": None, "details": False,
     "terms_url": "https://www.nseindia.in/nse-terms-of-use",
     "reason": ("Off by NSE's Terms of Use: \"User is prohibited to conduct any systematic or automated data "
                "collection activities (including scraping, data mining, data extraction and data harvesting) "
                "on or in relation to our Website\".")},
    {"id": "bse_rss", "name": "BSE · RSS feeds (announcements, notices, corporate actions)", "kind": "rss",
     "url": "https://www.bseindia.com/rss-feed.html", "enabled": False, "default_class": None, "details": False,
     "terms_url": "https://www.bseindia.com/rgess/disclaimer.htm",
     "reason": ("Off by BSE's disclaimer: \"Any reproduction, redistribution or transmission, for consideration "
                "or otherwise, of any such information contained in the Website is strictly prohibited\".")},
)

# Seconds between two network requests to the same owner (cached reads do not wait).
POLITE_DELAY_S = 3.0
# A listing page is read again when its cached copy is older than this (about 2.4 hours).
LIST_MAX_AGE_DAYS = 0.1
# An item's own page rarely changes once published.
DETAIL_MAX_AGE_DAYS = 30

# ---------- NSE and BSE (owner ruling 2026-11-16; docs/superpowers/specs/2026-11-16-signals-v2-design.md) ----------
# Read by tools/exchanges (not by the SEBI/RSS loop above), only while EXCHANGE_SOURCES is on
# (config/exchanges.exchange_sources_on, default on). "reader" names the function in
# tools/exchanges/<exchange>.py; "records" names the outputs/signals/<file>.json it fills.
NSE_TERMS = "https://www.nseindia.in/nse-terms-of-use"
BSE_TERMS = "https://www.bseindia.com/rgess/disclaimer.htm"
_NSE_RULING = ("Against the site's terms — owner's call. NSE's Terms of Use: \"User is prohibited to conduct any "
               "systematic or automated data collection activities (including scraping, data mining, data extraction "
               "and data harvesting) on or in relation to our Website\". Read anyway by the owner's ruling, politely "
               "(2 s gap, cached, honest User-Agent, no workaround when blocked).")
_BSE_RULING = ("Against the site's terms — owner's call. BSE's disclaimer: \"Any reproduction, redistribution or "
               "transmission, for consideration or otherwise, of any such information contained in the Website is "
               "strictly prohibited\". Read anyway by the owner's ruling, politely (2 s gap, cached, honest "
               "User-Agent, no workaround when blocked).")
EXCHANGE_RISK = "against the site's terms (owner's call)"


def _exchange_source(source_id: str, exchange: str, name: str, url: str, reader: str, records: str | None) -> dict:
    """One NSE/BSE source entry; enabled here, gated at run time by EXCHANGE_SOURCES."""
    nse = exchange == "NSE"
    return {"id": source_id, "name": name, "exchange": exchange, "kind": "exchange", "url": url, "enabled": True,
            "reader": reader, "records": records, "terms_url": NSE_TERMS if nse else BSE_TERMS,
            "reason": _NSE_RULING if nse else _BSE_RULING, "risk": EXCHANGE_RISK, "switch": "EXCHANGE_SOURCES"}


EXCHANGE_SOURCES = (
    _exchange_source("nse_announcements", "NSE", "NSE · Corporate announcements (OFS, allotment, listing, buyback, "
                     "acquisition)", "https://www.nseindia.in/companies-listing/corporate-filings-announcements",
                     "read_announcements", None),
    _exchange_source("nse_ipo", "NSE", "NSE · IPOs (current, upcoming, recently listed)",
                     "https://www.nseindia.in/market-data/all-upcoming-issues-ipo", "read_ipo", None),
    _exchange_source("nse_bulk_deals", "NSE", "NSE · Bulk deals",
                     "https://www.nseindia.in/report-detail/display-bulk-and-block-deals", "read_bulk", "deals"),
    _exchange_source("nse_block_deals", "NSE", "NSE · Block deals",
                     "https://www.nseindia.in/report-detail/display-bulk-and-block-deals", "read_block", "deals"),
    _exchange_source("nse_deals_archive", "NSE", "NSE · Bulk and block deal files, latest day (archive host)",
                     "https://www.nseindia.in/all-reports", "read_archive", "deals"),
    _exchange_source("nse_insider", "NSE", "NSE · Insider trading (PIT) disclosures",
                     "https://www.nseindia.in/companies-listing/corporate-filings-insider-trading", "read_insider",
                     "insider"),
    _exchange_source("bse_announcements", "BSE", "BSE · Corporate announcements (OFS, listing, buyback, open offer, "
                     "acquisition)", "https://www.bseindia.com/corporates/ann.html", "read_announcements", None),
    _exchange_source("bse_ipo", "BSE", "BSE · Public issues (IPO, OFS, buyback, open offer)",
                     "https://www.bseindia.com/publicissue.html", "read_issues", None),
    _exchange_source("bse_bulk_deals", "BSE", "BSE · Bulk deals",
                     "https://www.bseindia.com/markets/equity/EQReports/bulk_deals.aspx", "read_bulk", "deals"),
    _exchange_source("bse_block_deals", "BSE", "BSE · Block deals",
                     "https://www.bseindia.com/markets/equity/EQReports/block_deals.aspx", "read_block", "deals"),
    _exchange_source("bse_insider", "BSE", "BSE · Insider trading (PIT) disclosures",
                     "https://www.bseindia.com/corporates/Insider_Trading_new.aspx", "read_insider", "insider"),
)
