"""Score the pipeline's call lists against 20 hand-read people. No model calls.

    python -m eval.check_people                 # hit rate per field, per event, overall; every miss listed
    python -m eval.check_people --verify-gold   # also check the gold: quotes on their pages, amounts recomputed
    python -m eval.check_people --json out.json # also write the numbers as JSON

Gold is eval/gold/people_20.json (how it was built is written in its header). For each gold person
this reads outputs/<event_id>/ranked.json (the call list: role, amount, timing as an RM sees them) and
outputs/<event_id>/people.json (shares, price). People are matched by printed name, not by rank.

Seven fields per person: name, role, shares_offered, shares_held_pre_offer, price, amount, timing.
A field where the gold holds a value ends as one of
  hit      the pipeline holds the same value
  wrong    the pipeline holds a different value (the worst outcome; each one is listed)
  missing  the pipeline holds nothing, or never called the person
A field where the gold is blank on purpose (a number the documents do not print) ends as
  blank_ok  the pipeline also says unknown
  invented  the pipeline shows a value the documents do not support
These two groups are reported apart, so people with mostly blank gold fields do not lift the hit rate.

The script is a measurement, not a gate: it exits 0 when there are misses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from agents.locate import normalise
from agents.names import clean_name, name_tokens
from agents.verify import printed_number

ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "eval" / "gold" / "people_20.json"
FIELDS = ("name", "role", "shares_offered", "shares_held_pre_offer", "price", "amount", "timing")
MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_DATE = re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b")
_CRORE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)\s*crore")
AMOUNT_TOLERANCE = Decimal("0.005")  # 0.5%, or 0.01 crore, whichever is larger: printed totals are rounded
_SKIP_NAME_WORDS = {"held", "jointly", "with", "represented", "by"}


# ---------------------------------------------------------------- loading

def load_gold(path: Path = GOLD_PATH) -> dict:
    """Read the gold file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_event(event_id: str, root: Path = ROOT) -> dict | None:
    """{'callable': [...], 'people': {person_id: row}, 'price_basis': {...}} or None when the event was not run."""
    folder = Path(root) / "outputs" / event_id
    ranked, people = _read_json(folder / "ranked.json"), _read_json(folder / "people.json")
    if ranked is None or people is None:
        return None
    return {
        "callable": ranked.get("callable") or [],
        "people": {row.get("person_id"): row for row in people.get("people") or []},
        "price_basis": people.get("price_basis") or {},
    }


# ---------------------------------------------------------------- matching and comparing

def _name_key(name: str) -> str:
    return clean_name(name)


def _core_tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in name_tokens(name) if t not in _SKIP_NAME_WORDS)


def find_entry(gold_person: dict, entries: list[dict]) -> dict | None:
    """The call-list entry for this gold person: exact cleaned name first, then the same set of name words."""
    wanted = [gold_person["name"]["value"], *gold_person["name"].get("accept", [])]
    keys = {_name_key(n) for n in wanted}
    for entry in entries:
        if _name_key(entry.get("name_as_printed") or "") in keys:
            return entry
    cores = {_core_tokens(n) for n in wanted}
    for entry in entries:
        if _core_tokens(entry.get("name_as_printed") or "") in cores:
            return entry
    return None


def _role_key(role: str | None) -> tuple[str, ...]:
    """Role words, lower case, no 'and', plural s dropped: 'PROMOTER SELLING SHAREHOLDERS' == 'Promoter Selling Shareholder'."""
    words = re.findall(r"[a-z0-9]+", normalise(role or ""))
    out = []
    for word in words:
        if word == "and":
            continue
        out.append(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word)
    return tuple(out)


def _number(text) -> Decimal | None:
    try:
        return printed_number(text)
    except (InvalidOperation, ValueError):
        return None


def dates_in(text: str) -> set[str]:
    """Every 'D Mon YYYY' date in the text, as ISO dates."""
    found = set()
    for day, month, year in _DATE.findall(text or ""):
        found.add(f"{int(year):04d}-{MONTHS[month.lower()]:02d}-{int(day):02d}")
    return found


