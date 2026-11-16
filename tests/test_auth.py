"""Tier-1: sign-in, roles on every endpoint, and the fixes from the security review (FINDINGS.md)."""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

PUBLIC = {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/config"}
SPEC = {"event_id": "probe_ipo_202611", "event_type": "ipo", "company": "Probe Ltd",
        "documents": [{"url": "http://127.0.0.1/x.pdf", "doc_type": "prospectus"}]}


def test_demo_users_are_seeded_once_and_login_sets_a_safe_cookie(app_env):
    from fastapi.testclient import TestClient

    from api import db, seed_users

    client = TestClient(app_env.app)
    assert client.post("/api/auth/login", json={"email": "admin@aurelia.demo", "password": "wrong"}).status_code == 401
    reply = client.post("/api/auth/login", json={"email": "ADMIN@aurelia.demo", "password": "demo1234"})
    assert reply.status_code == 200 and reply.json()["role"] == "admin"
    cookie = reply.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=43200" in cookie
    assert seed_users.seed() == 0  # a repeat adds nothing
    with db.connect() as conn:
        assert {r["role"] for r in conn.query("SELECT role FROM users")} == {"admin", "head", "rm", "viewer"}
        assert "demo1234" not in conn.query("SELECT password_hash FROM users")[0]["password_hash"]
    assert client.get("/api/auth/me").json()["permissions"]["process"] is True


def test_a_forged_or_expired_cookie_is_not_a_session(app_env):
    from api import auth

    token = auth.make_session({"email": "a@x", "name": "A", "role": "admin"}, now=1_000.0)
    assert auth.read_session(token, now=1_001.0)["role"] == "admin"
    assert auth.read_session(token, now=1_000.0 + auth.SESSION_SECONDS + 1) is None
    body, _, _signature = token.partition(".")
    assert auth.read_session(body + ".AAAA", now=1_001.0) is None


def test_every_endpoint_needs_a_session(as_role, app_env):
    """No session -> 401 on every /api route except health, login and logout."""
    anonymous = as_role(None)
    checked = 0
    for route in app_env.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api") or path in PUBLIC:
            continue
        url = path.replace("{event_id}", "e").replace("{person_id}", "p").replace("{doc_sha}", "a" * 64).replace("{job_id}", "j")
        for method in route.methods - {"HEAD", "OPTIONS"}:
            assert anonymous.request(method, url, json={}).status_code == 401, f"{method} {path}"
            checked += 1
    assert checked >= 20


def test_viewer_is_read_only(as_role):
    viewer = as_role("viewer")
    assert viewer.get("/api/today").status_code == 200
    assert viewer.put("/api/rm/sedemac_ipo/p_mallika_r_iyer", json={"status": "called"}).status_code == 403
    assert viewer.post("/api/events/sedemac_ipo/run", json={}).status_code == 403
    assert viewer.post("/api/events", json=SPEC).status_code == 403
    assert viewer.post("/api/events/from-links", json={"urls": ["https://example.org/a.pdf"]}).status_code == 403
    assert viewer.get("/api/export/calls.csv").status_code == 403
    assert viewer.post("/api/ask", json={"q": "promoters"}).status_code == 403
    assert viewer.get("/api/ops").status_code == 403


def test_rm_can_log_outcomes_but_not_process_or_see_ops(as_role):
    rm = as_role("rm")
    assert rm.put("/api/rm/sedemac_ipo/p_mallika_r_iyer", json={"status": "called", "note": "x"}).status_code == 200
    assert rm.get("/api/export/calls.csv").status_code == 200
    assert rm.post("/api/events/sedemac_ipo/run", json={}).status_code == 403
    assert rm.post("/api/events", json=SPEC).status_code == 403
    assert rm.get("/api/ops").status_code == 403


def test_admin_sees_ops(as_role):
    assert as_role("admin").get("/api/ops").status_code == 200


# ---- FINDINGS.md ----

def test_finding1_redirect_to_a_private_address_is_refused(tmp_path, monkeypatch):
    from tools import fetch as fetch_mod

    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))
    calls = []

    def fake_get(url, timeout, headers, follow_redirects):
        calls.append((url, follow_redirects))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(fetch_mod.FetchError, match="refused"):
        fetch_mod.fetch("https://8.8.8.8/start.pdf")
    assert calls == [("https://8.8.8.8/start.pdf", False)]  # the private hop was never requested


