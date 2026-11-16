"""Which ruled-table column a holder number may come from: header words per field.

Used by agents/verify.py after a value has passed the text checks. The check only
ever removes a value, never adds one, and it decides only when it is sure:

- the cited page has a ruled table with a row whose name cell is this holder;
- in that row, the cells printing this value hold no other number;
- every one of those cells sits under a header that names another field
  (words below) and none of them names this field.

Anything else (no table, a header with no words from this list, a header naming
both fields, a cell that also prints a face value or an amount) leaves the text
check's result as it was. Headers are matched lowercased with spaces collapsed.

Example from a buyback letter of offer: "Maximum No. of Equity Shares intended to
be offered" names shares_intended, so a promoter's pre-offer holding copied from
that column is rejected as "wrong column".
"""

# A field's own words. A header containing any of them names that field.
COLUMN_WORDS: dict[str, tuple[str, ...]] = {
    "shares_offered": ("offered", "offer for sale", "sold"),
    "shares_held_pre_offer": ("held", "holding", "pre-offer", "pre offer", "pre-issue", "pre issue"),
    "shares_intended": ("intended",),
    "shares_accepted": ("accepted",),
    "waca_per_share": ("average cost", "cost of acquisition", "average price"),
}

# Header words that name a column which is no holder field we read, so a value
# under them is never one of the fields above.
OTHER_COLUMN_WORDS: tuple[str, ...] = ("post-offer", "post offer", "post-issue", "post issue")

# Fields the column check applies to. Printed rupee amounts are left out: their
# cells usually print shares and rupees together, so a header cannot settle them.
COLUMN_FIELDS: tuple[str, ...] = tuple(COLUMN_WORDS)

# A row whose first printed cell starts with this word is a total, not a holder.
TOTAL_WORD = "total"