def crore_in(text: str) -> Decimal | None:
    """The first '₹N crore' figure in the text, else None."""
    match = _CRORE.search(text or "")
    return Decimal(match.group(1).replace(",", "")) if match else None


def _within(gold: Decimal, value: Decimal) -> bool:
    return abs(value - gold) <= max(Decimal("0.01"), abs(gold) * AMOUNT_TOLERANCE)


def score_person(gold_person: dict, event: dict | None) -> dict:
    """{field: {'outcome', 'gold', 'pipeline'}} for one gold person. event None means the event was not run."""
    entry = find_entry(gold_person, event["callable"]) if event else None
    row = event["people"].get(entry.get("person_id")) if entry else None
    results = {field: _score_field(field, gold_person, entry, row, event) for field in FIELDS}
    if entry is None:
        for field, result in results.items():
            if result["outcome"] in ("blank_ok", "invented"):
                result["outcome"] = "blank_ok"  # nothing was claimed about a person the list never held
                result["pipeline"] = "(not in the call list)"
            else:
                result["outcome"] = "missing"
                result["pipeline"] = "(not in the call list)"
    return results


def _score_field(field: str, gold_person: dict, entry, row, event) -> dict:
    if entry is None:
        gold_value, blank = _gold_view(field, gold_person)
        return {"outcome": "blank_ok" if blank else "missing", "gold": gold_value, "pipeline": None}
    return _FIELD_SCORERS[field](gold_person, entry, row or {}, event)


def _gold_view(field: str, gold_person: dict) -> tuple[str, bool]:
    """(text of the gold value, is the gold blank on purpose)."""
    if field in ("name", "role"):
        return gold_person[field]["value"], False
    if field in ("shares_offered", "shares_held_pre_offer"):
        item = gold_person.get(field)
        value = None if not item else item["value"]
        return str(value), value is None
    if field == "price":
        return f"{gold_person['price']['kind']} {gold_person['price']['value']}", False
    if field == "amount":
        amount = gold_person["amount"]
        return (f"Rs {amount['expected_crore']} crore", False) if amount["kind"] != "not_printed" else ("not printed", True)
    dates = gold_person["timing"]["dates"]
    return (",".join(dates) if dates else "not printed"), not dates


def _result(outcome: str, gold_value, pipeline) -> dict:
    return {"outcome": outcome, "gold": gold_value, "pipeline": pipeline}


def _score_name(gold_person, entry, row, event):
    gold = gold_person["name"]
    keys = {_name_key(gold["value"]), *(_name_key(n) for n in gold.get("accept", []))}
    printed = entry.get("name_as_printed") or ""
    return _result("hit" if _name_key(printed) in keys else "wrong", gold["value"], printed)


def _score_role(gold_person, entry, row, event):
    gold = gold_person["role"]
    printed = entry.get("role_as_printed")
    if not printed:
        return _result("missing", gold["value"], None)
    keys = {_role_key(gold["value"]), *(_role_key(r) for r in gold.get("accept", []))}
    return _result("hit" if _role_key(printed) in keys else "wrong", gold["value"], printed)


def _shares_scorer(field):
    def score(gold_person, entry, row, event):
        gold = gold_person.get(field)
        pipeline = row.get(field)
        have = pipeline not in (None, "") and _number(pipeline) is not None
        if not gold or gold["value"] is None:
            return _result("invented" if have else "blank_ok", None, pipeline)
        if not have:
            return _result("missing", gold["value"], pipeline)
        return _result("hit" if _number(pipeline) == Decimal(gold["value"]) else "wrong", gold["value"], pipeline)
    return score


