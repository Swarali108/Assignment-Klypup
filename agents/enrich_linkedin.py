"""LinkedIn enrichment for one person already on a call list, through Bright Data's own LinkedIn products.

Owner ruling (2026-11-15): on by default (LINKEDIN_ENRICHMENT), against the assignment brief's "no LinkedIn" ground
rule, with these guardrails, all enforced here:
  - Only Bright Data's LinkedIn people datasets (config.enrichment.DATASET_*), never a scraper of ours.
  - Only public professional fields are kept: name, headline, positions (title, company, dates), education
    (school, years), city, profile URL, fetched_at. The output is built from an allow-list, then every kept string
    is scrubbed of email addresses and phone numbers. Raw responses are never written to disk.
  - Name-search candidates whose name does not carry the person's first and last name are dropped (they are other
    people, not on any call list).
  - Match level: "unconfirmed" for a name-only match; "likely" only when a position's company matches the filing's
    company or a related entity the caller names. The reason says which. City never upgrades a match, and the
    caller must never merge an unconfirmed profile into the person's facts.
  - One lookup is a paid step: estimate() gives the worst-case request count for the RM's confirm, and the client
    refuses before sending if the monthly cap could be crossed.

Bright Data (docs read 2026-11-15):
  Discover by name: dataset gd_m8d03he47z8nwb5xc, input {"url": "https://www.linkedin.com", "first_name",
    "last_name"}, async (trigger -> progress -> snapshot); output url, name, subtitle, location, experience,
    education, avatar. https://docs.brightdata.com/api-reference/scrapers/social-media-apis/linkedin-people-discover-new-profiles
  Collect by URL: dataset gd_l1viktl72bvl7bjuj0, input {"url"}, sync /scrape (202 + snapshot_id past 60 s).
    https://docs.brightdata.com/api-reference/scrapers/social-media-apis/linkedin-profiles-collect-by-url
  "Since November 13, 2025 ... Position, Experience and Education fields ... return cached data, with fill rates
    around 2 percent" (https://docs.brightdata.com/products/scrapers/linkedin/introduction), so positions are often
    empty and most matches stay "unconfirmed". That is the honest result, not a bug.
"""

from __future__ import annotations

import re
import unicodedata

from agents.names import name_tokens
from config import enrichment as cfg
from tools import brightdata as bd

SOURCE_DISCOVER = "Bright Data LinkedIn people search (by name)"
SOURCE_PROFILE = "Bright Data LinkedIn profile (by URL)"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# A run of digits with spaces, dots, dashes or brackets; it is a phone number only when it holds 10+ digits,
# so years ("2019 - 2023") and dates ("2019-01-01") survive.
_PHONE_RUN = re.compile(r"\+?\(?\d[\d\s().-]{6,}\d")
_PHONE_DIGITS = 10
_PROFILE_URL = re.compile(r"^https://([a-z]{2,3}\.)?(www\.)?linkedin\.com/in/[^/?#\s]+/?$", re.IGNORECASE)


class EnrichmentOff(Exception):
    """LINKEDIN_ENRICHMENT is off."""


# ---- scrubbing / allow-list ----------------------------------------------------------------------------------

def scrub_text(value) -> str | None:
    """A kept string with any email address or phone number removed. Non-strings and blanks become None."""
    if not isinstance(value, str):
        return None
    text = _PHONE_RUN.sub(lambda m: "" if sum(c.isdigit() for c in m.group(0)) >= _PHONE_DIGITS else m.group(0),
                          _EMAIL.sub("", value))
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;|-·")
    return text or None


def _year(value) -> str | None:
    """A 4-digit year from a date-ish value ("Jan 2019", "2019", 2019); else None."""
    found = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return found.group(0) if found else None


def _date(value) -> str | None:
    """A position date as printed ("Jan 2019", "Present"), scrubbed; else None."""
    return scrub_text(value) if isinstance(value, str) else (str(value) if isinstance(value, int) else None)


def _company_name(value) -> str | None:
    """Company from a string or an object with a name."""
    if isinstance(value, dict):
        value = value.get("name") or value.get("title")
    return scrub_text(value)


def _position(title, company, start, end) -> dict:
    """One position row. A "title" that only repeats the company (as in Bright Data's documented example) is
    not a job title, so it is dropped."""
    title, company = scrub_text(title), _company_name(company)
    if title and company and title.lower() == company.lower():
        title = None
    return {"title": title, "company": company, "start": _date(start), "end": _date(end)}


