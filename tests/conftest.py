"""Shared fixtures: an isolated app database and signed-in clients for each demo role."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_bright_data(tmp_path, monkeypatch):
    """No test may reach Bright Data or the real cache, whatever the developer's .env holds (rule 5: tests need no
    network). The token is set to empty rather than removed, because tools/brightdata.py calls load_dotenv() on each
    use and that refills a missing variable but never overwrites a set one. Tests that exercise the client pass their
    own token and a mock transport (tests/test_brightdata_enrich.py)."""
    monkeypatch.setenv("BRIGHTDATA_API_TOKEN", "")
    monkeypatch.setenv("BRIGHTDATA_CACHE_DIR", str(tmp_path / "brightdata"))


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """A temp SQLite database, a fixed session secret, no Postgres, no model, no evidence warming."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FINSIGHT_DB_PATH", str(tmp_path / "app.sqlite"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("FINSIGHT_WARM", "0")
    from api import main

    monkeypatch.setattr(main, "ASK_MODEL", lambda question: (_ for _ in ()).throw(RuntimeError("no model in tests")))
    return main


@pytest.fixture()
def as_role(app_env):
    """as_role('admin' | 'rm' | 'viewer' | None) -> a TestClient signed in as that demo user (None: signed out)."""

    def make(role: str | None) -> TestClient:
        client = TestClient(app_env.app)
        if role:
            reply = client.post("/api/auth/login", json={"email": f"{role}@finsight.demo", "password": "demo1234"})
            assert reply.status_code == 200, reply.text
        return client

    return make


@pytest.fixture()
def client_admin(as_role):
    """A client signed in as the demo admin."""
    return as_role("admin")
