"""Settings for people enrichment through Bright Data (LinkedIn profile + web search). Limits, never facts.

Owner rulings (2026-11-15) this file encodes:
  - LINKEDIN_ENRICHMENT is on by default. It goes against the assignment brief's "no LinkedIn" ground
    rule; the owner chose it, with the guardrails below. Set LINKEDIN_ENRICHMENT=off to stop it.
  - Only Bright Data's own LinkedIn people-profile products are used (never a scraper of ours).
  - Only public professional fields are stored or shown (the allow-lists below). Contact-like
    fields are dropped before anything is written to disk.
  - Every Bright Data request is counted locally per calendar month; at BRIGHTDATA_REQUEST_CAP the
    client refuses. The free tier is 5,000 credits a month, so 4,500 leaves a margin.
  - Lookups run only for people already on a call list, one person at a time, after an RM confirms.

Bright Data facts used here (docs read 2026-11-15):
  https://docs.brightdata.com/products/scrapers/linkedin/introduction  (dataset ids, sync vs async,
      "Position, Experience and Education ... return cached data, with fill rates around 2 percent")
  https://docs.brightdata.com/api-reference/scrapers/social-media-apis/linkedin-profiles-collect-by-url
  https://docs.brightdata.com/api-reference/scrapers/social-media-apis/linkedin-people-discover-new-profiles
  https://docs.brightdata.com/general/account/billing-and-pricing/free-tier  (5,000 credits/month,
      one credit per request or record, reset on the 1st, hard stop when exhausted on an unfunded account)
"""

from __future__ import annotations

import os

# Bright Data dataset ids (LinkedIn scrapers library).
DATASET_PROFILE_BY_URL = "gd_l1viktl72bvl7bjuj0"
DATASET_DISCOVER_BY_NAME = "gd_m8d03he47z8nwb5xc"

DEFAULT_REQUEST_CAP = 4500
# Most name-search candidates asked for per lookup. Each delivered record is one credit.
DISCOVER_LIMIT = 5
# Async jobs (trigger -> progress -> snapshot): how often and how many times to ask for progress.
POLL_SECONDS = 10
MAX_POLLS = 18
# Search results kept per query.
SEARCH_RESULTS = 10
# Cached responses are reused for this long (a repeat lookup costs 0 requests).
CACHE_DAYS = {"linkedin_discover": 30, "linkedin_profile": 30, "serp": 7, "zones": 1}

# Public professional fields kept from a LinkedIn profile. Everything else is dropped.
PROFILE_FIELDS = ("name", "headline", "city", "positions", "education", "profile_url", "fetched_at")
POSITION_FIELDS = ("title", "company", "start", "end")
EDUCATION_FIELDS = ("school", "start_year", "end_year")
# Fields kept from a name-search candidate (before the match level is added).
CANDIDATE_FIELDS = ("name", "headline", "city", "positions", "education", "profile_url", "fetched_at")
# Fields kept from a search result. No snippet or article text.
SEARCH_FIELDS = ("title", "source", "date", "url")
SEARCH_LABEL = "from web search, not verified"

# Raw keys that are never read, whatever the allow-list says (documentation for tests and reviewers).
CONTACT_LIKE_KEYS = (
    "email", "emails", "phone", "phones", "phone_number", "mobile", "address", "street_address",
    "birthday", "birth_date", "date_of_birth", "avatar", "image", "photo", "banner_image",
    "default_avatar", "connections", "followers", "posts", "activity", "people_also_viewed",
    "similar_profiles", "recommendations", "about", "contact_info", "websites", "twitter",
)

# Words that do not identify a company ("Limited", "Pvt", ...). Used when matching a position's company.
COMPANY_GENERIC_TOKENS = frozenset({
    "limited", "ltd", "private", "pvt", "llp", "inc", "incorporated", "co", "company", "corporation",
    "corp", "plc", "the", "and", "of", "india", "group", "gmbh", "llc",
})


def request_cap() -> int:
    """BRIGHTDATA_REQUEST_CAP from the environment, else 4,500. A bad value falls back to the default."""
    raw = (os.environ.get("BRIGHTDATA_REQUEST_CAP") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_REQUEST_CAP
    return value if value >= 0 else DEFAULT_REQUEST_CAP


def linkedin_enabled() -> bool:
    """LINKEDIN_ENRICHMENT: on unless it is set to off / 0 / false / no."""
    raw = (os.environ.get("LINKEDIN_ENRICHMENT") or "on").strip().lower()
    return raw not in ("off", "0", "false", "no")


def worst_case_requests(kind: str) -> int:
    """Most requests one lookup can use, as the local counter counts them (each HTTP call + each record past
    the first in a response). Used for the RM estimate and to refuse a lookup that could cross the cap.

    find_profiles: trigger + MAX_POLLS progress checks + snapshot download, plus DISCOVER_LIMIT - 1 extra records.
    profile:       a sync scrape; if Bright Data answers 202 it becomes MAX_POLLS checks + a download.
    search:        one SERP request, plus one zone lookup when the zone list is not cached.
    """
    if kind == "find_profiles":
        return 1 + MAX_POLLS + 1 + (DISCOVER_LIMIT - 1)
    if kind == "profile":
        return 1 + MAX_POLLS + 1
    if kind == "search":
        return 2
    raise ValueError(f"unknown enrichment kind {kind!r}")
