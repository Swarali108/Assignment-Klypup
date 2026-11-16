"""Score extract.json field by field against hand-checked people. No model calls.

    python -m eval.check_extract                 # every eval/gold/*_people.json
    python -m eval.check_extract --event-id <id> # one event

Gold is eval/gold/<event_id>_people.json: a list of
{name, shares_offered, shares_held_pre_offer, waca_per_share, source_page}.
People are matched to extract.json rows by clean_name. Each field is one of:
  correct  gold and output hold the same printed number
  wrong    both hold a value and they differ (the worst failure, each one is listed)
  missing  gold holds a value and the output is null, or the person is not in rows
  extra    the output holds a value that gold does not
precision = correct / (correct + wrong). recall = correct / gold fields.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.names import clean_name
from agents.verify import same_printed_value

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("shares_offered", "shares_held_pre_offer", "waca_per_share")
OUTCOMES = ("correct", "wrong", "missing", "extra")


def main(argv: list[str] | None = None) -> int:
    """Print one report per gold file. Exit 1 when a gold or extract file is missing."""
    parser = argparse.ArgumentParser(description="Score extract.json against hand-checked people.")
    parser.add_argument("--event-id", help="Score only this event. Default: every *_people.json.")
    args = parser.parse_args(argv)
    gold_dir = ROOT / "eval" / "gold"
    event_ids = [args.event_id] if args.event_id else _gold_event_ids(gold_dir)
    if not event_ids:
        print(f"no *_people.json in {gold_dir}")
        return 1
    status = 0
    for event_id in event_ids:
        gold_path = gold_dir / f"{event_id}_people.json"
        extract_path = ROOT / "outputs" / event_id / "extract.json"
        absent = [path for path in (gold_path, extract_path) if not path.is_file()]
        for path in absent:
            print(f"{event_id}: missing {path}")
        if absent:
            status = 1
            continue
        print(format_report(event_id, evaluate(load_gold(gold_path), load_rows(extract_path))))
    return status


def load_gold(path: Path) -> list[dict]:
    """Read the gold list. Two entries with the same cleaned name are an error in the gold."""
    people = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(people, list):
        raise ValueError(f"{path} must hold a JSON list of people.")
    seen: set[str] = set()
    for person in people:
        key = clean_name(str(person.get("name") or ""))
        if not key or key in seen:
            raise ValueError(f"{path}: blank or repeated name {person.get('name')!r}.")
        seen.add(key)
    return people


def load_rows(path: Path) -> list[dict]:
    """The kept, merged rows of extract.json. Unattributed rows are not output."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(payload.get("rows") or [])


def evaluate(gold: list[dict], rows: list[dict]) -> dict:
    """Compare every gold person and every output row, one field at a time."""
    by_name = {_row_key(row): row for row in rows if _row_key(row)}
    gold_keys = {clean_name(str(person.get("name") or "")) for person in gold}
    tally = {field: {outcome: 0 for outcome in OUTCOMES} for field in FIELDS}
    wrong: list[dict] = []
    for person in gold:
        key = clean_name(str(person.get("name") or ""))
        row = by_name.get(key) or {}
        for field in FIELDS:
            outcome = compare_field(person.get(field), row.get(field))
            if outcome is None:
                continue
            tally[field][outcome] += 1
            if outcome == "wrong":
                wrong.append(_wrong_item(person, row, field))
    for key, row in by_name.items():
        if key in gold_keys:
            continue
        for field in FIELDS:
            if not _blank(row.get(field)):
                tally[field]["extra"] += 1
    unmatched_gold = [p for p in gold if clean_name(str(p.get("name") or "")) not in by_name]
    unmatched_rows = [row for key, row in by_name.items() if key not in gold_keys]
    return {
        "fields": tally,
        "wrong": wrong,
        "gold_not_in_rows": sorted(str(person.get("name")) for person in unmatched_gold),
        "rows_not_in_gold": sorted(str(row.get("name_as_printed")) for row in unmatched_rows),
    }


def compare_field(gold_value: object, output_value: object) -> str | None:
    """Return correct, wrong, missing or extra. None when both are null."""
    gold_blank = _blank(gold_value)
    output_blank = _blank(output_value)
    if gold_blank and output_blank:
        return None
    if gold_blank:
        return "extra"
    if output_blank:
        return "missing"
    if same_printed_value(str(gold_value), str(output_value)):
        return "correct"
    return "wrong"


def precision_recall(tally: dict) -> tuple[float | None, float | None]:
    """Overall precision and recall across every field. None when the divisor is zero."""
    correct = sum(counts["correct"] for counts in tally.values())
    wrong = sum(counts["wrong"] for counts in tally.values())
    gold_fields = sum(counts["correct"] + counts["wrong"] + counts["missing"] for counts in tally.values())
    precision = correct / (correct + wrong) if correct + wrong else None
    recall = correct / gold_fields if gold_fields else None
    return precision, recall


def format_report(event_id: str, result: dict) -> str:
    """Per-field counts, overall precision and recall, then every wrong value."""
    lines = [f"event {event_id}", f"{'field':<24} {'correct':<8} {'wrong':<8} {'missing':<8} extra"]
    for field in FIELDS:
        counts = result["fields"][field]
        lines.append(
            f"{field:<24} {counts['correct']:<8} {counts['wrong']:<8} {counts['missing']:<8} {counts['extra']}"
        )
    precision, recall = precision_recall(result["fields"])
    lines.append(f"precision {_ratio(precision)}  recall {_ratio(recall)}")
    lines.append(f"wrong values {len(result['wrong'])}")
    for item in result["wrong"]:
        lines.append(
            f"  WRONG {item['name']} {item['field']}: gold {item['gold']} (p. {item['gold_page']}) "
            f"output {item['output']} (pdf {item['output_pages']})"
        )
    lines.append(f"gold people not in rows ({len(result['gold_not_in_rows'])}): {', '.join(result['gold_not_in_rows']) or '-'}")
    lines.append(f"rows not in gold ({len(result['rows_not_in_gold'])}): {', '.join(result['rows_not_in_gold']) or '-'}")
    return "\n".join(lines)


def _wrong_item(person: dict, row: dict, field: str) -> dict:
    """One wrong value with where gold and output say it came from."""
    pages = sorted({str(item.get("pdf_index")) for item in row.get("evidence") or [] if item.get("field") == field})
    return {
        "name": person.get("name"),
        "field": field,
        "gold": person.get(field),
        "gold_page": person.get("source_page"),
        "output": row.get(field),
        "output_pages": ",".join(pages) or "-",
    }


def _gold_event_ids(gold_dir: Path) -> list[str]:
    """Event ids that have a *_people.json gold file."""
    suffix = "_people.json"
    return sorted(path.name[: -len(suffix)] for path in Path(gold_dir).glob(f"*{suffix}"))


def _row_key(row: dict) -> str:
    """The row's cleaned name. extract.json stores it, but recompute when it is absent."""
    return str(row.get("name_clean") or clean_name(str(row.get("name_as_printed") or "")))


def _ratio(value: float | None) -> str:
    """Two decimals, or n/a when there was nothing to divide."""
    return "n/a" if value is None else f"{value:.2f}"


def _blank(value: object) -> bool:
    """True for null or an empty string."""
    return value is None or (isinstance(value, str) and not value.strip())


if __name__ == "__main__":
    raise SystemExit(main())
