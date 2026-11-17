"""NSE and BSE: the public endpoints their own web pages call, and the rules that read them.

Every URL here was seen in the network requests of the exchange's own page, opened in a browser
on 2026-11-15 (the page each comes from is in PAGES). Nothing names a company or a person.

Guardrails (owner ruling, docs/superpowers/specs/2026-11-16-signals-v2-design.md): at least
MIN_GAP_S between two requests to one host, every response cached (tools/fetch.py), an honest
User-Agent naming the app, the site's home page visited first for ordinary session cookies, no
proxies, no IP rotation, no CAPTCHA solving, no header tricks; a 401/403/429 stops that host for
the rest of the run and its sources show "blocked".
"""

from __future__ import annotations

import os

# The switch: EXCHANGE_SOURCES=on|off (default on).
SWITCH_ENV = "EXCHANGE_SOURCES"

# Honest: names the app and says what it does. The "Mozilla/5.0 (compatible; ...)" form is the
# usual way a non-browser client identifies itself; it claims no browser.
USER_AGENT = "Mozilla/5.0 (compatible; FinSight/0.2; money-event research; reads public exchange filings)"
# What a browser's ordinary request also sends. No sec-* or client-hint headers.
ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
ACCEPT_JSON = "application/json, text/plain, */*"
ACCEPT_LANGUAGE = "en-US,en;q=0.9"
MIN_GAP_S = 2.0
TIMEOUT_S = 30.0
BLOCK_CODES = (401, 403, 429)

# host -> the home page a browser would load first (None: a file host a browser opens directly)
# and the Referer its own pages send.
HOSTS = {
    "www.nseindia.in": {"home": "https://www.nseindia.in/", "referer": "https://www.nseindia.in/"},
    "nsearchives.nseindia.in": {"home": None, "referer": None},
    "api.bseindia.com": {"home": "https://www.bseindia.com/", "referer": "https://www.bseindia.com/"},
    "www.bseindia.com": {"home": "https://www.bseindia.com/", "referer": "https://www.bseindia.com/"},
}

# Lists for a past day do not change; today's list is read again after this many days.
TODAY_MAX_AGE_DAYS = 0.1
PAST_DAY_MAX_AGE_DAYS = 30
# One insider filing's XBRL file never changes.
FILE_MAX_AGE_DAYS = 365
# At most this many insider XBRL files are downloaded in one run (each is one request); the rest wait.
MAX_XBRL_PER_RUN = 60
# BSE pages its announcement lists 50 rows at a time.
BSE_PAGE_ROWS = 50
MAX_BSE_PAGES = 10
# The longest window read in one run, whatever since_days asks for.
MAX_DAYS = 31

NSE = "https://www.nseindia.in"
NSE_ARCHIVES = "https://nsearchives.nseindia.in"
BSE = "https://www.bseindia.com"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"

# The human page each endpoint belongs to (a record's link when the data itself is an API answer).
PAGES = {
    "nse_announcements": f"{NSE}/companies-listing/corporate-filings-announcements",
    "nse_ipo": f"{NSE}/market-data/all-upcoming-issues-ipo",
    "nse_deals": f"{NSE}/report-detail/display-bulk-and-block-deals",
    "nse_insider": f"{NSE}/companies-listing/corporate-filings-insider-trading",
    "nse_reports": f"{NSE}/all-reports",
    "bse_announcements": f"{BSE}/corporates/ann.html",
    "bse_bulk": f"{BSE}/markets/equity/EQReports/bulk_deals.aspx",
    "bse_block": f"{BSE}/markets/equity/EQReports/block_deals.aspx",
    "bse_insider": f"{BSE}/corporates/Insider_Trading_new.aspx",
    "bse_issues": f"{BSE}/publicissue.html",
}

# Endpoint templates. NSE dates are DD-MM-YYYY, BSE dates YYYYMMDD.
NSE_ANNOUNCEMENTS = NSE + "/api/corporate-announcements?index=equities&from_date={start}&to_date={end}"
NSE_IPO_CURRENT = NSE + "/api/ipo-current-issue"
NSE_IPO_UPCOMING = NSE + "/api/all-upcoming-issues?category=ipo"
NSE_IPO_PAST = NSE + "/api/public-past-issues"
NSE_DEALS = NSE + "/api/historicalOR/bulk-block-short-deals?optionType={option}&from={start}&to={end}"
NSE_INSIDER = NSE + "/api/corporates-pit-gg?index=equities&from_date={start}&to_date={end}"
# NSE's deals API answered at most this many rows per query on 2026-11-15 (13 Nov: 70 rows from the API,
# 136 in the archive file). A query that returns exactly this many is reported as possibly cut.
NSE_DEALS_ROW_CAP = 70
# The latest trading day's files, linked from NSE's "All Reports" page.
NSE_BULK_CSV = NSE_ARCHIVES + "/content/equities/bulk.csv"
NSE_BLOCK_CSV = NSE_ARCHIVES + "/content/equities/block.csv"
BSE_ANNOUNCEMENTS = (BSE_API + "/AnnSubCategoryGetData/w?pageno={page}&strCat={category}&strPrevDate={start}"
                     "&strScrip=&strSearch=P&strToDate={end}&strType=C&subcategory={subcategory}")
