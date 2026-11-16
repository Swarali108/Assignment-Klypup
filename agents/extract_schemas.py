"""Extraction schemas for buyback and stock-exchange OFS sections.

Each value is text exactly as printed, or null. config/event_types.py names
which schema each section uses. The IPO schemas stay in agents/extract.py.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class PrintedEvidence(BaseModel):
    """One copied span that supports one field."""

    field: str
    pdf_index: int
    printed_page: str | None = None
    quote: str

    @field_validator("pdf_index", mode="before")
    @classmethod
    def index_is_int(cls, value: object) -> object:
        """Accept a numeric string. The page tag prints the index as text."""
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return value

    @field_validator("printed_page", mode="before")
    @classmethod
    def printed_is_text(cls, value: object) -> str | None:
        """Store the printed label as text. Null stays null."""
        return None if value is None else str(value)


class _Printed(BaseModel):
    """Base for schemas whose values are printed text: blank becomes null, a number becomes text."""

    @field_validator("*", mode="before")
    @classmethod
    def blank_is_null(cls, value: object) -> object:
        """An empty string is a missing value. Lists (evidence, rows) pass through."""
        if isinstance(value, str):
            return value if value.strip() else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return value


class IntentionRow(_Printed):
    """A promoter or promoter-group member, their holding, and what they say they will tender."""

    name_as_printed: str
    role_as_printed: str | None = None
    shares_held_pre_offer: str | None = None
    shares_intended: str | None = None
    qualifier: str | None = None
    intention_as_printed: str | None = None
    evidence: list[PrintedEvidence] = []


class IntentionHolders(BaseModel):
    """The rows of a promoter-intention section, and the table's printed Total row if any."""

    rows: list[IntentionRow] = []
    table_total_as_printed: str | None = None
    evidence: list[PrintedEvidence] = []

    @field_validator("table_total_as_printed", mode="before")
    @classmethod
    def total_is_text(cls, value: object) -> object:
        """Blank is null; a number becomes text."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return str(value)


class BuybackTerms(_Printed):
    """Price, size and dates of a tender-offer buyback."""

    buyback_price: str | None = None
    maximum_shares: str | None = None
    record_date: str | None = None
    opening_date: str | None = None
    closing_date: str | None = None
    payment_date: str | None = None
    entitlement_ratio: str | None = None
    evidence: list[PrintedEvidence] = []


class ResultRow(_Printed):
    """Shares accepted in the buyback for one named holder."""

    name_as_printed: str
    role_as_printed: str | None = None
    shares_accepted: str | None = None
    evidence: list[PrintedEvidence] = []


class ResultHolders(BaseModel):
    """The rows of a buyback results section."""

    rows: list[ResultRow] = []


class AcceptanceFacts(_Printed):
    """The acceptance ratio printed in a buyback results document."""

    acceptance_ratio: str | None = None
    evidence: list[PrintedEvidence] = []


class OfsSellerRow(_Printed):
    """One seller in a stock-exchange offer for sale, with that seller's own shares if printed."""

    name_as_printed: str
    role_as_printed: str | None = None
    shares_offered: str | None = None
    greenshoe_shares: str | None = None
    qualifier: str | None = None
    evidence: list[PrintedEvidence] = []


class OfsSellerHolders(BaseModel):
    """The sellers named in an OFS notice."""

    rows: list[OfsSellerRow] = []


class OfsTerms(_Printed):
    """Floor price, size and dates of a stock-exchange offer for sale."""

    floor_price: str | None = None
    total_shares_offered: str | None = None
    greenshoe_total: str | None = None
    sale_date: str | None = None
    sale_date_retail: str | None = None
    settlement_as_printed: str | None = None
    evidence: list[PrintedEvidence] = []


class TimetableFacts(_Printed):
    """The scheduled start of trading from an offer document's indicative timetable."""

    listing_date_scheduled: str | None = None
    evidence: list[PrintedEvidence] = []


# schema name -> (model, kind, fields). kind "holders" returns rows; "facts" returns one object.
EVENT_SCHEMAS: dict[str, tuple[type[BaseModel], str, tuple[str, ...]]] = {
    "IntentionHolders": (IntentionHolders, "holders", tuple(f for f in IntentionRow.model_fields if f != "evidence")),
    "BuybackTerms": (BuybackTerms, "facts", tuple(f for f in BuybackTerms.model_fields if f != "evidence")),
    "ResultHolders": (ResultHolders, "holders", tuple(f for f in ResultRow.model_fields if f != "evidence")),
    "AcceptanceFacts": (AcceptanceFacts, "facts", ("acceptance_ratio",)),
    "OfsSellerHolders": (OfsSellerHolders, "holders", tuple(f for f in OfsSellerRow.model_fields if f != "evidence")),
    "OfsTerms": (OfsTerms, "facts", tuple(f for f in OfsTerms.model_fields if f != "evidence")),
    "TimetableFacts": (TimetableFacts, "facts", ("listing_date_scheduled",)),
}