def public_positions(raw: dict) -> list[dict]:
    """Positions (title, company, start, end) from experience and current_company.

    experience is a list of {title, company, start_date, end_date} on a by-URL profile (a company entry may hold
    several roles under "positions"), and one string (usually the current company) on a name-search result.
    The by-URL field mapping is from the docs' example only; not yet checked against a live record.
    """
    out: list[dict] = []
    experience = raw.get("experience")
    if isinstance(experience, str):
        out.append(_position(None, experience, None, None))
    for item in experience if isinstance(experience, list) else []:
        if not isinstance(item, dict):
            continue
        roles = item.get("positions") if isinstance(item.get("positions"), list) else []
        for role in [r for r in roles if isinstance(r, dict)] or [item]:
            out.append(_position(role.get("title"), item.get("company"), role.get("start_date"), role.get("end_date")))
    current = _company_name(raw.get("current_company"))
    if current and not any((p["company"] or "").lower() == current.lower() for p in out):
        out.insert(0, _position(None, current, None, None))
    return [{k: p[k] for k in cfg.POSITION_FIELDS} for p in out if p["title"] or p["company"]]


def public_education(raw: dict) -> list[dict]:
    """Education (school, start_year, end_year). The name search returns it as one string."""
    items = raw.get("education")
    if isinstance(items, str):
        school = scrub_text(items)
        return [{"school": school, "start_year": None, "end_year": None}] if school else []
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        school = scrub_text(item.get("title") or item.get("school") or item.get("institute"))
        if school:
            out.append({"school": school, "start_year": _year(item.get("start_year") or item.get("start_date")),
                        "end_year": _year(item.get("end_year") or item.get("end_date"))})
    return [{k: e.get(k) for k in cfg.EDUCATION_FIELDS} for e in out]


def public_profile(raw: dict, fetched_at: str | None = None) -> dict:
    """The allow-listed public professional fields of one raw Bright Data record. Nothing else survives."""
    url = raw.get("url") or raw.get("input_url") or ""
    url = url if isinstance(url, str) and _PROFILE_URL.match(url.split("?")[0]) else None
    profile = {
        "name": scrub_text(raw.get("name")),
        "headline": scrub_text(raw.get("position") or raw.get("subtitle") or raw.get("headline")),
        "city": scrub_text(raw.get("city") or raw.get("location")),
        "positions": public_positions(raw),
        "education": public_education(raw),
        "profile_url": url.split("?")[0] if url else None,
        "fetched_at": fetched_at,
    }
    return {k: profile.get(k) for k in cfg.PROFILE_FIELDS}


# ---- matching ------------------------------------------------------------------------------------------------

def _fold(text: str) -> str:
    """Lower-case with accents removed."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def split_name(name: str) -> tuple[str, str]:
    """(first, last) from a printed name, with the honorific and footnote marks dropped."""
    words = name_tokens(name)
    tokens = [t for t in words if len(t) > 1 or len(words) <= 2]  # drop initials when there are 3+ words
    if len(tokens) < 2:
        raise ValueError(f"need a first and last name to search, got {name!r}")
    return tokens[0], tokens[-1]


def same_name(candidate: str | None, first: str, last: str) -> bool:
    """The candidate's name carries the first and last name as words (accent- and case-insensitive)."""
    words = set(re.findall(r"[a-z]+", _fold(candidate or "")))
    return _fold(first) in words and _fold(last) in words


def company_core(name: str | None) -> list[str]:
    """The identifying words of a company name: legal words like Limited / Pvt / India dropped."""
    return [t for t in (re.sub(r"[^a-z0-9&]", "", _fold(w)) for w in name_tokens(name or ""))
            if t and t not in cfg.COMPANY_GENERIC_TOKENS]


def companies_match(position_company: str | None, filing_company: str | None) -> bool:
    """Same identifying words, or one name's words all inside the other's with the same first word
    ("Acme" vs "Acme Mechatronics Limited"). The shorter side needs a word of 4+ letters."""
    left, right = company_core(position_company), company_core(filing_company)
    if not left or not right:
        return False
    if left == right:
        return True
    short, long_ = (left, right) if len(left) <= len(right) else (right, left)
    return short[0] == long_[0] and set(short) <= set(long_) and any(len(t) >= 4 for t in short)


def match_level(profile: dict, company: str, related: tuple[str, ...] | list[str] = ()) -> tuple[str, str]:
    """("likely" | "unconfirmed", reason). Only a position's company can make it likely."""
    targets = [company, *related]
    for position in profile.get("positions") or []:
        for target in targets:
            if companies_match(position.get("company"), target):
                which = "the filing's company" if target == company else f"a related entity ({target})"
                title = f" as {position['title']}" if position.get("title") else ""
                return "likely", f"Name matches and a position{title} at {position['company']} matches {which}."
    headline = _fold(profile.get("headline") or "")
    if any(core and all(w in headline for w in core) for core in (company_core(t) for t in targets)):
        return "unconfirmed", ("Name matches and the headline mentions the company, but no listed position "
                               "confirms it, so this stays unconfirmed.")
    if profile.get("positions"):
        return "unconfirmed", "Name matches, but none of the listed positions is at the filing's company."
    return "unconfirmed", ("Name matches only. Bright Data returned no positions for this profile, so the company "
                           "cannot be checked.")


