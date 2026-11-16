"""Words that tell a person from an entity or a family vehicle. No names are listed here.

Tokens are compared after clean_name() and after dropping punctuation, so
"S.A.R.L." is "sarl" and "Pvt." is "pvt".
"""

from __future__ import annotations

HOLDER_TYPES = ("person", "entity", "family_vehicle", "unsure")

# A whole phrase that marks a family vehicle. Checked before the entity words,
# so "Family Trust" is a family vehicle and not just a trust.
FAMILY_VEHICLE_PHRASES = ("family trust",)
# A single token that marks a family vehicle.
FAMILY_VEHICLE_TOKENS = ("huf",)

# A single token that marks a company, fund, trust or other entity.
ENTITY_TOKENS = (
    "limited",
    "ltd",
    "llp",
    "llc",
    "fund",
    "trust",
    "society",
    "company",
    "pvt",
    "private",
    "sarl",
    "investments",
    "ventures",
    "series",
    "corporation",
    "bank",
    "foundation",
    "association",
    "holding",
    "holdings",
    "institute",
    # "X, Partner Representing Y Traders": the holder is the partnership firm.
    "partner",
)

# A person's name has this many tokens after the title is dropped. Outside the
# range, or with a digit, the name is "unsure".
PERSON_MIN_TOKENS = 2
PERSON_MAX_TOKENS = 4

# Exchange records (deal reports, insider disclosures) print counterparties in capitals, often without a legal
# form: brokers, arbitrage desks, insurers, foreign portfolio investors. A name holding one of these whole tokens
# is an entity even when the document rules above would call it a person. Applied to exchange records only
# (agents/rules_structured.py), so document events keep their tested rules. No company or person is named here.
EXCHANGE_ENTITY_TOKENS = (
    "securities", "security", "broking", "brokers", "broker", "stock", "stocks", "markets", "market",
    "financial", "finance", "finserv", "fincorp", "finvest", "capital", "investment", "investors", "investor",
    "advisors", "advisers", "advisory", "management", "managers", "asset", "assets", "mutual", "insurance",
    "assurance", "arbitrage", "trading", "traders", "research", "technologies", "technology", "enterprises",
    "industries", "international", "global", "corp", "inc", "pte", "plc", "gmbh",
    "odi", "fpi", "fii", "partners", "equity", "equities", "opportunities", "master", "offshore", "mauritius",
    "singapore", "cayman", "luxembourg", "ireland", "government", "governor", "president", "promoters",
    "infra", "infrastructure", "services", "solutions", "systems", "exports", "agencies", "commodities",
)
# Two-letter legal forms count only as the last word: as a first or middle word they are usually initials
# ("NV <surname>").
EXCHANGE_ENTITY_SUFFIX_TOKENS = ("sa", "ag", "nv", "bv", "lp")