def _score_price(gold_person, entry, row, event):
    gold = gold_person["price"]
    basis = event["price_basis"]
    text = f"{basis.get('kind')} {basis.get('low')}-{basis.get('high')}"
    if basis.get("kind") in (None, "unknown"):
        return _result("missing", f"{gold['kind']} {gold['value']}", basis.get("reason") or "unknown")
    try:
        same = (basis["kind"] == gold["kind"] and Decimal(str(basis["low"])) == Decimal(gold["value"])
                and Decimal(str(basis["high"])) == Decimal(gold["value"]))
    except (KeyError, InvalidOperation):
        same = False
    return _result("hit" if same else "wrong", f"{gold['kind']} {gold['value']}", text)


def _score_amount(gold_person, entry, row, event):
    gold = gold_person["amount"]
    shown = entry.get("amount_display") or ""
    number = crore_in(shown)
    if gold["kind"] == "not_printed":
        if number is None:
            return _result("blank_ok", "not printed", shown)
        ceiling = gold.get("max_crore")
        labelled_estimate = "estimate" in shown.lower()
        if ceiling is not None and number <= Decimal(ceiling) and labelled_estimate:
            return _result("blank_ok", f"not printed (ceiling Rs {ceiling} crore)", shown)
        return _result("invented", "not printed", shown)
    want = Decimal(gold["expected_crore"])
    if number is None:
        return _result("missing", f"Rs {want} crore", shown)
    is_cash_label = "not cash" not in shown.lower()
    kind_ok = is_cash_label if gold["kind"] == "cash_proceeds" else not is_cash_label
    return _result("hit" if _within(want, number) and kind_ok else "wrong", f"Rs {want} crore ({gold['kind']})", shown)


def _score_timing(gold_person, entry, row, event):
    gold = gold_person["timing"]
    shown = entry.get("timing_display") or ""
    found = dates_in(shown)
    wanted = gold["dates"]
    if not wanted:
        return _result("invented" if found else "blank_ok", "not printed", shown)
    if not found:
        return _result("missing", ",".join(wanted), shown)
    ok = set(wanted) <= found if gold.get("match") == "all" else bool(set(wanted) & found)
    return _result("hit" if ok else "wrong", f"{gold['match']} of {','.join(wanted)}", shown)


_FIELD_SCORERS = {
    "name": _score_name, "role": _score_role,
    "shares_offered": _shares_scorer("shares_offered"), "shares_held_pre_offer": _shares_scorer("shares_held_pre_offer"),
    "price": _score_price, "amount": _score_amount, "timing": _score_timing,
}


# ---------------------------------------------------------------- scoring everything

def evaluate(gold: dict, root: Path = ROOT) -> dict:
    """Score every gold person. Returns per-person results plus the tallies."""
    events: dict[str, dict | None] = {}
    people_results = []
    for person in gold["people"]:
        event_id = person["event_id"]
        if event_id not in events:
            events[event_id] = load_event(event_id, root)
        people_results.append({"id": person["id"], "event_id": event_id, "name": person["name"]["value"],
                               "fields": score_person(person, events[event_id])})
    return {"people": people_results, "events_missing": sorted(e for e, v in events.items() if v is None),
            "tally": tally(people_results)}


def tally(people_results: list[dict]) -> dict:
    """Per-field counts, per-event value hit rates, and the overall numbers."""
    per_field = {f: {k: 0 for k in ("hit", "wrong", "missing", "blank_ok", "invented")} for f in FIELDS}
    per_event: dict[str, dict] = {}
    fully_right = 0
    for person in people_results:
        event = per_event.setdefault(person["event_id"], {"people": 0, "value_fields": 0, "hits": 0})
        event["people"] += 1
        right = True
        for field, result in person["fields"].items():
            outcome = result["outcome"]
            per_field[field][outcome] += 1
            if outcome in ("hit", "wrong", "missing"):
                event["value_fields"] += 1
                event["hits"] += outcome == "hit"
            right = right and outcome in ("hit", "blank_ok")
        fully_right += right
    value_fields = sum(c["hit"] + c["wrong"] + c["missing"] for c in per_field.values())
    hits = sum(c["hit"] for c in per_field.values())
    blank_fields = sum(c["blank_ok"] + c["invented"] for c in per_field.values())
    return {
        "per_field": per_field, "per_event": per_event,
        "value_fields": value_fields, "hits": hits, "wrong": sum(c["wrong"] for c in per_field.values()),
        "missing": sum(c["missing"] for c in per_field.values()),
        "blank_fields": blank_fields, "blank_ok": sum(c["blank_ok"] for c in per_field.values()),
        "invented": sum(c["invented"] for c in per_field.values()),
        "people": len(people_results), "fully_right": fully_right,
    }


