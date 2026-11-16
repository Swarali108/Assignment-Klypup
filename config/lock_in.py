"""When money from an IPO reaches a holder: lock-in rules and the proceeds-at-listing rule.

No document is named here. Each rule period carries anchor phrases. At run time
agents/rule_sources.py looks for them in this event's own pages (the lock_in
pages locate found first, then every page) and cites the page where all of a
period's anchors appear together. A period whose anchors are not found makes the
timing that needs it "unknown: lock-in rule not found in this event's documents".

The periods restate SEBI ICDR Regulations 14, 16 and 17 as offer documents
print them. TODO (check before the call): the SEBI sources in docs/sources.md
(S19 board memo, S21 Taxguru) were seen only as search excerpts. Read the ICDR
regulation text itself and confirm these periods have not changed.

Anchors are matched case-insensitively, with any run of spaces, hyphens or
punctuation between words, so "locked-in" matches "locked in". A number matches
its digits or its word, with an optional repeat in brackets, so "18 months" also
matches "eighteen months" and "six months" matches "6 (six) months"; "offer" also
matches "issue", so "pre-offer" matches "pre – Issue". An anchor written as a
tuple of phrases is found when any one of them is on the page. A rule's own
periods are tried first; each entry in its optional "variants" carries other
wording and its own periods (for example SME offer documents), and the first set
whose anchors are all found is used.

A rule applies when its role words appear in the printed role and none of its
excluded words do. A role that no rule fits gives timing "unknown".
"""

from __future__ import annotations

