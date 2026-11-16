"""Read NSE and BSE once and print what came back.

    python -m tools.exchanges --since 7      # days; writes outputs/signals/{deals,insider}.json
    EXCHANGE_SOURCES=off python -m tools.exchanges --since 7    # every source "disabled", no request
"""

from __future__ import annotations

import argparse
import json

from tools import exchanges


def main() -> None:
    """--since DAYS (default 7), --json to print the whole result."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", type=float, default=7.0, help="How many days back to read (at most 31).")
    parser.add_argument("--json", action="store_true", help="Print the whole result as JSON.")
    args = parser.parse_args()
    result = exchanges.read_all(args.since)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    for status in result["sources"]:
        print(f"{status['id']:20} {status['status']:8} items={status['items']:<4} records={status['records']:<4} "
              f"{status['note']}")
    counts = {name: len(rows) for name, rows in result["records"].items()}
    print(f"requests sent: {result.get('requests')}; items: {len(result['items'])}; records: {counts}")


if __name__ == "__main__":
    main()
