"""The person trail tells the same day counts as the call card (both recounted to today, not the run day)."""

from __future__ import annotations

from api import store, trail, views


def test_trail_rank_reasons_and_brief_match_the_card():
    """For every callable person of a few document events, the trail's rank reasons and brief lines equal the card's."""
    events = {e["spec"].event_id: e for e in store.load_events()}
    checked = 0
    for eid in ("sedemac_ipo", "hd_fire_protect_limited_ipo_202610", "zetwerk_manufacturing_businesses_limited_ipo_202610"):
        event = events.get(eid)
        if not event or not event["processed"]:
            continue
        for entry in (event["out"]["ranked"] or {}).get("callable", [])[:8]:
            pid = entry["person_id"]
            card = views.person_card(event, pid, None, {})
            steps = {s["key"]: s for s in trail.build(event, pid)["steps"]}
            assert steps["rank"]["reasons"] == card["rank_reasons"], pid
            if steps["brief"].get("lines"):
                assert steps["brief"]["lines"] == card["brief"]["lines"], pid
            checked += 1
    assert checked > 0
