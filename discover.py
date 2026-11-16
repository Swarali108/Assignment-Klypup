"""Discover money events in official public sources, then optionally process them.

    python discover.py --since 30d
    python discover.py --since 7d --process 10 --max-cost 1.00

Sources and why each is on or off: config/sources.py. Classification rules:
config/discovery.py. Results: events/auto/*.json, outputs/discovery.json and
outputs/discovery_log.json. It always exits 0: a failed source, item or run is
recorded with its reason. Under GitHub Actions it writes changed=true|false to
$GITHUB_OUTPUT so the workflow commits only when something changed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from tools import discover

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    """Refresh, print a summary, process when asked, and report whether anything changed."""
    args = _parser().parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    started = time.perf_counter()
    before = _fingerprint()
    try:
        report = discover.refresh(_days(args.since), **discover.live_options())
        _print_refresh(report)
        if args.process:
            result = discover.process_events(report, args.process, args.max_cost)
            _print_processing(result)
    except Exception as exc:  # recorded, never raised: a scheduled run must still succeed
        discover.record(ROOT / "outputs", {"event_id": "discovery", "status": "failed",
                                           "reason": f"{type(exc).__name__}: {exc}"[:300],
                                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                           "trace": traceback.format_exc()[-1500:]})
        print(f"discovery failed and was recorded: {exc}")
    changed = _fingerprint() != before
    print(f"took {time.perf_counter() - started:.1f} s; changed={str(changed).lower()}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"changed={str(changed).lower()}\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    """--since, --process, --max-cost."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default="30d", help="How far back to read items: 30d, 7d or 12h.")
    parser.add_argument("--process", type=int, default=0, help="Run the pipeline on up to N new or changed events.")
    parser.add_argument("--max-cost", type=float, default=2.00, help="Stop starting runs once this many US$ are spent.")
    return parser


def _days(text: str) -> float:
    """"30d" -> 30, "12h" -> 0.5. Anything else is an error message, not a guess."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([dh])\s*", text)
    if not match:
        raise SystemExit(f"--since must look like 30d or 12h, not {text!r}")
    value = float(match.group(1))
    return value if match.group(2) == "d" else value / 24


def _fingerprint() -> str:
    """What a commit would contain: event files, discovery results (not their timestamp), runs and model cache."""
    parts = []
    for folder in ("events/auto", "cache/llm"):
        parts += sorted(str(path.relative_to(ROOT)) + str(path.stat().st_size) for path in (ROOT / folder).glob("*.json"))
    discovery = ROOT / "outputs" / "discovery.json"
    if discovery.is_file():
        data = json.loads(discovery.read_text(encoding="utf-8"))
        parts.append(json.dumps({key: data.get(key) for key in ("items", "events", "sources")}, sort_keys=True))
    for name in ("discovery_log.json", "runs.csv"):
        path = ROOT / "outputs" / name
        parts.append(str(path.stat().st_size) if path.is_file() else "")
    return str(hash("|".join(parts)))


def _print_refresh(report: dict) -> None:
    """Sources, items per class, events per status."""
    print(f"refreshed {report['refreshed_at']} (items since {report['window_start']})")
    for source in report["sources"]:
        line = f"  {source['status']:<9} {source['id']:<22} items={source['items']}"
        if source["status"] != "ok" or source.get("note"):
            line += f"  ({source.get('note') or source['reason']})"
        print(line[:220])
    counts = report["counts"]
    print("items per class:", json.dumps(counts["per_class"], ensure_ascii=False))
    print("events:", json.dumps(counts["events_by_status"], ensure_ascii=False))


def _print_processing(result: dict) -> None:
    """One line per processed event, then the spend."""
    for entry in result["processed"]:
        print(f"  {entry['status']:<8} {entry['event_id']:<60} ${float(entry.get('cost_usd') or 0):.4f} "
              f"{entry.get('seconds', '')}s {entry.get('reason', '')}"[:240])
    print(f"processing spent ${result['spent_usd']:.4f} of ${result['max_cost']:.2f}")


if __name__ == "__main__":
    sys.exit(main())
