"""Deployment settings read from the environment: allowed origins, production secret, Secure cookie, health, DATA_DIR."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api import auth, datadir, guard

LOGIN = {"email": "admin@aurelia.demo", "password": "demo1234"}


@pytest.fixture()
def no_dotenv(monkeypatch):
    """Startup must not read a developer's .env (it could hold a real DATABASE_URL)."""
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)


# ---------- ALLOWED_ORIGINS ----------

def test_origins_default_to_the_local_web_app(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("AURELIA_ORIGINS", raising=False)
    json_headers = {"content-type": "application/json"}
    assert guard.refusal({**json_headers, "origin": "http://localhost:3000"}, "POST") is None
    assert guard.refusal({**json_headers, "origin": "https://aurelia.vercel.app"}, "POST")[0] == 403


def test_allowed_origins_replace_the_default(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://Aurelia.example.com/ , https://aurelia.vercel.app,")
    monkeypatch.delenv("AURELIA_ORIGINS", raising=False)
    assert guard.allowed_origins() == {"https://aurelia.example.com", "https://aurelia.vercel.app"}
    json_headers = {"content-type": "application/json"}
    assert guard.refusal({**json_headers, "origin": "https://aurelia.vercel.app"}, "PUT") is None
    assert guard.refusal({**json_headers, "origin": "https://aurelia.example.com/"}, "POST") is None
    assert guard.refusal({**json_headers, "origin": "http://localhost:3000"}, "POST")[0] == 403
    assert guard.refusal({**json_headers, "origin": "https://evil.example"}, "DELETE")[0] == 403
    assert guard.refusal({"origin": "https://evil.example"}, "GET") is None  # reads are never refused


def test_allowed_origins_apply_to_real_requests(app_env, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://aurelia.vercel.app")
    client = TestClient(app_env.app)
    assert client.post("/api/auth/login", json=LOGIN, headers={"Origin": "https://aurelia.vercel.app"}).status_code == 200
    refused = client.post("/api/auth/login", json=LOGIN, headers={"Origin": "https://other.example"})
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Requests from this site are not allowed"


# ---------- SESSION_SECRET in production ----------

def test_production_refuses_to_start_without_session_secret(app_env, monkeypatch, no_dotenv):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        with TestClient(app_env.app):
            pass


def test_production_refuses_a_short_session_secret(app_env, monkeypatch, no_dotenv):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "too-short")
    with pytest.raises(RuntimeError, match="at least 32"):
        with TestClient(app_env.app):
            pass


def test_production_never_falls_back_to_a_generated_secret_file(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / "session_secret")
    with pytest.raises(RuntimeError):
        auth.make_session({"email": "a@b.c", "name": "A", "role": "viewer"})
    assert not (tmp_path / "session_secret").exists()


def test_production_starts_with_a_real_secret(app_env, monkeypatch, no_dotenv):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "x" * 64)
    with TestClient(app_env.app) as client:
        assert client.get("/api/health").json() == {"ok": True, "db": "sqlite"}


def test_local_without_app_env_still_starts_without_a_secret(app_env, monkeypatch, no_dotenv, tmp_path):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / "session_secret")
    with TestClient(app_env.app) as client:
        assert client.post("/api/auth/login", json=LOGIN).status_code == 200
    assert (tmp_path / "session_secret").is_file()


# ---------- demo accounts in production (DEMO_ACCOUNTS) ----------

DEMO_NON_ADMIN = ["rm@aurelia.demo", "viewer@aurelia.demo", "new.rm@aurelia.demo", "head@aurelia.demo"]


