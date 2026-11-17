"""Tier-1: RM preferences, the client book, and the per-user "In your book" flag."""

from __future__ import annotations


def test_name_key_folds_titles_case_and_punctuation():
    from api.prefs import name_key

    assert name_key("Dr. Dharminder  Kumar Nagar") == name_key("DHARMINDER KUMAR NAGAR") == "dharminder kumar nagar"
    assert name_key("Shri. K. S. Rao") == "k s rao"
    assert name_key("") == ""


def test_new_rm_is_not_onboarded_and_preferences_merge(app_env):
    from fastapi.testclient import TestClient

    client = TestClient(app_env.app)
    assert client.post("/api/auth/login", json={"email": "new.rm@finsight.demo", "password": "demo1234"}).status_code == 200
    me = client.get("/api/me").json()
    assert me["onboarded"] is False and me["role"] == "rm" and me["book_count"] == 0
    saved = client.put("/api/me/preferences", json={"event_types": ["ipo"], "min_ticket_cr": 25}).json()
    assert saved["event_types"] == ["ipo"] and saved["min_ticket_cr"] == 25 and saved["alerts"] == "daily"
    done = client.put("/api/me/preferences", json={"onboarded": True}).json()
    assert done["onboarded"] is True and done["event_types"] == ["ipo"]


def test_book_flags_only_the_owner_and_dedupes(as_role, monkeypatch):
    from api import prefs

    rm, admin = as_role("rm"), as_role("admin")
    assert rm.get("/api/me/preferences").json()["onboarded"] is True  # seeded demo accounts skip the guide
    assert rm.post("/api/me/book", json={"names": ["Asha Rao", "ASHA RAO", "  ", "Mr. Vikas Jain"]}).json() == {"book_count": 2}

    # in_book reads the asker set by the middleware; check the helper directly for both users.
    token = prefs._asker.set("rm@finsight.demo")
    try:
        assert prefs.in_book("asha rao") and prefs.in_book("Vikas Jain") and not prefs.in_book("Someone Else")
    finally:
        prefs._asker.reset(token)
    token = prefs._asker.set("admin@finsight.demo")
    try:
        assert not prefs.in_book("Asha Rao")
    finally:
        prefs._asker.reset(token)

    assert admin.get("/api/me/preferences").json()["book_count"] == 0
    assert rm.delete("/api/me/book", headers={"Content-Type": "application/json"}).json() == {"book_count": 0}
    assert rm.post("/api/me/book", json={"names": ["x"] * 5001}).status_code == 413
