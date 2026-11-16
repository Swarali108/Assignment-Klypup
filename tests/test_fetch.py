"""Fetch cache. httpx is mocked, so this makes no network call."""

from __future__ import annotations

import hashlib

import httpx

from tools.fetch import fetch


def test_second_fetch_returns_the_cached_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    calls = {"n": 0}

    def fake_get(url, timeout, headers, follow_redirects):
        calls["n"] += 1
        assert headers == {"User-Agent": "Money-event-RM-call-list/0.1 (educational; public filings)"}
        assert timeout == 30.0
        assert "Cookie" not in headers
        return httpx.Response(
            200,
            content=b"filing-bytes",
            headers={"content-type": "text/plain"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    first_path, first_meta = fetch("https://example.test/filing")
    second_path, second_meta = fetch("https://example.test/filing")

    assert calls["n"] == 1
    assert first_path == second_path
    assert first_path.read_bytes() == b"filing-bytes"
    assert first_path.name.endswith(".bin")
    digest = hashlib.sha256(b"filing-bytes").hexdigest()
    assert first_meta["sha256"] == digest
    assert second_meta["sha256"] == digest
    assert second_meta["url"] == "https://example.test/filing"
    assert second_meta["status"] == 200
    assert second_meta["content_type"] == "text/plain"
    assert second_meta["fetched_at"].endswith("Z")