@pytest.fixture()
def production(app_env, monkeypatch):
    """APP_ENV=production with a real-length secret and no admin or demo settings from the developer's shell."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "x" * 64)
    for name in ("DEMO_ACCOUNTS", "ADMIN_EMAIL", "ADMIN_PASSWORD", "ADMIN_NAME"):
        monkeypatch.delenv(name, raising=False)
    return TestClient(app_env.app)


def _login(client: TestClient, email: str, password: str = "demo1234") -> int:
    return client.post("/api/auth/login", json={"email": email, "password": password}).status_code


def test_production_offers_no_demo_accounts_by_default(production):
    assert production.get("/api/auth/config").json() == {"production": True, "demo_accounts": []}
    assert _login(production, "rm@aurelia.demo") == 401


def test_demo_accounts_flag_offers_every_demo_account_except_admin(production, monkeypatch):
    monkeypatch.setenv("DEMO_ACCOUNTS", "1")
    assert production.get("/api/auth/config").json()["demo_accounts"] == DEMO_NON_ADMIN
    assert _login(production, "rm@aurelia.demo") == 200
    assert production.get("/api/auth/me").json()["permissions"]["process"] is False
    assert _login(production, "admin@aurelia.demo") == 401  # the public demo password never opens an admin


def test_the_real_admin_may_reuse_the_demo_admin_address(production, monkeypatch):
    monkeypatch.setenv("DEMO_ACCOUNTS", "1")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@aurelia.demo")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-private-password")
    assert _login(production, "admin@aurelia.demo", "a-long-private-password") == 200
    assert _login(production, "admin@aurelia.demo") == 401


def test_turning_the_flag_off_locks_out_demo_accounts_already_created(production, monkeypatch):
    monkeypatch.setenv("DEMO_ACCOUNTS", "1")
    assert _login(production, "head@aurelia.demo") == 200
    monkeypatch.delenv("DEMO_ACCOUNTS")
    assert _login(production, "head@aurelia.demo") == 401


def test_local_offers_every_demo_account(app_env, monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    config = TestClient(app_env.app).get("/api/auth/config").json()
    assert config == {"production": False, "demo_accounts": ["admin@aurelia.demo", *DEMO_NON_ADMIN]}


# ---------- Secure cookie ----------

def _set_cookie(client: TestClient, headers: dict | None = None) -> str:
    reply = client.post("/api/auth/login", json=LOGIN, headers=headers or {})
    assert reply.status_code == 200
    return reply.headers["set-cookie"].lower()


def test_cookie_not_secure_on_plain_local_http(app_env, monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.delenv("AURELIA_COOKIE_SECURE", raising=False)
    assert "secure" not in _set_cookie(TestClient(app_env.app))


def test_cookie_secure_when_forced(app_env, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    cookie = _set_cookie(TestClient(app_env.app))
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_cookie_secure_when_the_request_came_over_https(app_env, monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.delenv("AURELIA_COOKIE_SECURE", raising=False)
    assert "secure" in _set_cookie(TestClient(app_env.app), {"X-Forwarded-Proto": "https"})


def test_cookie_secure_can_be_switched_off(app_env, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "0")
    assert "secure" not in _set_cookie(TestClient(app_env.app), {"X-Forwarded-Proto": "https"})


# ---------- health ----------

def test_health_checks_the_database(app_env):
    client = TestClient(app_env.app)
    assert client.get("/api/health").json() == {"ok": True, "db": "sqlite"}


def test_health_is_503_when_the_database_fails(app_env, monkeypatch):
    from api import db

    def broken():
        raise ConnectionError("no database")

    monkeypatch.setattr(db, "connect", broken)
    reply = TestClient(app_env.app).get("/api/health")
    assert reply.status_code == 503
    assert reply.json() == {"ok": False, "db": "sqlite", "error": "ConnectionError"}


# ---------- DATA_DIR ----------

def _shipped(root):
    (root / "outputs" / "ev1").mkdir(parents=True)
    (root / "outputs" / "ev1" / "ranked.json").write_text("v1", encoding="utf-8")
    (root / "events").mkdir()
    (root / "events" / "ev1.json").write_text("{}", encoding="utf-8")
    (root / "cache" / "llm").mkdir(parents=True)
    (root / "cache" / "llm" / "a.json").write_text("cached", encoding="utf-8")
    (root / "cost_log.csv").write_text("header\n", encoding="utf-8")


def test_data_dir_unset_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    _shipped(tmp_path)
    assert datadir.prepare(tmp_path) is None
    assert not (tmp_path / "outputs").is_symlink()


def test_data_dir_first_boot_seeds_and_links(tmp_path, monkeypatch):
    monkeypatch.delenv("COST_LOG_PATH", raising=False)
    root, volume = tmp_path / "app", tmp_path / "data"
    root.mkdir()
    _shipped(root)
    counts = datadir.prepare(root, str(volume))
    assert counts["outputs"] == 1 and counts["events"] == 1 and counts["cache"] == 1 and counts["cost_log.csv"] == 1
    for name in ("outputs", "events", "cache", "api/state"):
        assert (root / name).is_symlink() and (root / name).resolve() == (volume / name).resolve()
    assert (root / "outputs" / "ev1" / "ranked.json").read_text(encoding="utf-8") == "v1"
    (root / "outputs" / "ev2").mkdir()  # a write through the app's path lands on the volume
    assert (volume / "outputs" / "ev2").is_dir()
    import os

    assert os.environ["COST_LOG_PATH"] == str(volume / "cost_log.csv")
    assert (root / "cost_log.csv").is_symlink()
    with (root / "cost_log.csv").open("a", encoding="utf-8") as handle:  # an append through the app path
        handle.write("row\n")
    assert (volume / "cost_log.csv").read_text(encoding="utf-8") == "header\nrow\n"
    assert "outputs" not in datadir.prepare(root, str(volume))  # already linked: a restart in the same container is a no-op


def _redeploy(tmp_path, volume, ranked_text: str, extra_event: bool = False):
    """A new container: a fresh copy of the shipped files next to the same volume."""
    root = tmp_path / f"app-{ranked_text}-{int(extra_event)}"
    root.mkdir()
    _shipped(root)
    (root / "outputs" / "ev1" / "ranked.json").write_text(ranked_text, encoding="utf-8")
    if extra_event:
        (root / "events" / "ev9.json").write_text('{"new": true}', encoding="utf-8")
    return root, datadir.prepare(root, str(volume))


def test_data_dir_later_deploy_updates_untouched_files_and_adds_new_ones(tmp_path, monkeypatch):
    monkeypatch.delenv("COST_LOG_PATH", raising=False)
    root, volume = tmp_path / "app", tmp_path / "data"
    root.mkdir()
    _shipped(root)
    datadir.prepare(root, str(volume))
    _root2, counts = _redeploy(tmp_path, volume, "v2", extra_event=True)
    assert (volume / "outputs" / "ev1" / "ranked.json").read_text(encoding="utf-8") == "v2"
    assert (volume / "events" / "ev9.json").is_file()
    assert counts["outputs"] == 1 and counts["events"] == 1 and counts["cache"] == 0


def test_data_dir_keeps_work_done_on_the_volume(tmp_path, monkeypatch):
    monkeypatch.delenv("COST_LOG_PATH", raising=False)
    root, volume = tmp_path / "app", tmp_path / "data"
    root.mkdir()
    _shipped(root)
    datadir.prepare(root, str(volume))
    (volume / "outputs" / "ev1" / "ranked.json").write_text("re-run in production", encoding="utf-8")
    _redeploy(tmp_path, volume, "v2")
    assert (volume / "outputs" / "ev1" / "ranked.json").read_text(encoding="utf-8") == "re-run in production"
    manifest = json.loads((volume / datadir.MANIFEST).read_text(encoding="utf-8"))
    assert "outputs/ev1/ranked.json" in manifest


def test_data_dir_not_writable_exits_with_the_fix(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        datadir.prepare(tmp_path, str(blocker / "data"))
    assert "RAILWAY_RUN_UID=0" in capsys.readouterr().err
