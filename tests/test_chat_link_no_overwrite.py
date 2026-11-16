"""A link pasted in the chat never overwrites an event spec that already exists (FINDINGS item 7)."""

import json
from datetime import date

from api import store
from api.chat import actions
from tools.discover import slug


def _setup(tmp_path, monkeypatch):
    """A temporary events folder holding one existing event for 'Acme Ltd'."""
    monkeypatch.setattr(store, "EVENTS_DIR", tmp_path)
    (tmp_path / "auto").mkdir()
    event_id = f"{slug('Acme Ltd')}_ipo_{date.today().strftime('%Y%m')}"
    original = {"event_id": event_id, "event_type": "ipo", "company": "Acme Ltd",
                "documents": [{"url": "https://example.com/original.pdf", "doc_type": "rhp"}]}
    (tmp_path / f"{event_id}.json").write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr("tools.propose.propose",
                        lambda url: {"company": "Acme Ltd", "event_type": "ipo", "doc_type": "prospectus"})
    monkeypatch.setattr("tools.propose.existing_event", lambda *args, **kwargs: None)
    return event_id, original


def test_existing_event_is_opened_not_overwritten(tmp_path, monkeypatch):
    event_id, original = _setup(tmp_path, monkeypatch)
    returned = actions._new_event_from_link("https://example.com/other.pdf")
    assert returned == event_id
    assert json.loads((tmp_path / f"{event_id}.json").read_text(encoding="utf-8")) == original