# ---- public API ----------------------------------------------------------------------------------------------

def estimate(kind: str = "find_profiles") -> dict:
    """A breakdown row for the chat estimate card: worst-case Bright Data requests, $0 on the free tier."""
    requests = cfg.worst_case_requests(kind)
    label = {"find_profiles": "LinkedIn search by name (Bright Data)",
             "profile": "LinkedIn profile by URL (Bright Data)"}[kind]
    return {"step": label, "model": None, "calls": requests, "cost_usd": 0.0, "brightdata_requests": requests,
            "basis": "worst case as counted locally, without 5xx retries; free monthly allowance"}


def find_profiles(name: str, company: str, city: str | None = None, related: tuple[str, ...] | list[str] = (),
                  client: bd.Client | None = None) -> list[dict]:
    """LinkedIn candidates for one call-list person, each with match "likely" | "unconfirmed" and a reason.

    name: as printed in the filing (honorifics are dropped). company: the filing's company. related: other
    entities from the filing (group companies) that may also confirm a position. city: shown as context only.
    Each candidate: name, headline, city, positions, education, profile_url, fetched_at, match, reason, source.
    A cached search costs 0 requests.
    """
    if not cfg.linkedin_enabled():
        raise EnrichmentOff("LinkedIn enrichment is off (LINKEDIN_ENRICHMENT).")
    first, last = split_name(name)
    payload = {"dataset": cfg.DATASET_DISCOVER_BY_NAME, "first_name": first, "last_name": last,
               "limit": cfg.DISCOVER_LIMIT}
    client = client or bd.Client()

    def fetch() -> list[dict]:
        bd.ensure_budget(cfg.worst_case_requests("find_profiles"), client.cap)
        return client.collect("linkedin_discover", cfg.DATASET_DISCOVER_BY_NAME,
                              [{"url": "https://www.linkedin.com", "first_name": first, "last_name": last}],
                              body_extra={"limit_per_input": cfg.DISCOVER_LIMIT})

    def keep(raw: list[dict]) -> list[dict]:
        records = bd.drop_error_records(raw)[: cfg.DISCOVER_LIMIT]
        return [public_profile(r) for r in records if same_name(r.get("name"), first, last)]

    kept, fetched_at, _ = bd.cached("linkedin_discover", payload, cfg.CACHE_DAYS["linkedin_discover"], fetch, keep)
    out = []
    for profile in kept:
        profile = {**profile, "fetched_at": profile.get("fetched_at") or fetched_at}
        level, reason = match_level(profile, company, related)
        if city and profile.get("city") and _fold(city) in _fold(profile["city"]):
            reason += f" City ({profile['city']}) is consistent, which alone does not confirm identity."
        out.append({**{k: profile.get(k) for k in cfg.CANDIDATE_FIELDS}, "match": level, "reason": reason,
                    "source": SOURCE_DISCOVER})
    return sorted(out, key=lambda c: c["match"] != "likely")


def profile(url: str, company: str | None = None, related: tuple[str, ...] | list[str] = (),
            client: bd.Client | None = None) -> dict:
    """Public professional fields of one LinkedIn profile URL (contact-like fields stripped).

    Returns name, headline, city, positions, education, profile_url, fetched_at, source; plus match and reason
    when company is given. {} when Bright Data returns no record. A cached profile costs 0 requests.
    """
    if not cfg.linkedin_enabled():
        raise EnrichmentOff("LinkedIn enrichment is off (LINKEDIN_ENRICHMENT).")
    url = (url or "").strip().split("?")[0]
    if not _PROFILE_URL.match(url):
        raise ValueError(f"not a LinkedIn profile URL: {url!r}")
    client = client or bd.Client()

    def fetch() -> list[dict]:
        bd.ensure_budget(cfg.worst_case_requests("profile"), client.cap)
        return client.scrape("linkedin_profile", cfg.DATASET_PROFILE_BY_URL, [{"url": url}])

    def keep(raw: list[dict]) -> dict:
        records = bd.drop_error_records(raw)
        return public_profile(records[0]) if records else {}

    kept, fetched_at, _ = bd.cached("linkedin_profile", {"dataset": cfg.DATASET_PROFILE_BY_URL, "url": url},
                                    cfg.CACHE_DAYS["linkedin_profile"], fetch, keep)
    if not kept:
        return {}
    result = {**kept, "fetched_at": kept.get("fetched_at") or fetched_at, "source": SOURCE_PROFILE}
    if company:
        result["match"], result["reason"] = match_level(result, company, related)
    return result
