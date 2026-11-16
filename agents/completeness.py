"""Check a holder table against its own printed total. Code only, no model call.

For each section config/event_types.py lists under "completeness":
  - the verified rows' share field is summed and compared with the verified
    table_total_as_printed (the table's own Total row);
  - for IPO sellers, the same sum is also compared with the verified offer size.
status, first match wins:
  "not checked"                no verified total, or one that is not a single number;
  "sum exceeds printed total"  the verified rows add up to more than the total;
  "values unverified"          some rows have no verified share count, so a shortfall
                               may be theirs rather than missing rows;
  "rows missing"               every row has a value and the sum is below the total;
  "complete"                   the sum equals the total.
Nothing changes an amount or adds a row. Rows without a verified share count get
the flag UNVERIFIED_SHARES; no other row is flagged.
"""

from __future__ import annotations

import re
from decimal import Decimal

from agents.verify import number_tokens, printed_number

UNVERIFIED_SHARES = "share count not verified"
MISMATCH = ("rows missing", "sum exceeds printed total")
_SHARE_COUNT = re.compile(r"(\d[\d,]*)\s+equity\s+shares", re.IGNORECASE)


def check_section(rows: list[dict], share_field: str, total: dict | None) -> dict:
    """Sum of the verified rows' share field against the verified printed table total."""
    printed = (total or {}).get("table_total_as_printed")
    if not printed:
        return {"status": "not checked", "reason": "no verified printed total for this table"}
    return compare(rows, share_field, printed_number(printed), printed, "table total")


def check_offer_size(rows: list[dict], share_field: str, offer_facts: dict, size_field: str) -> dict:
    """Sum of the verified rows' share field against the verified offer size, e.g. the OFS size."""
    printed = offer_facts.get(size_field)
    if not printed:
        return {"status": "not checked", "reason": f"no verified {size_field}"}
    return compare(rows, share_field, share_count(printed), printed, size_field)


def compare(rows: list[dict], share_field: str, target: Decimal | None, printed: str, label: str) -> dict:
    """The comparison and its numbers. A target that is not one clear number is not checked."""
    if target is None:
        return {"status": "not checked", "reason": f"{label} '{printed}' is not a single share count"}
    values = [printed_number(row.get(share_field)) for row in rows]
    extracted = sum((value for value in values if value is not None), Decimal(0))
    unverified = sum(1 for value in values if value is None)
    result = {
        "against": label,
        "printed_total": printed,
        "printed_total_shares": str(target),
        "extracted_sum": str(extracted),
        "rows_summed": len(values) - unverified,
        "rows_without_value": unverified,
        "missing_shares": str(target - extracted),
    }
    if extracted > target:
        return {**result, "status": "sum exceeds printed total"}
    if unverified:
        note = (f"{unverified} rows have no verified share count; the shortfall may be theirs "
                f"or may be missing rows")
        return {**result, "status": "values unverified", "note": note}
    return {**result, "status": "complete" if extracted == target else "rows missing"}


def share_count(text: object) -> Decimal | None:
    """The share count in "Up to 8,000 Equity Shares of face value ₹10": the number before "equity shares".

    A value that is only one number is that number. Anything else is None.
    """
    raw = str(text or "")
    match = _SHARE_COUNT.search(raw)
    if match:
        return number_tokens(match.group(1))[0]
    return printed_number(raw)


def _best_column(rows: list[dict], rule: dict, total: dict | None) -> dict:
    """Check the rule's share column; when it does not close, try the rule's other columns.

    A buyback table may print its Total under the shares-to-tender column, not the holding
    column. The first column whose verified rows add up to the printed total is used.
    """
    first = {**check_section(rows, rule["share_field"], total), "share_field": rule["share_field"]}
    for field in rule.get("other_share_fields", ()):
        other = check_section(rows, field, total)
        if other.get("status") == "complete":
            return {**other, "share_field": field}
    return first


def completeness(config: dict, rows: list[dict], totals: dict[str, dict], offer_facts: dict) -> dict:
    """completeness[section] for every section the event type checks, plus any offer-size check."""
    found: dict = {}
    for section, rule in (config.get("completeness") or {}).items():
        mine = [row for row in rows if row.get("section") == section]
        found[section] = _best_column(mine, rule, totals.get(section))
        if rule.get("offer_size_field"):
            key = f"{section} vs {rule['offer_size_field']}"
            found[key] = check_offer_size(mine, rule["share_field"], offer_facts, rule["offer_size_field"])
    return found


def flag_rows(config: dict, rows: list[dict], results: dict) -> None:
    """Add UNVERIFIED_SHARES to each row, in a checked section, that has no verified share count."""
    for section, rule in (config.get("completeness") or {}).items():
        checked = any(result["status"] != "not checked" for key, result in results.items()
                      if key.split(" vs ")[0] == section)
        if not checked:
            continue
        for row in rows:
            field = (results.get(section) or {}).get("share_field") or rule["share_field"]
            if row.get("section") == section and printed_number(row.get(field)) is None:
                if UNVERIFIED_SHARES not in (row.get("flags") or []):
                    row["flags"] = list(row.get("flags") or []) + [UNVERIFIED_SHARES]
