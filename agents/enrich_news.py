"""Web-search leads for a deep dive: Bright Data SERP API (Google) results as title, source, date, URL only.

No snippet, description, image or article text is kept. Every result carries the label
"from web search, not verified": a lead for the RM to open, never a fact in a person's record.

Bright Data (docs read 2026-11-15):
  POST https://api.brightdata.com/request {"zone": <SERP zone>, "url": "https://www.google.com/search?q=...&brd_json=1",
  "format": "raw"}; tbm=nws gives news. Parsed JSON has "organic" [{link, title, description, global_rank, ...}]
  and, for news, "news" [{title, link, source, date ("1 day ago"), image, rank, ...}].
  https://docs.brightdata.com/api-reference/serp/google-search/parsed-json
  https://docs.brightdata.com/api-reference/serp/google-search/news
  https://docs.brightdata.com/products/serp-api/fast-serp/web-search  (organic fields)
  The docs differ on brd_json=json vs brd_json=1; tools/brightdata.py sends 1 (the news page's own example).
  Not yet checked against a live response: the account had no SERP zone on 2026-11-15.
"""

from __future__ import annotations

from urllib.parse import urlparse

from agents.names import clean_name
from config import enrichment as cfg
from tools import brightdata as bd

SOURCE = "Bright Data SERP API (Google)"


def _domain(url: str) -> str | None:
    """www.example.com -> example.com."""
    host = urlparse(url).hostname or ""
    return host[4:] if host.startswith("www.") else (host or None)


def results_from_serp(raw: dict, news: bool) -> list[dict]:
    """title, source, date, url for each result in a parsed SERP answer. Only http(s) links; no text kept."""
    rows = []
    items = (raw or {}).get("news" if news else "organic") or []
    for item in items[: cfg.SEARCH_RESULTS]:
        if not isinstance(item, dict):
            continue
        url = item.get("link") or item.get("url")
        title = item.get("title")
        if not (isinstance(url, str) and url.startswith(("http://", "https://")) and isinstance(title, str)):
            continue
        source = item.get("source") if isinstance(item.get("source"), str) else _domain(url)
        date = item.get("date") if isinstance(item.get("date"), str) else None
        rows.append({"title": title.strip(), "source": source, "date": date, "url": url})
    return [{k: r.get(k) for k in cfg.SEARCH_FIELDS} for r in rows]


def estimate() -> dict:
    """A breakdown row for the chat estimate card (worst case, without 5xx retries)."""
    requests = cfg.worst_case_requests("search")
    return {"step": "Web search (Bright Data SERP)", "model": None, "calls": requests, "cost_usd": 0.0,
            "brightdata_requests": requests, "basis": "worst case as counted locally, without retries; free allowance"}


def _run(query: str, news: bool, client: bd.Client | None) -> list[dict]:
    """One cached SERP query -> labelled rows. A cached query costs 0 requests."""
    client = client or bd.Client()

    def fetch() -> dict:
        bd.ensure_budget(cfg.worst_case_requests("search"), client.cap)
        return client.google(query, news=news)

    rows, fetched_at, _ = bd.cached("serp", {"q": query, "news": news, "n": cfg.SEARCH_RESULTS},
                                    cfg.CACHE_DAYS["serp"], fetch, lambda raw: results_from_serp(raw, news))
    return [{**row, "label": cfg.SEARCH_LABEL, "query": query, "fetched_at": fetched_at, "via": SOURCE}
            for row in rows]


def search(name: str, company: str, client: bd.Client | None = None) -> list[dict]:
    """Web results for "<name> <company>" (honorific dropped, both quoted).

    Each row: title, source, date (as Google prints it, e.g. "3 days ago"), url, label, query, fetched_at, via.
    """
    person = " ".join(w.capitalize() for w in clean_name(name).split())
    return _run(f'"{person}" "{company}"', news=False, client=client)


def company_news(company: str, client: bd.Client | None = None) -> list[dict]:
    """Google News results for the company. Same row shape as search()."""
    return _run(f'"{company}"', news=True, client=client)
