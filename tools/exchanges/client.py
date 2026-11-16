"""The one polite way this app reads NSE and BSE (guardrails in config/exchanges.py).

    client = ExchangeClient()
    text = client.get_text(url, max_age_days)    # cached via tools/fetch.py

- At least MIN_GAP_S between two network requests to the same host (cached reads do not wait).
- Before the first request to a host, its HOSTS home page is visited once, as a browser would,
  so the session holds the site's ordinary cookies. Nothing else is added to the cookie jar.
- Headers: the honest USER_AGENT, Accept, Accept-Language and the site's own Referer. Nothing more.
- A 401, 403 or 429 (on the home page or any request) latches that host as blocked for the rest
  of this client's life: no further request is sent to it and every call raises FetchError with
  the original status. No retry, no other headers, no proxy.
"""

from __future__ import annotations

import time
from typing import Callable
from urllib.parse import urlparse

import httpx

from config.exchanges import (ACCEPT_HTML, ACCEPT_JSON, ACCEPT_LANGUAGE, BLOCK_CODES, HOSTS, MIN_GAP_S, TIMEOUT_S,
                              USER_AGENT)
from tools.fetch import FetchError, fetch


def host_of(url: str) -> str:
    """The lower-cased host name of url."""
    return (urlparse(url).hostname or "").lower()


class ExchangeClient:
    """A cookie session with a per-host gap, a one-time home-page visit and a blocked-host latch."""

    def __init__(self, transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, min_gap_s: float = MIN_GAP_S):
        self.session = httpx.Client(transport=transport, timeout=TIMEOUT_S, follow_redirects=True,
                                    max_redirects=5, headers={"User-Agent": USER_AGENT,
                                                              "Accept-Language": ACCEPT_LANGUAGE})
        self.sleep, self.clock, self.min_gap_s = sleep, clock, min_gap_s
        self.last_request: dict[str, float] = {}
        self.visited_home: set[str] = set()
        self.blocked: dict[str, FetchError] = {}
        self.requests = 0

    def get_text(self, url: str, max_age_days: float) -> str:
        """The body of url as text: from the cache when fresh, else one polite request."""
        path, _meta = fetch(url, max_age_days=max_age_days, downloader=self.download)
        return path.read_bytes().decode("utf-8", errors="replace")

    def download(self, url: str) -> httpx.Response:
        """One GET of url after the host's home-page visit; raises FetchError on a block or an error."""
        host = host_of(url)
        self._raise_if_blocked(host)
        home = (HOSTS.get(host) or {}).get("home")
        if home and home != url and host_of(home) not in self.visited_home:
            self._visit_home(home, host)
        accept = ACCEPT_HTML if url == home else ACCEPT_JSON
        referer = (HOSTS.get(host) or {}).get("referer")
        headers = {"Accept": accept, **({"Referer": referer} if referer and url != home else {})}
        response = self._get(url, headers)
        self._check(url, host, response)
        return response

    def _visit_home(self, home: str, for_host: str) -> None:
        """Load the site's home page once, like a browser; a block there blocks the host asking for it."""
        home_host = host_of(home)
        self._raise_if_blocked(home_host)
        self.visited_home.add(home_host)
        response = self._get(home, {"Accept": ACCEPT_HTML})
        try:
            self._check(home, home_host, response)
        except FetchError as exc:
            self.blocked.setdefault(for_host, exc)
            raise

    def _get(self, url: str, headers: dict) -> httpx.Response:
        """GET after waiting out the host's gap. Transport errors become FetchError(status None)."""
        host = host_of(url)
        last = self.last_request.get(host)
        if last is not None:
            wait = self.min_gap_s - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        try:
            return self.session.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise FetchError(url, None, f"Download failed for {url}. {exc}") from exc
        finally:
            self.last_request[host] = self.clock()
            self.requests += 1

    def _check(self, url: str, host: str, response: httpx.Response) -> None:
        """Latch the host on 401/403/429; raise FetchError on any other 4xx/5xx."""
        status = response.status_code
        if status in BLOCK_CODES:
            error = FetchError(url, status, f"HTTP {status} from {host}. Stopped reading {host} for this run "
                                            "(no retry, no other headers).")
            self.blocked[host] = error
            raise error
        if status >= 400:
            raise FetchError(url, status, f"HTTP {status} for {url}.")

    def _raise_if_blocked(self, host: str) -> None:
        """Raise the latched error when host was blocked earlier in this run."""
        if host in self.blocked:
            earlier = self.blocked[host]
            raise FetchError(earlier.url, earlier.status, str(earlier))
