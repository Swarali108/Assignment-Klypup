"""Bright Data client + LinkedIn / web-search enrichment. No network, no key: httpx.MockTransport plays the API.

Fixtures: tests/fixtures/brightdata/live/ are this token's real answers on 2026-11-15 (the account could not run
scrapers yet); docs_examples/ are Bright Data's own documented response examples, labelled as such. Contact-like
fields are injected at test time, so the strip tests do not depend on what a fixture happens to hold.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agents import enrich_linkedin as el
from agents import enrich_news as en
from config import enrichment as cfg
from tools import brightdata as bd

FIXTURES = Path(__file__).parent / "fixtures" / "brightdata"
TOKEN = "test-token-never-real"
SENTINELS = ("sentinel@example.org", "+91 98765 43210", "221B Sentinel Street", "1990-04-01", "sentinel-photo.jpg")


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Temp cache/usage dir, default switches, no SERP zone override."""
    monkeypatch.setenv("BRIGHTDATA_CACHE_DIR", str(tmp_path / "bd"))
    monkeypatch.delenv("BRIGHTDATA_SERP_ZONE", raising=False)
    monkeypatch.delenv("LINKEDIN_ENRICHMENT", raising=False)
    monkeypatch.delenv("BRIGHTDATA_REQUEST_CAP", raising=False)
    return tmp_path / "bd"


class FakeAPI:
    """Routes (method, path) to queued responses and records every call."""

    def __init__(self, routes: dict):
        self.routes = {key: list(value) for key, value in routes.items()}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        queue = self.routes[(request.method, request.url.path)]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    def client(self, cap: int | None = None) -> bd.Client:
        return bd.Client(token=TOKEN, transport=httpx.MockTransport(self), sleep=lambda s: None, cap=cap)


def person_record(**extra) -> dict:
    """A by-URL style record (shape from the docs example) for a made-up person, with contact-like fields injected."""
    record = load("docs_examples/profile_by_url.json")["records"][0] | {
        "name": "Asha Example", "url": "https://in.linkedin.com/in/asha-example-123",
        "position": "Director | sentinel@example.org | +91 98765 43210", "city": "Pune, Maharashtra, India",
        "email": "sentinel@example.org", "phone": "+91 98765 43210", "address": "221B Sentinel Street",
        "birthday": "1990-04-01", "avatar": "https://cdn.example/sentinel-photo.jpg",
        "people_also_viewed": [{"name": "Other Person", "profile_link": "https://linkedin.com/in/other"}],
        "current_company": {"name": "Acme Mechatronics Pvt Ltd", "phone": "+91 98765 43210"},
        "experience": [{"title": "Managing Director", "company": "Acme Mechatronics Pvt Ltd",
                        "start_date": "Jan 2019", "end_date": "Present", "contact_info": {"email": "sentinel@example.org"}},
                       {"title": "Engineer", "company": "Other Works", "start_date": "2010", "end_date": "2018"}],
        "education": [{"title": "Example Institute of Technology", "start_year": "2004", "end_year": "2008",
                       "address": "221B Sentinel Street"}],
    }
    return record | extra


def assert_no_sentinels(tree: Path, value=None):
    text = json.dumps(value, ensure_ascii=False) if value is not None else ""
    for path in tree.rglob("*.json"):
        if path.name != "usage.json":
            text += path.read_text(encoding="utf-8")
    for sentinel in SENTINELS:
        assert sentinel not in text, sentinel
    assert "Other Person" not in text  # a third party from people_also_viewed


# ---- counter and cap -----------------------------------------------------------------------------------------

def test_every_request_is_counted_and_5xx_retried(isolated):
    api = FakeAPI({("GET", "/zone/get_active_zones"): [(502, "bad gateway"), (200, [])]})
    zones = api.client().active_zones()
    assert zones == [] and len(api.calls) == 2
    summary = bd.usage_summary()
    assert summary["requests"] == 2 and summary["used"] == 2 and summary["remaining"] == cfg.DEFAULT_REQUEST_CAP - 2


