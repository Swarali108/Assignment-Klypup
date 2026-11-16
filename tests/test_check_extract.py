"""Field-level accuracy against a fake gold file. No model calls."""

from __future__ import annotations

import json

from eval import check_extract
from eval.check_extract import compare_field, evaluate, format_report, precision_recall


def _gold() -> list[dict]:
    return [
        {"name": "Asha Example", "shares_offered": "45,000", "shares_held_pre_offer": "864,000",
         "waca_per_share": "46.00", "source_page": "16"},
        {"name": "Ravi Sample", "shares_offered": "1,800", "shares_held_pre_offer": None,
         "waca_per_share": "352.29", "source_page": "17"},
        {"name": "Not Extracted", "shares_offered": "10", "shares_held_pre_offer": None,
         "waca_per_share": None, "source_page": "17"},
    ]


def _rows() -> list[dict]:
    return [
        {"name_as_printed": "Asha Example^", "name_clean": "asha example", "shares_offered": "45000",
         "shares_held_pre_offer": "864,000", "waca_per_share": "46", "evidence": []},
        {"name_as_printed": "Ravi Sample", "name_clean": "ravi sample", "shares_offered": "1,900",
         "shares_held_pre_offer": "6,000", "waca_per_share": None,
         "evidence": [{"field": "shares_offered", "pdf_index": 21}]},
        {"name_as_printed": "Only In Output", "name_clean": "only in output", "shares_offered": None,
         "shares_held_pre_offer": "5", "waca_per_share": None, "evidence": []},
    ]


def test_compare_field_outcomes():
    assert compare_field("71,50,500", "7150500") == "correct"
    assert compare_field("46.00", "46") == "correct"
    assert compare_field("100", "200") == "wrong"
    assert compare_field("100", None) == "missing"
    assert compare_field(None, "100") == "extra"
    assert compare_field(None, "") is None


def test_evaluate_counts_each_field_and_lists_wrong_values():
    result = evaluate(_gold(), _rows())
    fields = result["fields"]
    assert fields["shares_offered"] == {"correct": 1, "wrong": 1, "missing": 1, "extra": 0}
    assert fields["shares_held_pre_offer"] == {"correct": 1, "wrong": 0, "missing": 0, "extra": 2}
    assert fields["waca_per_share"] == {"correct": 1, "wrong": 0, "missing": 1, "extra": 0}
    assert result["wrong"] == [
        {"name": "Ravi Sample", "field": "shares_offered", "gold": "1,800", "gold_page": "17",
         "output": "1,900", "output_pages": "21"}
    ]
    assert result["gold_not_in_rows"] == ["Not Extracted"]
    assert result["rows_not_in_gold"] == ["Only In Output"]
    precision, recall = precision_recall(fields)
    assert precision == 3 / 4
    assert recall == 3 / 6
    report = format_report("sample_ipo", result)
    assert "precision 0.75  recall 0.50" in report
    assert "WRONG Ravi Sample shares_offered: gold 1,800 (p. 17) output 1,900 (pdf 21)" in report


def test_main_reports_a_missing_gold_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_extract, "ROOT", tmp_path)
    (tmp_path / "eval" / "gold").mkdir(parents=True)
    assert check_extract.main(["--event-id", "sample_ipo"]) == 1
    assert "missing" in capsys.readouterr().out


def test_main_scores_a_gold_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_extract, "ROOT", tmp_path)
    gold_dir = tmp_path / "eval" / "gold"
    gold_dir.mkdir(parents=True)
    (gold_dir / "sample_ipo_people.json").write_text(json.dumps(_gold()), encoding="utf-8")
    out = tmp_path / "outputs" / "sample_ipo"
    out.mkdir(parents=True)
    (out / "extract.json").write_text(json.dumps({"rows": _rows()}), encoding="utf-8")
    assert check_extract.main([]) == 0
    assert "event sample_ipo" in capsys.readouterr().out
