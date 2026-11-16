"""The spending gate: viewing is open, running needs APP_PASSWORD. No network, no key.

The password box is in the profile menu; the Run button and the new-event form are
on the Reports page and appear only once the password matches.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import tools.llm  # noqa: F401  (loads .env now, so the tests below control the environment)
from app import password_matches

APP = str(Path(__file__).resolve().parents[1] / "app.py")
RUN = "Run full pipeline"
NEW_EVENT_FIELD = "event_id (lowercase slug)"


def _reports(monkeypatch, password: str | None, secret: str | None = None) -> AppTest:
    """The app on the Reports page, with APP_PASSWORD set (or not) in the environment and st.secrets."""
    monkeypatch.setenv("APP_PASSWORD", password or "")
    app = AppTest.from_file(APP, default_timeout=60)
    if secret is not None:
        app.secrets["APP_PASSWORD"] = secret
    app.session_state["page"] = "reports"
    return app.run()


def _buttons(app: AppTest) -> list[str]:
    return [button.label for button in app.button]


def _new_event_form_shown(app: AppTest) -> bool:
    return any(field.label == NEW_EVENT_FIELD for field in app.text_input)


def _type_password(app: AppTest, value: str) -> AppTest:
    return app.text_input(key="run_password").input(value).run()


def test_no_password_set_hides_run_and_new_event(monkeypatch):
    app = _reports(monkeypatch, None)
    assert not app.exception
    assert RUN not in _buttons(app) and not _new_event_form_shown(app)
    assert not [field for field in app.text_input if field.key == "run_password"]


def test_run_and_new_event_appear_only_with_the_right_password(monkeypatch):
    app = _reports(monkeypatch, "open-sesame")
    assert RUN not in _buttons(app) and not _new_event_form_shown(app)
    _type_password(app, "wrong")
    assert RUN not in _buttons(app) and app.error
    _type_password(app, "open-sesame")
    assert RUN in _buttons(app) and _new_event_form_shown(app)


def test_password_from_secrets_is_copied_into_the_environment(monkeypatch):
    app = _reports(monkeypatch, None, secret="from-secrets")
    _type_password(app, "from-secrets")
    assert RUN in _buttons(app)


@pytest.mark.parametrize(("entered", "expected"), [("pw", True), ("pW", False), ("", False), ("pwx", False)])
def test_password_matches(entered, expected):
    assert password_matches(entered, "pw") is expected
