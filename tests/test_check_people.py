"""The 20-person accuracy check: gold structure, the scorer on a fake outputs folder, the report. No model calls.

Hit rates against the live outputs/ are not asserted here: other work re-runs the pipeline and the numbers move.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from eval import check_people
from eval.check_people import (
    FIELDS,
    crore_in,
    dates_in,
    evaluate,
    format_report,
    load_gold,
    main,
    score_person,
    verify_gold,
)

ROOT = Path(__file__).resolve().parents[1]


def test_gold_has_20_people_over_at_least_4_events_and_a_written_rule():
    gold = load_gold()
    assert len(gold["people"]) == 20
    assert len({p["event_id"] for p in gold["people"]}) >= 4
    assert "sha256" in gold["selection_rule"] and "top 3" in gold["selection_rule"]
    header = " ".join(gold["header"]).lower()
    assert "read from the printed source pages" in header and "not copied from the pipeline" in header
    assert gold["skipped_by_rule"], "the picks the rule skipped must be named"
    assert len({p["id"] for p in gold["people"]}) == 20


def test_every_gold_field_has_a_pdf_index_and_a_quote():
    gold = load_gold()
    for person in gold["people"]:
        for field in FIELDS:
            item = person.get(field)
            if field == "amount" or item is None:
                continue
            assert item["evidence"], (person["id"], field)
            for ev in item["evidence"]:
                assert ev["source"] in gold["sources"]
                assert isinstance(ev["pdf_index"], int) and ev["quote"].strip()


def test_gold_amounts_are_shares_times_price_and_structure_is_clean():
    assert verify_gold(load_gold(), check_quotes=False) == []


def test_gold_quotes_are_on_their_pages_when_the_cache_is_present():
    gold = load_gold()
    keys = [hashlib.sha256(s["url"].encode()).hexdigest() for s in gold["sources"].values()]
    if not all((ROOT / "cache" / "fetch" / f"{k}.bin").is_file() for k in keys):
        pytest.skip("source PDFs are not in cache/fetch")
    assert verify_gold(gold) == []


def test_gold_names_no_repo_folder_tracker_or_local_path():
    text = (ROOT / "eval" / "gold" / "people_20.json").read_text(encoding="utf-8").lower()
    for word in (ROOT.name.lower(), "ontrack", "evaluator", "/users/", "scratchpad"):
        assert word not in text


# ---- the scorer on a fake outputs folder ----

def _gold_person(**changes) -> dict:
    person = {
        "id": "t1", "event_id": "ev", "picked_by": "test",
        "name": {"value": "Asha Example", "accept": [], "evidence": []},
        "role": {"value": "Promoter Selling Shareholder", "accept": [], "evidence": []},
        "shares_offered": {"value": 1000, "evidence": []},
        "shares_held_pre_offer": {"value": 5000, "evidence": []},
        "price": {"kind": "offer_price", "value": "100", "evidence": []},
        "amount": {"kind": "cash_proceeds", "expected_crore": "0.01"},
        "timing": {"dates": ["2026-10-21"], "match": "any", "evidence": []},
    }
    person.update(changes)
    return person


def _write_outputs(root: Path, entry: dict, row: dict, price_basis: dict) -> None:
    folder = root / "outputs" / "ev"
    folder.mkdir(parents=True)
    (folder / "ranked.json").write_text(json.dumps({"callable": [entry]}), encoding="utf-8")
    (folder / "people.json").write_text(json.dumps({"price_basis": price_basis, "people": [row]}), encoding="utf-8")


def _entry(**changes) -> dict:
    entry = {"person_id": "p1", "name_as_printed": "ASHA EXAMPLE^", "role_as_printed": "PROMOTER SELLING SHAREHOLDERS",
             "amount_display": "₹0.01 crore", "timing_display": "in hand since about 21 Oct 2026 (25 days ago)"}
    entry.update(changes)
    return entry


def _row(**changes) -> dict:
    row = {"person_id": "p1", "shares_offered": "1,000", "shares_held_pre_offer": "5,000"}
    row.update(changes)
    return row


PRICE = {"kind": "offer_price", "low": "100.00", "high": "100.00"}


def test_scorer_hits_with_different_formatting(tmp_path):
    _write_outputs(tmp_path, _entry(), _row(shares_offered="1,00,000", shares_held_pre_offer="5000"), PRICE)
    # Indian grouping (1,00,000) is the number 100000; case, plural and a footnote mark do not matter
    gold = _gold_person(shares_offered={"value": 100000, "evidence": []})
    result = evaluate({"people": [gold]}, tmp_path)
    assert {f: r["outcome"] for f, r in result["people"][0]["fields"].items()} == {f: "hit" for f in FIELDS}
    assert result["tally"]["hits"] == 7 and result["tally"]["fully_right"] == 1


def test_scorer_reports_wrong_missing_and_invented(tmp_path):
    entry = _entry(role_as_printed=None, amount_display="₹9.99 crore", timing_display="unknown: no date")
    row = _row(shares_offered="2,000", shares_held_pre_offer="5,000")
    _write_outputs(tmp_path, entry, row, {"kind": "unknown", "reason": "no verified price"})
    gold = _gold_person(shares_held_pre_offer=None, timing={"dates": [], "match": "any", "evidence": []})
    fields = evaluate({"people": [gold]}, tmp_path)["people"][0]["fields"]
    assert fields["role"]["outcome"] == "missing"
    assert fields["shares_offered"]["outcome"] == "wrong"
    assert fields["shares_held_pre_offer"]["outcome"] == "invented"
    assert fields["price"]["outcome"] == "missing"
    assert fields["amount"]["outcome"] == "wrong"
    assert fields["timing"]["outcome"] == "blank_ok"


def test_amount_labelled_shares_not_cash_is_wrong_for_a_cash_gold(tmp_path):
    entry = _entry(amount_display="₹0.01 crore (estimate, valued at offer price); shares, not cash")
    _write_outputs(tmp_path, entry, _row(), PRICE)
    assert evaluate({"people": [_gold_person()]}, tmp_path)["people"][0]["fields"]["amount"]["outcome"] == "wrong"


def test_blank_amount_gold_rejects_a_number_over_the_ceiling(tmp_path):
    gold = _gold_person(amount={"kind": "not_printed", "max_crore": "120.00"})
    _write_outputs(tmp_path, _entry(amount_display="₹500.00 crore (estimate)"), _row(), PRICE)
    assert evaluate({"people": [gold]}, tmp_path)["people"][0]["fields"]["amount"]["outcome"] == "invented"
    unknown = _entry(amount_display="unknown: acceptance ratio not printed")
    assert score_person(gold, {"callable": [unknown], "people": {"p1": _row()}, "price_basis": PRICE})["amount"]["outcome"] == "blank_ok"


def test_person_not_in_the_call_list_is_missing_everywhere_a_value_was_expected(tmp_path):
    _write_outputs(tmp_path, _entry(name_as_printed="Someone Else"), _row(), PRICE)
    fields = evaluate({"people": [_gold_person()]}, tmp_path)["people"][0]["fields"]
    assert all(r["outcome"] == "missing" for r in fields.values())


def test_event_that_was_not_run_counts_as_missing(tmp_path):
    result = evaluate({"people": [_gold_person()]}, tmp_path)
    assert result["events_missing"] == ["ev"] and result["tally"]["missing"] == 7


def test_date_and_crore_parsers():
    assert dates_in("locked until 9 Sep 2027 (allotment 9 Mar 2026)") == {"2027-09-09", "2026-03-09"}
    assert crore_in("up to ₹141.96 crore, if all offered shares are sold").__str__() == "141.96"
    assert crore_in("unknown: x") is None


def test_report_lists_every_miss_and_main_exits_zero_on_the_real_gold(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    for line in ("A. fields where the documents print a value", "B. fields the documents leave blank",
                 "OVERALL value-field hit rate", "D. every miss"):
        assert line in out
    for field in FIELDS:
        assert re.search(rf"^{field}\s", out, re.M) or field == "name", field


def test_format_report_with_no_misses(tmp_path):
    _write_outputs(tmp_path, _entry(), _row(), PRICE)
    text = format_report(evaluate({"people": [_gold_person()]}, tmp_path))
    assert "OVERALL value-field hit rate: 7/7 = 100%" in text and text.rstrip().endswith("none")