def test_finding1_redirect_to_a_public_address_is_followed(tmp_path, monkeypatch):
    from tools import fetch as fetch_mod

    monkeypatch.setenv("FETCH_CACHE_DIR", str(tmp_path))

    def fake_get(url, timeout, headers, follow_redirects):
        if url.endswith("/start.pdf"):
            return httpx.Response(301, headers={"location": "https://1.1.1.1/real.pdf"}, request=httpx.Request("GET", url))
        return httpx.Response(200, content=b"%PDF-1.4 ok", headers={"content-type": "application/pdf"},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    path, _meta = fetch_mod.fetch("https://8.8.8.8/start.pdf")
    assert path.read_bytes().startswith(b"%PDF")


def test_finding1_docs_endpoint_serves_only_pdfs(client_admin, tmp_path, monkeypatch):
    from api import store

    monkeypatch.setattr(store, "FETCH_DIR", tmp_path)
    page, pdf = b"<html>internal page</html>", b"%PDF-1.4 real"
    shas = {}
    for name, body, ctype in (("html", page, "text/html"), ("pdf", pdf, "application/octet-stream")):
        sha = hashlib.sha256(name.encode()).hexdigest()
        shas[name] = sha
        (tmp_path / f"{sha}.bin").write_bytes(body)
        (tmp_path / f"{sha}.json").write_text(json.dumps({"content_type": ctype}), encoding="utf-8")
    assert client_admin.get(f"/api/docs/{shas['html']}.pdf").status_code == 404
    assert client_admin.get(f"/api/docs/{shas['pdf']}.pdf").status_code == 200


@pytest.mark.parametrize("url", ["http://127.0.0.1/x.pdf", "http://169.254.169.254/latest/meta-data/x.pdf", "http://10.0.0.5/a.pdf"])
def test_finding2_create_event_rejects_private_document_urls(client_admin, url):
    body = {**SPEC, "documents": [{"url": url, "doc_type": "prospectus"}]}
    assert client_admin.post("/api/events", json=body).status_code == 400


def test_finding3_cross_site_writes_are_refused(client_admin):
    evil = client_admin.put("/api/rm/sedemac_ipo/p_mallika_r_iyer", json={"status": "called"},
                            headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert client_admin.post("/api/ask", json={"q": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403
    ok = client_admin.put("/api/rm/sedemac_ipo/p_mallika_r_iyer", json={"status": "called"},
                          headers={"Origin": "http://localhost:3000"})
    assert ok.status_code == 200
    # a plain form post (no preflight) is not JSON, so it is refused too
    assert client_admin.post("/api/ask", content="q=hi", headers={"content-type": "application/x-www-form-urlencoded"}).status_code == 415


def test_finding4_csv_cells_that_could_run_as_formulas_are_prefixed():
    from api.views import csv_cell

    for cell in (" =1+1", "\t=1", "=SUM(A1)", "+1", "-2+3", "@x", "\r=1", "  @cmd"):
        assert csv_cell(cell) == "'" + cell
    assert csv_cell("Rahul Bahri") == "Rahul Bahri" and csv_cell(12.5) == 12.5


def test_postgres_sql_is_written_once_and_translated_for_sqlite():
    from api.db import Conn

    sql = "INSERT INTO rm_state (event_id, person_id) VALUES (%s, %s) ON CONFLICT (event_id, person_id) DO NOTHING"
    assert Conn(None, "sqlite")._sql(sql).count("?") == 2
    assert Conn(None, "postgres")._sql(sql) == sql
