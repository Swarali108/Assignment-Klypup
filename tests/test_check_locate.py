"""Hit@3 against a fake gold file. No model calls."""

from __future__ import annotations

import json

from eval.check_locate import evaluate, format_report


def test_hit_at_3_uses_only_confirmed_sections(tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "sample.json").write_text(
        json.dumps(
            {
                "event_id": "sample_ipo",
                "sections": {"selling_shareholders": ["2", "9"], "price": ["8"]},
                "unverified": {"waca": ["99"]},
            }
        ),
        encoding="utf-8",
    )
    outputs = tmp_path / "outputs" / "sample_ipo"
    outputs.mkdir(parents=True)
    (outputs / "locate.json").write_text(
        json.dumps(
            {
                "sections": {
                    "selling_shareholders": [
                        {"printed_page": "1"},
                        {"printed_page": "2"},
                        {"printed_page": "3"},
                        {"printed_page": "9"},
                    ],
                    "price": [
                        {"printed_page": "1"},
                        {"printed_page": None},
                        {"printed_page": "4"},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    rows = evaluate(gold, tmp_path / "outputs")
    assert [(row["section"], row["hit"]) for row in rows] == [
        ("selling_shareholders", True),
        ("price", False),
    ]
    assert rows[0]["top3"] == ["1", "2", "3"]
    report = format_report(rows)
    assert "hit rate 1/2 = 0.50" in report
    assert "99" not in report


def test_pdf_index_label_hits_without_the_printed_page(tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "sample.json").write_text(
        json.dumps({"event_id": "sample_ipo", "sections": {"price": ["pdf:20"]}}),
        encoding="utf-8",
    )
    outputs = tmp_path / "outputs" / "sample_ipo"
    outputs.mkdir(parents=True)
    (outputs / "locate.json").write_text(
        json.dumps(
            {
                "sections": {
                    "price": [
                        {"pdf_index": 4, "printed_page": "1"},
                        {"pdf_index": 20, "printed_page": "8"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    rows = evaluate(gold, tmp_path / "outputs")
    assert rows[0]["hit"] is True
    assert rows[0]["gold"] == ["pdf:20"]


def test_people_gold_files_are_not_scored_as_locate_gold(tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "sample_ipo_people.json").write_text(json.dumps([{"name": "Asha Example"}]), encoding="utf-8")
    assert evaluate(gold, tmp_path / "outputs") == []
