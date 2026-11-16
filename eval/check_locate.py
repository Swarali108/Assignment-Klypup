"""Score locate.json against eval/gold. No model calls.

Only the "sections" object is scored. "unverified" is a note for a human and is
not part of the hit rate. Gold page numbers live in those JSON files, not in code.
Files named *_people.json are extraction gold for check_extract.py and are skipped here.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Print gold pages, the top three printed pages, hit@3, and the hit rate."""
    print(format_report(evaluate(ROOT / "eval" / "gold", ROOT / "outputs")))
    return 0


def evaluate(gold_dir: Path, outputs_dir: Path) -> list[dict]:
    """Compare each gold section with the top three printed pages in locate.json."""
    rows: list[dict] = []
    for path in sorted(Path(gold_dir).glob("*.json")):
        if path.name.endswith("_people.json"):
            continue
        gold = json.loads(path.read_text(encoding="utf-8"))
        event_id = str(gold.get("event_id") or path.stem)
        locate_path = Path(outputs_dir) / event_id / "locate.json"
        located = None
        if locate_path.is_file():
            located = json.loads(locate_path.read_text(encoding="utf-8"))
        sections = gold.get("sections") or {}
        for section, gold_pages in sections.items():
            hits = _top_hits(located, section)
            top3 = [_printed(hit) for hit in hits]
            labels = [str(page) for page in gold_pages]
            rows.append(
                {
                    "event_id": event_id,
                    "section": section,
                    "gold": labels,
                    "top3": top3,
                    "hit": _gold_hit(labels, hits),
                    "missing": located is None,
                }
            )
    return rows


def format_report(rows: list[dict]) -> str:
    """Render one line per section and the overall hit rate."""
    lines = [_section_line(row) for row in rows]
    hits = sum(1 for row in rows if row["hit"])
    total = len(rows)
    rate = hits / total if total else 0
    lines.append(f"hit rate {hits}/{total} = {rate:.2f}")
    return "\n".join(lines)


def _section_line(row: dict) -> str:
    """One section: gold pages, top three printed pages, and whether any gold page hit."""
    gold = ",".join(row["gold"]) or "-"
    top3 = ",".join(_show(page) for page in row["top3"]) or "-"
    flag = "true" if row["hit"] else "false"
    missing = " missing" if row["missing"] else ""
    return (
        f"{row['event_id']} {row['section']} gold={gold} top3={top3} "
        f"hit@3={flag}{missing}"
    )


def _top_hits(located: dict | None, section: str) -> list[dict]:
    """The first three hits. An empty list means the section was absent."""
    if located is None:
        return []
    hits = (located.get("sections") or {}).get(section) or []
    return list(hits[:3])


def _gold_hit(labels: list[str], hits: list[dict]) -> bool:
    """True when a gold label is in the top three.

    A printed page matches the printed label. "pdf:N" matches pdf_index N.
    """
    printed = [page for page in (_printed(hit) for hit in hits) if page]
    for label in labels:
        if label.startswith("pdf:") and label[4:].isdigit():
            index = int(label[4:])
            if any(hit.get("pdf_index") == index for hit in hits):
                return True
            continue
        if label in printed:
            return True
    return False


def _printed(hit: dict) -> str | None:
    """The printed page as text, or None when locate stored null."""
    value = hit.get("printed_page")
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def _show(page: str | None) -> str:
    """Print a missing printed page as a dash."""
    return page if page else "-"


if __name__ == "__main__":
    raise SystemExit(main())
