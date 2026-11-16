"""Validate an event file before any document is fetched."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EVENT_TYPES = ("ipo", "buyback", "ofs_stock_exchange", "acquisition", "esop_buyback", "other", "block_deal", "insider_sale")
# Events built from structured exchange records (deal reports, insider-trading disclosures), not from a PDF.
# They carry record ids and the records file instead of documents.
STRUCTURED_TYPES = ("block_deal", "insider_sale")
# public_announcement: a buyback's pre-offer announcement (price, size, promoters' intention); read like a
# letter of offer. announcement: a later notice (allotment, listing, buyback results), read whole.
DOC_TYPES = ("rhp", "prospectus", "letter_of_offer", "public_announcement", "announcement", "news")
_SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
# A structured event's records file: outputs/signals/<kind>.json, nothing else (the path is opened by run.py).
_RECORDS_FILE = re.compile(r"^outputs/signals/[a-z0-9_]+\.json$")


class DocumentSpec(BaseModel):
    """One public document the event points at."""

    url: str
    doc_type: Literal["rhp", "prospectus", "letter_of_offer", "public_announcement", "announcement", "news"]
    note: str | None = None

    @field_validator("url")
    @classmethod
    def url_is_http(cls, value: str) -> str:
        """Accept only web URLs. fetch() is the only downloader."""
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("document url must start with http:// or https://")
        return value


class EventSpec(BaseModel):
    """The input file for one money event. Company text stays in this file, not in code."""

    event_id: str
    event_type: Literal["ipo", "buyback", "ofs_stock_exchange", "acquisition", "esop_buyback", "other",
                        "block_deal", "insider_sale"]
    company: str = Field(min_length=1)
    documents: list[DocumentSpec] = Field(default_factory=list)
    event_date: str | None = None
    # Structured events only: the ids of the exchange records this event covers, and the file that holds them.
    # None (not []) by default, so a document event written with exclude_none gains no new keys.
    records: list[str] | None = None
    records_file: str | None = None

    @field_validator("event_id")
    @classmethod
    def event_id_is_slug(cls, value: str) -> str:
        """Keep ids safe as folder names."""
        if _SLUG.fullmatch(value) is None:
            raise ValueError("event_id must be a lowercase slug")
        return value

    @field_validator("records_file")
    @classmethod
    def records_file_is_signals_json(cls, value: str | None) -> str | None:
        """Only outputs/signals/<kind>.json: run.py opens this path, so nothing else is accepted."""
        if value is None:
            return None
        if _RECORDS_FILE.fullmatch(value) is None:
            raise ValueError("records_file must be outputs/signals/<kind>.json")
        return value

    @model_validator(mode="after")
    def inputs_match_type(self) -> "EventSpec":
        """A document event needs at least one document; a structured event needs record ids and their file."""
        if self.event_type in STRUCTURED_TYPES:
            if not self.records or not self.records_file:
                raise ValueError(f"a {self.event_type} event needs records (record ids) and records_file")
        elif not self.documents:
            raise ValueError("documents must list at least one document")
        return self

    @field_validator("event_date")
    @classmethod
    def event_date_is_iso(cls, value: str | None) -> str | None:
        """Require YYYY-MM-DD when a date is present."""
        if value is None:
            return None
        datetime.strptime(value, "%Y-%m-%d")
        return value


def load_event_spec(path: Path) -> EventSpec:
    """Read and validate one events/<event_id>.json file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EventSpec.model_validate(data)