BSE_BULK = BSE_API + "/BulkDeal_Beta/w"
BSE_BLOCK = BSE_API + "/BlockDeal_Beta/w"
BSE_INSIDER = BSE_API + "/getCorp_Regulation_ng/w?scripCode=&Regulation=&fromDT={start}&ToDate={end}&Isdefault=0"
BSE_ISSUES = BSE_API + "/GetPublicIssue_par_updated/w?flag=1"
# BSE's own page links an attachment as AttachLive when PDFFLAG is 0, AttachHis otherwise (both checked live
# 2026-11-15: a PDFFLAG 0 file under AttachLive, a PDFFLAG 1 file under AttachHis).
BSE_ATTACHMENT = BSE + "/xml-data/corpfiling/{folder}/{name}"

# BSE announcement queries: (category, subcategory or "-1" for all). Only the subcategories that
# can carry a money event are asked for, so a day costs a few requests, not forty.
BSE_QUERIES = (
    ("New Listing", "-1"),
    ("Company Update", "Offer for Sale"),
    ("Company Update", "Buy back"),
    ("Company Update", "Public Announcement-Buyback of Shares"),
    ("Company Update", "Post Buyback Public Announcement"),
    ("Company Update", "Closure of Buy Back"),
    ("Company Update", "Open Offer"),
    ("Company Update", "Public Announcement-Open Offer"),
    ("Company Update", "Acquisition"),
)

# Classes this module adds next to config/discovery.CLASSES (discover's own classes are reused
# where they fit: basis_of_allotment, listing_notice, ofs_notice, buyback_public_announcement).
EXCHANGE_CLASSES = {
    "ipo_issue": {"event_type": "ipo", "doc_type": "announcement", "label": "IPO on the exchange's issue list"},
    "buyback_announcement": {"event_type": "buyback", "doc_type": "announcement",
                             "label": "Buyback announcement"},
    "acquisition": {"event_type": "acquisition", "doc_type": "announcement",
                    "label": "Acquisition or open offer"},
}

# Announcement subject (NSE "desc", BSE "SUBCATNAME"/"CATEGORYNAME") -> class. Tried in order on the
# lower-cased subject; the first rule whose words all match (any of each group), with none of its
# "none" words, wins. A subject no rule matches is not a money event and is not kept.
SUBJECT_RULES = (
    ("basis_of_allotment", (("basis of allotment",),), ()),
    ("listing_notice", (("new listing", "listing of equity", "listing of securities", "listing and trading",
                         "commencement of trading"),), ("delisting",)),
    ("ofs_notice", (("offer for sale",),), ()),
    ("buyback_public_announcement", (("buyback", "buy back", "buy-back"), ("public announcement",)),
     ("post buyback", "post buy back", "post-buyback")),
    ("buyback_announcement", (("buyback", "buy back", "buy-back"),), ()),
    ("acquisition", (("open offer", "takeover", "acquisition"),), ("allotment",)),
)

# When the subject says nothing, the announcement's own one-line text may (same rule form).
TEXT_RULES = (
    ("basis_of_allotment", (("basis of allotment",),), ()),
    ("ofs_notice", (("offer for sale",), ("stock exchange mechanism",)), ()),
)

# Insider "category of person" as printed -> the shared record category.
CATEGORY_WORDS = (
    ("promoter_group", ("promoter group", "promoters immediate relative", "promoter's immediate relative")),
    ("promoter", ("promoter",)),
    ("director", ("director",)),
    ("kmp", ("kmp", "key managerial")),
)
# A printed mode of disposal that pays the seller no cash; such "sales" are not kept as insider_sale
# (matched on the lower-cased mode).
NON_CASH_MODES = ("gift", "inter-se", "inter se", "pledge", "invocation", "revocation", "transmission")
# The only host an insider XBRL link (taken from NSE's answer) may point to.
NSE_XBRL_HOST = "nsearchives.nseindia.in"
# Printed transaction type -> side. Anything else (pledge, revoke, invocation) is not a trade.
SELL_WORDS = ("sell", "sale", "disposal")
BUY_WORDS = ("buy", "purchase", "acquisition")


def exchange_sources_on() -> bool:
    """True unless EXCHANGE_SOURCES is off (also false/0/no). Read at call time, not import time."""
    return os.environ.get(SWITCH_ENV, "on").strip().lower() not in ("off", "false", "0", "no")
