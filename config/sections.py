"""Section keywords for Indian offer documents and buyback letters.

Terms are phrases a filing uses as headings or table labels. Weights are
relative: a longer official phrase outranks a short form of the same idea.
No company, person, or event is named here.
"""

from __future__ import annotations

# Added once when a matched term sits in the first HEADING_LINES non-empty lines.
HEADING_BONUS = 3
# Added once when a matched term sits on a line with at least this many numbers.
TABLE_BONUS = 2
HEADING_LINES = 5
TABLE_MIN_NUMBERS = 3
# Added once per phrase below that appears on the page. These are column headers.
STRUCTURE_BONUS = 4

# section -> ((term, weight), ...). Order is the order locate() returns.
SECTIONS: dict[str, tuple[tuple[str, int], ...]] = {
    "selling_shareholders": (
        # The offer-for-sale seller table is usually titled this way.
        ("details of selling shareholders", 4),
        ("selling shareholders", 3),
        ("selling shareholder", 3),
    ),
    "offer_structure": (
        # Distinguishes new shares from shares sold by existing holders.
        ("fresh issue of equity shares", 4),
        ("offer for sale of equity shares", 4),
        ("fresh issue", 3),
        ("offer for sale", 3),
    ),
    "waca": (
        # The acquisition-cost table in an offer document.
        ("weighted average cost of acquisition", 5),
        ("weighted average cost", 2),
    ),
    "promoter_holding": (
        # How many shares the promoters hold, and the contribution block.
        ("promoters' contribution", 4),
        ("shareholding of our promoters", 3),
        ("shareholding of the promoters", 3),
        ("promoter holding", 3),
    ),
    "shareholding_pattern": (
        # The category-wise holder table, not the promoter-only block.
        ("shareholding pattern", 4),
        ("statement of the shareholding", 3),
        ("category of shareholder", 2),
        # The issuer's own table outranks a subsidiary's. Each subsidiary write-up in an offer
        # document has a "Capital structure and shareholding pattern" sub-heading; a negative
        # weight (no heading or table bonus) pushes those pages down.
        ("shareholding pattern of our company", 8),
        ("capital structure and shareholding pattern", -8),
    ),
    "kmp": (
        # The management section and two roles that section names.
        ("key managerial personnel", 4),
        ("key managerial", 2),
        ("whole-time director", 2),
        ("chief financial officer", 2),
    ),
    "esop": (
        # Employee option schemes. "esop" is matched on a word boundary.
        ("employee stock option", 4),
        ("employee stock options", 3),
        ("stock option scheme", 3),
        ("esop", 2),
    ),
    "lock_in": (
        # Shares that cannot be sold until a stated period ends.
        ("lock-in", 3),
        ("lock in period", 3),
        ("locked-in", 3),
    ),
    "price": (
        # The rupee price the document actually states.
        ("price band", 4),
        ("buyback price", 4),
        ("offer price", 3),
        ("floor price", 3),
        ("cap price", 3),
    ),
    "buyback_entitlement": (
        # Whether promoters tender, and how much of the buyback is accepted.
        ("intention to participate", 4),
        ("promoters intend to participate", 4),
        ("acceptance ratio", 4),
        ("buyback entitlement", 4),
    ),
    "buyback_terms": (
        # The price, size and dates of a tender-offer buyback. A letter of offer
        # prints these on its cover and in its schedule of activities.
        ("schedule of activities", 4),
        ("buyback price", 4),
        ("buyback opening date", 4),
        ("buyback closing date", 4),
        ("record date", 2),
        ("payment of consideration", 3),
        # The entitlement ("N for every M held") is printed on the cover, apart from the schedule.
        ("buyback entitlement", 4),
        ("ratio of buyback", 4),
    ),
    "timetable": (
        # The indicative timetable an IPO offer document prints: bid dates, credit of
        # shares, and the scheduled start of trading (the listing date).
        ("commencement of trading of the equity shares", 4),
        ("indicative timetable", 3),
        ("credit of equity shares to demat accounts", 3),
        ("bid/offer closing date", 2),
        ("initiation of refunds", 2),
    ),
    "promoter_intention": (
        # The promoters' holdings and whether they will tender: a disclosure every
        # tender-offer letter of offer makes.
        ("intention of the promoters", 5),
        ("intention to participate", 4),
        ("intention not to participate", 4),
        ("shareholding of the promoter", 4),
        ("members of the promoter group", 2),
    ),
}

# Column headers for each section. They show up in that section's table and
# rarely as a sentence. No company, person, or event is named here.
# One hit adds STRUCTURE_BONUS, however many times the header is repeated.
STRUCTURE: dict[str, tuple[str, ...]] = {
    "selling_shareholders": (
        "number of equity shares offered",
        "date of consent letter",
        "date of corporate authorisation",
        "name of the selling shareholder",
    ),
    "offer_structure": (
        "size of the fresh issue",
        "size of the offer for sale",
    ),
    "waca": (
        "number of equity shares acquired",
        "acquisition price per equity share",
        "nature of consideration",
    ),
    "promoter_holding": (
        "minimum promoters' contribution",
        "amount contributed by the promoters",
    ),
    "shareholding_pattern": (
        "number of fully paid up equity shares held",
        "shares held in dematerialised form",
    ),
    "kmp": (
        "remuneration paid",
        "date of appointment",
    ),
    "esop": (
        "number of options granted",
        "exercise price per option",
        "options outstanding",
    ),
    "lock_in": (
        "equity shares locked-in",
        "expiry of lock-in",
    ),
    "price": (
        "discount to the floor price",
    ),
    "buyback_entitlement": (
        "equity shares proposed to be bought back",
        "reservation for small shareholders",
    ),
    "buyback_terms": (
        "buyback opening date",
        "buyback closing date",
        "last date for payment of consideration",
    ),
    "timetable": (
        "bid/offer opening date",
        "bid/offer closing date",
        "commencement of trading",
    ),
    "promoter_intention": (
        "name of the shareholder",
        "number of equity shares",
        "maximum number of equity shares",
    ),
}


# Optional: a section's pages must contain one of these phrases. choose_pages then
# keeps only locate's hits, or a hit's next page, that contain a phrase, plus each
# such page's next page. With no match it falls back to the top pages and says so in
# extract.json. A phrase's words must appear in order, case ignored; a few other
# words may sit between them (PHRASE_MAX_GAP_WORDS, PHRASE_MAX_EXTRA_WORDS), because
# a column heading's text is often interleaved with a neighbouring column's.
PHRASE_MAX_GAP_WORDS = 4
PHRASE_MAX_EXTRA_WORDS = 6
MUST_CONTAIN: dict[str, tuple[str, ...]] = {
    # ICDR offer documents introduce the per-holder cost table with this wording.
    # A "weighted average price of acquisition" table for shares bought in the last
    # year is a different table and must not be the one sent.
    "waca": ("average cost of acquisition per equity share",),
}