def _pct(num: int, den: int) -> str:
    return f"{100 * num / den:.0f}%" if den else "n/a"


def format_report(result: dict) -> str:
    """The report: per-field table, per-event rates, overall, then every miss."""
    t = result["tally"]
    lines = [f"people checked: {t['people']}  events: {len(t['per_event'])}"]
    for event_id in result["events_missing"]:
        lines.append(f"  event not run (no outputs/{event_id}/ranked.json + people.json): every field there counts as missing")
    lines += ["", "A. fields where the documents print a value (hit rate = hit / all)",
              f"{'field':<24}{'n':>4}{'hit':>5}{'wrong':>7}{'missing':>9}{'hit rate':>10}"]
    for field in FIELDS:
        c = t["per_field"][field]
        n = c["hit"] + c["wrong"] + c["missing"]
        if n:
            lines.append(f"{field:<24}{n:>4}{c['hit']:>5}{c['wrong']:>7}{c['missing']:>9}{_pct(c['hit'], n):>10}")
    lines.append(f"{'ALL value fields':<24}{t['value_fields']:>4}{t['hits']:>5}{t['wrong']:>7}{t['missing']:>9}{_pct(t['hits'], t['value_fields']):>10}")
    lines += ["", "B. fields the documents leave blank (a number not printed): the right answer is 'unknown'",
              f"{'field':<24}{'n':>4}{'blank_ok':>10}{'invented':>10}"]
    for field in FIELDS:
        c = t["per_field"][field]
        n = c["blank_ok"] + c["invented"]
        if n:
            lines.append(f"{field:<24}{n:>4}{c['blank_ok']:>10}{c['invented']:>10}")
    lines.append(f"{'ALL blank fields':<24}{t['blank_fields']:>4}{t['blank_ok']:>10}{t['invented']:>10}  (correctly blank: {_pct(t['blank_ok'], t['blank_fields'])})")
    lines += ["", "C. per event (value fields only)"]
    for event_id, c in t["per_event"].items():
        lines.append(f"{event_id:<56}{c['people']:>3} people  {c['hits']}/{c['value_fields']} = {_pct(c['hits'], c['value_fields'])}")
    lines += ["", f"OVERALL value-field hit rate: {t['hits']}/{t['value_fields']} = {_pct(t['hits'], t['value_fields'])}"
              f"   wrong {t['wrong']}  missing {t['missing']}  invented {t['invented']}",
              f"people with every field right: {t['fully_right']}/{t['people']}", "", "D. every miss"]
    misses = 0
    for person in result["people"]:
        for field, r in person["fields"].items():
            if r["outcome"] in ("wrong", "missing", "invented"):
                misses += 1
                lines.append(f"  [{r['outcome']:<8}] {person['id']:<12} {person['name'][:34]:<34} {field:<22} gold: {r['gold']}  |  pipeline: {r['pipeline']}")
    if not misses:
        lines.append("  none")
    return "\n".join(lines)


# ---------------------------------------------------------------- checking the gold itself

def _squash(text: str) -> str:
    return re.sub(r"\s+", "", normalise(text))


def _all_evidence(person: dict):
    for field in FIELDS:
        item = person.get(field)
        if item is None:
            continue
        evidence = item.get("evidence") or []
        yield field, evidence, item


