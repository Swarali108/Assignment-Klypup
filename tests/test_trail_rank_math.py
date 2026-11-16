"""The trail's rank step shows factors that multiply to the score it shows, for every ranked person on file."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from api.trail import rank_step

ROOT = Path(__file__).resolve().parents[1]
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _factor(value: str) -> Decimal:
    """The number inside a part's value ("₹110.73 Cr" -> 110.73)."""
    found = NUMBER.findall(value.replace(",", ""))
    assert len(found) == 1, value
    return Decimal(found[0])


def _ranked_entries():
    for path in sorted((ROOT / "outputs").glob("*/ranked.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for group in ("callable", "entities", "context"):
            for entry in doc.get(group) or []:
                yield path.parent.name, group, entry


def test_rank_step_factors_multiply_to_score():
    """Every ranked person: product of the shown parts equals the shown score (to the 0.01 it is shown at)."""
    checked, wrong = 0, []
    for event_id, group, entry in _ranked_entries():
        step = rank_step(entry, group)
        product = Decimal(1)
        for part in step["parts"]:
            product *= _factor(part["value"])
        score = Decimal(step["score"])
        checked += 1
        if abs(product - score) > Decimal("0.005"):
            wrong.append(f"{event_id}/{entry['person_id']}: {[p['value'] for p in step['parts']]} -> {product} != {score}")
    assert checked
    assert not wrong, f"{len(wrong)} of {checked} wrong, e.g. {wrong[:5]}"


def test_unlock_by_holding_shows_holding_and_split():
    """sedemac Manish Sharma: ranked by the whole ₹110.73 Cr holding at half weight, not by ₹0."""
    doc = json.loads((ROOT / "outputs" / "sedemac_ipo" / "ranked.json").read_text(encoding="utf-8"))
    entry = next(e for e in doc["callable"] if e["person_id"] == "p_manish_sharma")
    step = rank_step(entry, "callable")
    values = [p["value"] for p in step["parts"]]
    assert values[0] == "₹110.73 Cr"
    assert "0.5" in values[1:]
    # The later score (66.44) did not set this rank, so the step must not say it did.
    assert step["later"] is None or "higher" not in json.dumps(step["later"])