LOCK_IN_RULES: tuple[dict, ...] = (
    {
        "id": "minimum_promoters_contribution",
        "role_words": ("promoter",),
        "exclude_words": ("promoter group",),
        "period": (
            "18 months from the date of Allotment for the shares that form the Minimum "
            "Promoters' Contribution (20% of fully diluted post-Offer capital); six months "
            "from the date of Allotment for promoter shares above that 20%"
        ),
        "split_note": "Which of this promoter's shares fall in the 20% is not extracted.",
        # Each period runs from the date of Allotment. "share_of_retained" says whether
        # the number of shares in that period is known: "all" or "unknown".
        "periods": (
            {
                "label": "Minimum Promoters' Contribution",
                "months": 18,
                "share_of_retained": "unknown",
                "anchors": (
                    ("aggregate of 20%", "minimum promoters' contribution", "minimum promoter's contribution", "promoters' contribution"),
                    "locked in for a period of 18 months",
                ),
            },
            {
                "label": "promoter shares above the 20%",
                "months": 6,
                "share_of_retained": "unknown",
                "anchors": (
                    (
                        "in excess of 20%",
                        "in excess of minimum promoters' contribution",
                        "in excess of the minimum promoters' contribution",
                        "in excess of minimum promoter's contribution",
                        "in excess of the minimum promoter's contribution",
                        "in excess of promoters' contribution",
                        "in excess of the promoters' contribution",
                    ),
                    "locked in for a period of six months",
                ),
            },
        ),
        # SME offer documents (ICDR Chapter IX, Regulations 236 and 238) print other periods.
        # TODO (check before relying on these): confirm in the SEBI ICDR Regulations text
        # that Regulation 238 still sets these periods; they are copied as the documents print them.
        "variants": (
            {
                "id": "sme",
                "period": (
                    "three years from the date of allotment for the shares that form the Minimum "
                    "Promoters' Contribution; for promoter shares above it, fifty percent for two years "
                    "and the remaining fifty percent for one year from the date of allotment"
                ),
                "split_note": "Which of this promoter's shares fall in each part is not extracted.",
                "periods": (
                    {
                        "label": "Minimum Promoters' Contribution",
                        "months": 36,
                        "share_of_retained": "unknown",
                        "anchors": ("minimum promoters' contribution", "locked in for a period of three years from the date of allotment"),
                    },
                    {
                        "label": "fifty percent of promoter shares above the minimum contribution",
                        "months": 24,
                        "share_of_retained": "unknown",
                        "anchors": ("in excess of minimum promoters' contribution", "locked in for a period of two years from the date of allotment"),
                    },
                    {
                        "label": "remaining fifty percent of promoter shares above the minimum contribution",
                        "months": 12,
                        "share_of_retained": "unknown",
                        "anchors": ("remaining fifty percent", "locked in for a period of one year from the date of allotment"),
                    },
                ),
            },
            {
                # Some main-board offer documents print three years and one year.
                # TODO (check before relying on these): copied as the documents print them.
                "id": "three_year",
                "period": (
                    "three years from the date of Allotment for the shares that form the Minimum "
                    "Promoters' Contribution (20% of post-Offer capital); one year from the date of "
                    "Allotment for promoter shares above that 20%"
                ),
                "split_note": "Which of this promoter's shares fall in the 20% is not extracted.",
                "periods": (
                    {
                        "label": "Minimum Promoters' Contribution",
                        "months": 36,
                        "share_of_retained": "unknown",
                        "anchors": ("aggregate of 20%", "locked in for a period of three years"),
                    },
                    {
                        "label": "promoter shares above the 20%",
                        "months": 12,
                        "share_of_retained": "unknown",
                        "anchors": ("in excess of 20%", "locked in for a period of one year"),
                    },
                ),
            },
        ),
    },
    {
        "id": "pre_offer_capital",
        "role_words": ("promoter group", "selling shareholder"),
        "exclude_words": (),
        "period": "six months from the date of Allotment",
        "split_note": (
            "Not locked: shares sold in the Offer for Sale; shares held by VCFs, Category I or II "
            "AIFs or FVCIs (subject to Regulation 17); shares employees hold under the ESOP "
            "schemes. Whether this holder falls in one of these is not checked."
        ),
        "periods": (
            {
                "label": "pre-Offer capital",
                "months": 6,
                "share_of_retained": "all",
                "anchors": (
                    ("entire pre-offer equity share capital", "entire pre-offer capital", "entire pre-offer paid-up equity share capital"),
                    "six months from the date of allotment",
                ),
            },
        ),
        # SME offer documents (ICDR Chapter IX, Regulation 239) print one year.
        # TODO (check before relying on this): confirm the period and its exceptions in the
        # SEBI ICDR Regulations text; the period is copied as the documents print it.
        "variants": (
            {
                "id": "sme",
                "period": "one year from the date of allotment",
                "split_note": (
                    "The exceptions to this lock-in in Regulation 239 are not checked for this holder. "
                    "TODO: read Regulation 239."
                ),
                "periods": (
                    {
                        "label": "pre-offer capital held by persons other than the promoters",
                        "months": 12,
                        "share_of_retained": "all",
                        "anchors": (
                            "entire pre-offer capital held by the persons other than the promoters",
                            "locked in for a period of one year from the date of allotment",
                        ),
                    },
                ),
            },
        ),
    },
)

# Offer-for-sale money. TODO: an offer document may not say on which day sellers
# are paid. All anchors must sit in ONE sentence: listing wording, and wording that
# says money is transferred or paid to the selling shareholders. A sentence about
# sellers reimbursing offer expenses "upon listing" does not say when they are paid,
# so the exclude words rule it out and the "(not stated ...)" qualifier stays.
# Check the Prospectus or the Offer Agreement before relying on "at listing".
OFS_PROCEEDS_RULE: dict = {
    "id": "ofs_proceeds_at_listing",
    "when": "at listing",
    "not_found": "at listing (not stated in this event's documents)",
    "todo": (
        "The offer document may not state the day sellers are paid. Check the Prospectus or "
        "Offer Agreement."
    ),
    "scope": "sentence",
    "anchors": (
        ("listing and trading", "listing approval", "listing approvals"),
        (
            "transferred to the selling shareholders",
            "transferred to the selling shareholder",
            "transferred to each of the selling shareholders",
            "paid to the selling shareholders",
            "paid to the selling shareholder",
            "remitted to the selling shareholders",
            "credited to the selling shareholders",
            "released to the selling shareholders",
        ),
    ),
    "exclude": ("reimburse", "expenses"),
}

NOT_FOUND = "lock-in rule not found in this event's documents"