def verify_gold(gold: dict, root: Path = ROOT, check_quotes: bool = True) -> list[str]:
    """Problems in the gold: missing evidence, an amount that is not shares x price, a quote not on its page.

    Quotes are skipped for a source whose PDF is not in cache/fetch (a clean checkout), not reported as errors.
    """
    problems: list[str] = []
    sources = gold["sources"]
    pages_cache: dict[str, list[dict] | None] = {}

    def pages_for(source: str):
        if source not in pages_cache:
            path = Path(root) / "cache" / "fetch" / f"{hashlib.sha256(sources[source]['url'].encode()).hexdigest()}.bin"
            if not path.is_file():
                pages_cache[source] = None
            else:
                from tools.pdf import pdf_to_pages
                pages_cache[source] = pdf_to_pages(path)
        return pages_cache[source]

    for person in gold["people"]:
        pid = person["id"]
        for field in FIELDS:
            item = person.get(field)
            if field == "amount":
                continue  # computed from the evidenced share count and price; checked by _amount_problems
            if field in ("shares_offered", "shares_held_pre_offer") and item is None:
                continue
            if not (item or {}).get("evidence"):
                problems.append(f"{pid}.{field}: no evidence")
        problems += _amount_problems(person)
        for field, evidence, _ in _all_evidence(person):
            for ev in evidence:
                problems += _evidence_problems(pid, field, ev, sources, pages_for if check_quotes else None)
    return problems


def _amount_problems(person: dict) -> list[str]:
    amount, pid = person["amount"], person["id"]
    if amount["kind"] == "not_printed":
        return []
    source = person["shares_offered"] if amount["kind"] == "cash_proceeds" else person["shares_held_pre_offer"]
    if not source or source["value"] is None:
        return [f"{pid}.amount: no share count to compute from"]
    expected = (Decimal(source["value"]) * Decimal(person["price"]["value"]) / Decimal(10**7)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return [] if Decimal(amount["expected_crore"]) == expected else [f"{pid}.amount: {amount['expected_crore']} != shares x price = {expected}"]


def _evidence_problems(pid: str, field: str, ev: dict, sources: dict, pages_for) -> list[str]:
    where = f"{pid}.{field} ({ev.get('source')} pdf {ev.get('pdf_index')})"
    if ev.get("source") not in sources or not isinstance(ev.get("pdf_index"), int) or not ev.get("quote"):
        return [f"{where}: evidence needs a known source, an integer pdf_index and a quote"]
    if pages_for is None:
        return []
    pages = pages_for(ev["source"])
    if pages is None:
        return []
    page = next((p for p in pages if p["pdf_index"] == ev["pdf_index"]), None)
    if page is None:
        return [f"{where}: no such page"]
    out = []
    if _squash(ev["quote"]) not in _squash(page["text"]):
        out.append(f"{where}: quote not on that page: {ev['quote'][:70]!r}")
    printed = ev.get("printed_page")
    if printed and page.get("printed_page") and str(printed) != str(page["printed_page"]):
        out.append(f"{where}: printed_page {printed} but the page says {page['printed_page']}")
    return out


# ---------------------------------------------------------------- command line

def main(argv: list[str] | None = None) -> int:
    """Print the report. Exit 2 only when the gold file itself is unreadable or fails --verify-gold."""
    parser = argparse.ArgumentParser(description="Score the call lists against hand-read people.")
    parser.add_argument("--gold", default=str(GOLD_PATH), help="Gold file. Default: eval/gold/people_20.json.")
    parser.add_argument("--verify-gold", action="store_true", help="Check the gold's quotes and amounts first.")
    parser.add_argument("--json", metavar="PATH", help="Also write the tallies and every person's results as JSON.")
    args = parser.parse_args(argv)
    gold = load_gold(Path(args.gold))
    status = 0
    if args.verify_gold:
        problems = verify_gold(gold)
        print(f"gold check: {len(problems)} problem(s)" + ("" if problems else " (every quote is on its page, every amount is shares x price)"))
        for problem in problems:
            print(f"  {problem}")
        print()
        status = 2 if problems else 0
    result = evaluate(gold)
    print(format_report(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
