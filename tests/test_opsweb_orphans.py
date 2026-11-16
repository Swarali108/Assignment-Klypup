"""RM state and assignments are only written for a person who is on the event (no orphan rows in the Team counts)."""

EVENT, PERSON = "sedemac_ipo", "p_mallika_r_iyer"


def test_rm_state_for_unknown_event_or_person_is_404_and_not_stored(as_role):
    from api import rm_state

    rm = as_role("rm")
    assert rm.put("/api/rm/no_such_event/no_such_person", json={"note": "x"}).status_code == 404
    assert rm.put(f"/api/rm/{EVENT}/zz", json={"status": "called"}).status_code == 404
    assert rm_state.all_states().get((EVENT, "zz")) is None
    assert rm_state.all_states().get(("no_such_event", "no_such_person")) is None
    assert rm.put(f"/api/rm/{EVENT}/{PERSON}", json={"status": "called"}).status_code == 200


def test_assignment_for_unknown_person_is_404(as_role):
    admin = as_role("admin")
    assert admin.put(f"/api/assignments/{EVENT}/zz", json={"rm_email": None}).status_code == 404
    assert admin.put("/api/assignments/no_such_event/zz", json={"rm_email": None}).status_code == 404
