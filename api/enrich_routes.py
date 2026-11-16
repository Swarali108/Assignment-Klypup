"""Routes for people enrichment (Bright Data): status for the Sources page, a person's stored result, and a
confirmed refresh. See api/enrichment.py for the rules (public fields only, request cap, confirm before paid lookups).

  GET  /api/enrichment/status                         requests used / cap this month, LinkedIn switch, token set?
  GET  /api/people/{event}/{person}/enrichment        stored result + running flag + worst-case estimate for a refresh
  POST /api/people/{event}/{person}/enrichment        body {kinds: ["linkedin","web"], confirmed_requests: n, refresh: bool}
       Starts the lookups in the background (202). confirmed_requests must be at least the server's own worst-case
       count for this moment, so a stale confirm (cap used meanwhile, a cached copy expired) is refused with 409.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import auth, enrichment

router = APIRouter()


class RefreshBody(BaseModel):
    kinds: list[str] = Field(default_factory=lambda: list(enrichment.KINDS))
    confirmed_requests: int = Field(ge=0)
    refresh: bool = True


@router.get("/api/enrichment/status", dependencies=[auth.VIEW])
def enrichment_status() -> dict:
    """Requests used / cap for this month, the LinkedIn switch, whether Bright Data is connected."""
    return enrichment.status()


@router.get("/api/people/{event_id}/{person_id}/enrichment", dependencies=[auth.VIEW])
def person_enrichment(event_id: str, person_id: str) -> dict:
    """The stored public profile and web mentions for this person (nothing is fetched here)."""
    try:
        return enrichment.state(event_id, person_id)
    except KeyError:
        raise HTTPException(404, "No such person in this event")


@router.post("/api/people/{event_id}/{person_id}/enrichment", dependencies=[auth.EDIT_RM], status_code=202)
def refresh_enrichment(event_id: str, person_id: str, body: RefreshBody) -> dict:
    """Confirmed paid lookup for this person. Runs in the background; poll the GET route."""
    kinds = [k for k in body.kinds if k in enrichment.KINDS]
    if not kinds:
        raise HTTPException(400, "Choose the public profile, the web mentions, or both.")
    try:
        found = enrichment.estimate(event_id, person_id, kinds, refresh=body.refresh)
    except KeyError:
        raise HTTPException(404, "No such person in this event")
    blocked = [v["reason"] for v in found["kinds"].values() if not v["allowed"] and v["reason"]]
    if blocked and found["total"] == 0:
        raise HTTPException(409, blocked[0])
    if found["over_cap"]:
        raise HTTPException(409, f"This lookup could need {found['total']} requests but only {found['remaining']} are left "
                                 f"in {found['month']}. Nothing was sent.")
    if body.confirmed_requests < found["total"]:
        raise HTTPException(409, f"The request estimate changed to {found['total']}. Review it and confirm again.")
    if not enrichment.start(event_id, person_id, kinds, body.refresh):
        raise HTTPException(409, "A lookup for this person is already running.")
    return {"started": True, "kinds": kinds, "requests_estimated": found["total"]}