def test_4xx_is_not_retried_and_message_names_the_owner_action(isolated):
    live = load("live/trigger_not_active.json")
    api = FakeAPI({("POST", "/datasets/v3/trigger"): [(live["status_code"], live["body"])]})
    with pytest.raises(bd.BrightDataError) as caught:
        api.client().collect("linkedin_discover", cfg.DATASET_DISCOVER_BY_NAME, [{"url": "https://www.linkedin.com"}])
    assert len(api.calls) == 1 and caught.value.status == 400
    assert "Customer is not active" in str(caught.value) and "control panel" in str(caught.value)
    assert TOKEN not in str(caught.value)


def test_cap_refuses_before_sending(isolated, monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_REQUEST_CAP", "1")
    api = FakeAPI({("GET", "/zone/get_active_zones"): [(200, [])]})
    client = api.client()
    client.active_zones()
    with pytest.raises(bd.CapReached):
        client.active_zones()
    assert len(api.calls) == 1
    assert bd.usage_summary()["remaining"] == 0


def test_lookup_refused_when_worst_case_would_cross_cap(isolated):
    api = FakeAPI({})
    with pytest.raises(bd.CapReached):
        el.find_profiles("Asha Example", "Acme Mechatronics Limited", client=api.client(cap=5))
    assert api.calls == []


def test_records_past_the_first_count(isolated):
    records = [person_record(), person_record(name="Asha B Example")]
    api = FakeAPI({("POST", "/datasets/v3/scrape"): [(200, records)]})
    api.client().scrape("linkedin_profile", cfg.DATASET_PROFILE_BY_URL, [{"url": "https://linkedin.com/in/x"}])
    summary = bd.usage_summary()
    assert summary["requests"] == 1 and summary["records"] == 2 and summary["used"] == 2


def test_auth_header_is_bearer_token(isolated):
    api = FakeAPI({("GET", "/status"): [(200, load("live/status.json"))]})
    status = bd.account_status(api.client())
    assert api.calls[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert status == {"status": "active", "can_make_requests": False, "auth_fail_reason": "zone_not_found"}


# ---- LinkedIn ------------------------------------------------------------------------------------------------

def discover_api(records: list[dict]) -> FakeAPI:
    return FakeAPI({("POST", "/datasets/v3/trigger"): [(200, {"snapshot_id": "s_test"})],
                    ("GET", "/datasets/v3/progress/s_test"): [(200, {"status": "running"}), (200, {"status": "ready"})],
                    ("GET", "/datasets/v3/snapshot/s_test"): [(200, records)]})


def test_find_profiles_async_flow_strips_contacts_and_caches(isolated):
    others = {"name": "Ravi Different", "url": "https://linkedin.com/in/ravi", "experience": "Acme Mechatronics"}
    api = discover_api([person_record(), others])
    found = el.find_profiles("Prof. Asha Example", "Acme Mechatronics Limited", city="Pune", client=api.client())
    sent = json.loads(api.calls[0].content)
    assert sent["input"] == [{"url": "https://www.linkedin.com", "first_name": "asha", "last_name": "example"}]
    assert sent["limit_per_input"] == cfg.DISCOVER_LIMIT
    assert len(api.calls) == 4  # trigger, 2 progress checks, snapshot
    assert [c["name"] for c in found] == ["Asha Example"]  # a different person is never kept
    candidate = found[0]
    assert set(candidate) == set(cfg.CANDIDATE_FIELDS) | {"match", "reason", "source"}
    assert candidate["match"] == "likely" and "Acme Mechatronics Pvt Ltd" in candidate["reason"]
    assert "does not confirm" in candidate["reason"]  # city is context only
    assert candidate["headline"] == "Director"
    assert candidate["positions"][0] == {"title": "Managing Director", "company": "Acme Mechatronics Pvt Ltd",
                                         "start": "Jan 2019", "end": "Present"}
    assert candidate["education"] == [{"school": "Example Institute of Technology", "start_year": "2004",
                                       "end_year": "2008"}]
    assert candidate["fetched_at"]
    assert_no_sentinels(isolated, found)
    again = el.find_profiles("Prof. Asha Example", "Acme Mechatronics Limited", client=api.client())
    assert again == [{**candidate, "reason": candidate["reason"].split(" City")[0]}] and len(api.calls) == 4


def test_profile_by_url_keeps_only_public_professional_fields(isolated):
    api = FakeAPI({("POST", "/datasets/v3/scrape"): [(200, [person_record()])]})
    result = el.profile("https://in.linkedin.com/in/asha-example-123?trk=x", company="Acme Mechatronics Limited",
                        client=api.client())
    assert set(result) == set(cfg.PROFILE_FIELDS) | {"source", "match", "reason"}
    for position in result["positions"]:
        assert set(position) == set(cfg.POSITION_FIELDS)
    assert result["profile_url"] == "https://in.linkedin.com/in/asha-example-123"
    assert_no_sentinels(isolated, result)


def test_profile_sync_202_falls_back_to_polling(isolated):
    api = FakeAPI({("POST", "/datasets/v3/scrape"): [(202, {"snapshot_id": "s_test", "message": "in progress"})],
                   ("GET", "/datasets/v3/progress/s_test"): [(200, {"status": "ready"})],
                   ("GET", "/datasets/v3/snapshot/s_test"): [(200, [person_record()])]})
    result = el.profile("https://www.linkedin.com/in/asha-example-123", client=api.client())
    assert result["name"] == "Asha Example" and "match" not in result and len(api.calls) == 3


def test_profile_rejects_non_profile_url(isolated):
    with pytest.raises(ValueError):
        el.profile("https://www.nseindia.com/some/page", client=FakeAPI({}).client())


def test_match_levels():
    base = {"name": "Asha Example", "headline": None, "positions": []}
    assert el.match_level(base, "Acme Mechatronics Limited")[0] == "unconfirmed"
    headline_only = base | {"headline": "Founder, Acme Mechatronics"}
    level, reason = el.match_level(headline_only, "Acme Mechatronics Limited")
    assert level == "unconfirmed" and "headline" in reason
    elsewhere = base | {"positions": [{"title": "CEO", "company": "Other Works", "start": None, "end": None}]}
    assert el.match_level(elsewhere, "Acme Mechatronics Limited")[0] == "unconfirmed"
    related = base | {"positions": [{"title": None, "company": "Acme Holdings Private Limited", "start": None, "end": None}]}
    level, reason = el.match_level(related, "Acme Mechatronics Limited", related=["Acme Holdings Pvt Ltd"])
    assert level == "likely" and "related entity" in reason
    assert not el.companies_match("Acme Steel", "Acme Motors Limited")
    assert el.companies_match("ACME", "Acme Mechatronics Limited")


def test_docs_example_masked_name_is_not_matched():
    """Bright Data's documented discover example masks names; a masked name never passes as the person."""
    record = load("docs_examples/discover_by_name.json")["records"][0]
    assert not el.same_name(record["name"], "muge", "ozlutiras")
    kept = el.public_profile(record)
    assert kept["education"] == [{"school": "ETH Zurich", "start_year": None, "end_year": None}]
    assert kept["positions"] == []


def test_docs_example_title_that_repeats_company_is_dropped():
    record = load("docs_examples/profile_by_url.json")["records"][0]
    kept = el.public_profile(record)
    assert kept["positions"] == [{"title": None, "company": "Marshfield Clinic", "start": None, "end": None}]
    assert kept["profile_url"] is None  # the example's masked URL is not a profile URL


def test_scrub_text_removes_contacts_but_keeps_dates():
    assert el.scrub_text("Jan 2019 - Dec 2023") == "Jan 2019 - Dec 2023"
    assert el.scrub_text("2019-01-01") == "2019-01-01"
    assert el.scrub_text("Call +91 98765 43210 or (020) 2567-8901, mail a.b@x.co.in") == "Call or , mail"


def test_switch_off_sends_nothing(isolated, monkeypatch):
    monkeypatch.setenv("LINKEDIN_ENRICHMENT", "off")
    api = FakeAPI({})
    with pytest.raises(el.EnrichmentOff):
        el.find_profiles("Asha Example", "Acme Mechatronics Limited", client=api.client())
    assert api.calls == []


# ---- web search ----------------------------------------------------------------------------------------------

def test_no_serp_zone_is_reported_not_worked_around(isolated):
    api = FakeAPI({("GET", "/zone/get_active_zones"): [(200, load("live/zones.json"))]})
    with pytest.raises(bd.BrightDataError, match="No active SERP zone"):
        en.search("Asha Example", "Acme Mechatronics Limited", client=api.client())
    assert [c.url.path for c in api.calls] == ["/zone/get_active_zones"]


def test_non_serp_zone_is_refused(isolated, monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "unblocker1")
    api = FakeAPI({("GET", "/zone/get_active_zones"): [(200, [{"name": "unblocker1", "type": "unblocker"}])]})
    with pytest.raises(bd.BrightDataError, match="not an active SERP zone"):
        api.client().google("anything")


def test_company_news_keeps_title_source_date_url_only(isolated):
    news = load("docs_examples/serp_news.json")["response"]
    api = FakeAPI({("GET", "/zone/get_active_zones"): [(200, [{"name": "serp_api1", "type": "serp"}])],
                   ("POST", "/request"): [(200, news)]})
    rows = en.company_news("Acme Mechatronics Limited", client=api.client())
    body = json.loads(api.calls[1].content)
    assert body["zone"] == "serp_api1" and body["url"].startswith("https://www.google.com/search?q=")
    assert "tbm=nws" in body["url"] and "brd_json=1" in body["url"]
    assert rows[0]["title"].startswith("Hegseth") and rows[0]["source"] == "The Hill" and rows[0]["date"] == "1 day ago"
    for row in rows:
        assert set(row) == set(cfg.SEARCH_FIELDS) | {"label", "query", "fetched_at", "via"}
        assert row["label"] == "from web search, not verified"
    assert "Global retail sales" not in json.dumps(rows) + "".join(p.read_text() for p in isolated.rglob("*.json"))
    en.company_news("Acme Mechatronics Limited", client=api.client())
    assert len(api.calls) == 2  # zones and the query are both cached


def test_web_search_quotes_name_and_company_and_drops_bad_links(isolated):
    organic = {"organic": [{"title": "A result", "link": "https://news.example.com/a", "description": "snippet"},
                           {"title": "No link"}, {"title": "Script", "link": "javascript:alert(1)"}]}
    api = FakeAPI({("GET", "/zone/get_active_zones"): [(200, [{"name": "serp_api1", "type": "serp"}])],
                   ("POST", "/request"): [(200, organic)]})
    rows = en.search("Prof. Asha Example", "Acme Mechatronics Limited", client=api.client())
    query = json.loads(api.calls[1].content)["url"]
    assert "%22Asha+Example%22+%22Acme+Mechatronics+Limited%22" in query
    assert [(r["title"], r["source"], r["date"], r["url"]) for r in rows] == [
        ("A result", "news.example.com", None, "https://news.example.com/a")]


def test_estimates_are_worst_case_requests_at_zero_dollars():
    for row in (el.estimate("find_profiles"), el.estimate("profile"), en.estimate()):
        assert row["cost_usd"] == 0.0 and row["calls"] == row["brightdata_requests"] > 0
    assert el.estimate("find_profiles")["brightdata_requests"] == 1 + cfg.MAX_POLLS + 1 + cfg.DISCOVER_LIMIT - 1


def test_cached_zone_list_without_serp_is_refetched_once(isolated):
    api = FakeAPI({("GET", "/zone/get_active_zones"): [(200, []), (200, [{"name": "serp_api1", "type": "serp"}])]})
    client = api.client()
    with pytest.raises(bd.BrightDataError, match="No active SERP zone"):
        client.serp_zone()
    assert client.serp_zone() == "serp_api1"  # the owner added a zone; the cached empty list is not trusted
    assert len(api.calls) == 2
    assert client.serp_zone() == "serp_api1" and len(api.calls) == 2  # now cached


def test_error_only_snapshot_is_raised_not_cached(isolated):
    api = discover_api([{"error": "dead_page", "error_code": "dead_page", "input": {"first_name": "asha"}}])
    with pytest.raises(bd.BrightDataError, match="only error records"):
        el.find_profiles("Asha Example", "Acme Mechatronics Limited", client=api.client())
    assert not list((isolated / "linkedin_discover").glob("*.json"))


def test_no_records_is_an_honest_empty_result(isolated):
    api = discover_api([])
    assert el.find_profiles("Asha Example", "Acme Mechatronics Limited", client=api.client()) == []
