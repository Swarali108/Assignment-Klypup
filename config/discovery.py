"""Rules that turn a discovered item into a class, and classes into event documents.

Title rules are tried in order on the lower-cased title; the first rule whose words
all match (any of each group) and whose "none" words are absent wins. A rule with no
class gives "other" with that rule's label. Items no rule settles go to one cheap
model call (tools/discover.py), whose answer must be one of CLASSES or "other".
"""

from __future__ import annotations

# class -> the event it belongs to and the document type it adds (agents/spec.py DOC_TYPES).
CLASSES = {
    "ipo_rhp": {"event_type": "ipo", "doc_type": "rhp", "label": "IPO red herring prospectus"},
    "ipo_prospectus": {"event_type": "ipo", "doc_type": "prospectus", "label": "IPO prospectus"},
    "basis_of_allotment": {"event_type": "ipo", "doc_type": "announcement", "label": "Basis of allotment"},
    "listing_notice": {"event_type": "ipo", "doc_type": "announcement", "label": "Listing notice"},
    "price_band_ad": {"event_type": "ipo", "doc_type": "announcement", "label": "Price band"},
    "buyback_letter_of_offer": {"event_type": "buyback", "doc_type": "letter_of_offer",
                                "label": "Buyback letter of offer"},
    "buyback_public_announcement": {"event_type": "buyback", "doc_type": "public_announcement",
                                    "label": "Buyback public announcement"},
    "ofs_notice": {"event_type": "ofs_stock_exchange", "doc_type": "announcement",
                   "label": "Offer for sale notice"},
}

# The document an event cannot be processed without, per event type.
MAIN_DOCUMENT = {"ipo": ("prospectus", "rhp"), "buyback": ("letter_of_offer",), "ofs_stock_exchange": ("announcement",)}
# Until the main document arrives, an event may be processed from another document when
# `run.py --step check` finds every listed section in it. A buyback public announcement
# prints the price and size (buyback_terms) and the promoters' holdings and intention
# (promoter_intention); the letter of offer supersedes it when it arrives.
STAND_IN_DOCUMENT = {
    "buyback": {"doc_type": "public_announcement", "from_class": "buyback_public_announcement",
                "needs_sections": ("buyback_terms", "promoter_intention")},
}

# (class or None, label for "other", all_of: tuple of any-of groups, none_of)
TITLE_RULES = (
    ("price_band_ad", "", (("price band",),), ()),
    ("basis_of_allotment", "", (("basis of allotment",),), ()),
    (None, "delisting", (("delisting",),), ()),
    ("listing_notice", "", (("listing",), ("trading", "commencement")), ()),
    (None, "draft offer document", (("draft", "drhp", "udrhp"),), ()),
    (None, "abridged prospectus", (("abridged",),), ()),
    (None, "addendum to offer document", (("addendum", "corrigendum"),), ()),
    ("ipo_rhp", "", (("rhp", "red herring"),), ()),
    ("ipo_prospectus", "", (("prospectus",),), ()),
    ("buyback_letter_of_offer", "", (("buyback", "buy-back", "buy back"), ("letter of offer",)), ("draft",)),
    ("buyback_public_announcement", "", (("buyback", "buy-back", "buy back"), ("public announcement",)), ()),
    ("ofs_notice", "", (("offer for sale",), ("stock exchange", "notice")), ()),
    (None, "takeover open offer", (("open offer", "takeover", "substantial acquisition"),), ()),
    (None, "block deal", (("block deal", "bulk deal"),), ()),
    (None, "merger or scheme", (("merger", "amalgamation", "scheme of arrangement", "demerger"),), ()),
    (None, "dividend", (("dividend",),), ()),
    (None, "rights issue", (("rights issue",),), ()),
    (None, "regulator's circular or order", (("circular", "adjudication", "settlement order", "final order"),), ()),
)

# Words in a document's file name (split on anything not a letter or digit), for pages
# that list several files: the first matching rule names the file's class.
FILE_RULES = (
    (None, "draft letter of offer", ("dlof",)),
    ("buyback_letter_of_offer", "", ("lof",)),
    ("buyback_public_announcement", "", ("pa",)),
)

# Items of one company and one event type belong to one event when they are this close.
GROUP_WINDOW_DAYS = 60
# Words of a company name kept in an event id.
EVENT_ID_WORDS = 6
# The cheap model is asked about at most this many unsettled items per refresh.
MAX_MODEL_ITEMS = 20
CLASSIFY_PROMPT_VERSION = "v1"

# A document's own first pages say what it is. Tried in order on the lower-cased text of the
# first FIRST_PAGES pages; the first rule whose words all match (any of each group) wins.
# (doc_type or None for "not supported", event_type, label, all_of groups, none_of)
FIRST_PAGES = 3
FIRST_PAGE_RULES = (
    (None, None, "draft offer document", (("draft red herring", "draft letter of offer", "draft prospectus"),), ()),
    (None, None, "abridged prospectus", (("abridged prospectus",),), ()),
    ("announcement", "ipo", "addendum or price band advertisement", (("addendum", "corrigendum"),), ()),
    # SEBI requires this disclaimer on IPO advertisements (price band, basis of allotment).
    ("announcement", "ipo", "IPO public announcement",
     (("public announcement for information purposes only",), ("not a prospectus",)), ()),
    ("letter_of_offer", "buyback", "buyback letter of offer", (("letter of offer",), ("buyback", "buy-back", "buy back")), ()),
    ("public_announcement", "buyback", "buyback public announcement",
     (("public announcement",), ("buyback", "buy-back", "buy back")), ()),
    ("announcement", "ofs_stock_exchange", "offer for sale through the stock exchange",
     (("floor price", "stock exchange mechanism"), ("offer for sale",)), ()),
    ("announcement", "ipo", "basis of allotment", (("basis of allotment",),), ("red herring prospectus",)),
    ("rhp", "ipo", "red herring prospectus", (("red herring prospectus",),), ()),
    ("prospectus", "ipo", "prospectus", (("prospectus",),), ("abridged",)),
)
# Where a first page names its company: "<NAME> LIMITED" just before (the "Company") or
# "OUR COMPANY", else the first "<NAME> LIMITED" on the page. Code reads these, not a model.
COMPANY_SUFFIXES = ("limited", "ltd")
