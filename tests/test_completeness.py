"""Holder tables checked against their printed totals. No network, no model call."""

from __future__ import annotations

from agents.completeness import UNVERIFIED_SHARES, check_offer_size, check_section, completeness, flag_rows, share_count
from agents.extract import extract_event
from config.event_types import event_config

# The 13 promoter rows the model returned for one real letter of offer, and that table's printed total.
GARWARE_ROWS = ["61,57,400", "50", "1,82,01,250", "45,93,555", "44,06,000", "27,70,695", "22,88,725",
                "14,19,925", "13,74,160", "12,82,000", "10,07,600", "4,40,895", "10,755"]


def _rows(values: list[str], field: str = "shares_held_pre_offer", section: str = "promoter_intention") -> list[dict]:
    return [{"name_as_printed": f"Holder {n}", field: value, "section": section} for n, value in enumerate(values)]


def test_thirteen_rows_against_the_printed_total_are_flagged():
    result = check_section(_rows(GARWARE_ROWS), "shares_held_pre_offer", {"table_total_as_printed": "5,29,70,480"})
    assert result["status"] == "rows missing"
    assert result["extracted_sum"] == "43953010"
    assert result["printed_total_shares"] == "52970480"
    assert result["missing_shares"] == "9017470"
    assert result["rows_summed"] == 13


def test_an_exact_match_passes_and_no_total_is_not_checked():
    rows = _rows(["1,000", "2,500"])
    assert check_section(rows, "shares_held_pre_offer", {"table_total_as_printed": "3,500"})["status"] == "complete"
    assert check_section(rows, "shares_held_pre_offer", {"table_total_as_printed": None})["status"] == "not checked"
    assert check_section(rows, "shares_held_pre_offer", None)["status"] == "not checked"
    assert check_section(rows, "shares_held_pre_offer", {"table_total_as_printed": "Total 3,500 53.36"})["status"] == "not checked"


def test_sellers_are_compared_with_the_offer_size_and_rows_are_flagged():
    rows = _rows(["45,000", "67,500"], "shares_offered", "selling_shareholders") + _rows(["9"], "shares_held_pre_offer", "waca")
    offer = {"ofs_size": "Up to 1,12,600 Equity Shares of face value of ₹10 each"}
    assert share_count(offer["ofs_size"]) == 112600
    results = completeness(event_config("ipo"), rows, {}, offer)
    assert results["selling_shareholders"]["status"] == "not checked"
    assert results["selling_shareholders vs ofs_size"]["status"] == "rows missing"
    assert results["selling_shareholders vs ofs_size"]["missing_shares"] == "100"
    flag_rows(event_config("ipo"), rows, results)
    assert all("flags" not in row for row in rows)
    assert rows[0]["shares_offered"] == "45,000"
    assert check_offer_size(rows[:2], "shares_offered", {"ofs_size": "Up to 1,12,500 Equity Shares"}, "ofs_size")["status"] == "complete"


def test_printed_total_goes_through_verify_and_flags_the_people(monkeypatch):
    url = "https://example.test/lof.pdf"
    text = "Name Number of Equity Shares\nAsha Example 1,000\nRavi Example 2,000\nTotal 9,000"
    pages = [{"pdf_index": 4, "printed_page": "2", "source_url": url, "text": text}]
    located = {"sections": {"promoter_intention": [{"pdf_index": 4, "source_url": url}]}}

    def evidence(field: str, quote: str) -> dict:
        return {"field": field, "pdf_index": 4, "printed_page": "2", "quote": quote}

    def fake_llm_call(agent_name, messages, schema_name, prompt_version, event_id, person_id=None, model=None):
        if schema_name != "IntentionHolders":
            return {"rows": []} if schema_name.endswith("Holders") else {"evidence": []}
        return {
            "rows": [
                {"name_as_printed": "Asha Example", "shares_held_pre_offer": "1,000",
                 "evidence": [evidence("name_as_printed", "Asha Example"), evidence("shares_held_pre_offer", "Asha Example 1,000")]},
                {"name_as_printed": "Ravi Example", "shares_held_pre_offer": "2,000",
                 "evidence": [evidence("name_as_printed", "Ravi Example"), evidence("shares_held_pre_offer", "Ravi Example 2,000")]},
            ],
            "table_total_as_printed": "9,000",
            "evidence": [evidence("table_total_as_printed", "Total 9,000")],
        }

    monkeypatch.setattr("agents.extract.llm_call", fake_llm_call)
    result = extract_event("sample_buyback", located, pages, [], "buyback")
    check = result["completeness"]["promoter_intention"]
    assert check["status"] == "rows missing" and check["missing_shares"] == "6000"
    assert all("flags" not in row for row in result["rows"])
    assert [row["shares_held_pre_offer"] for row in result["rows"]] == ["1,000", "2,000"]


def test_rows_without_a_verified_count_are_values_unverified_and_only_they_are_flagged():
    rows = _rows(["1,000", None, "2,000"])
    result = check_section(rows, "shares_held_pre_offer", {"table_total_as_printed": "9,000"})
    assert result["status"] == "values unverified"
    assert result["note"] == "1 rows have no verified share count; the shortfall may be theirs or may be missing rows"
    config = {"completeness": {"promoter_intention": {"share_field": "shares_held_pre_offer"}}}
    flag_rows(config, rows, {"promoter_intention": result})
    assert [row.get("flags") for row in rows] == [None, [UNVERIFIED_SHARES], None]
    over = check_section(_rows(["5,000", None, "6,000"]), "shares_held_pre_offer", {"table_total_as_printed": "9,000"})
    assert over["status"] == "sum exceeds printed total"


def test_rows_missing_is_retried_once_and_the_complete_retry_is_kept(monkeypatch):
    url = "https://example.test/lof.pdf"
    text = "Name Number of Equity Shares\nAsha Example 1,000\nRavi Example 2,000\nMohan Example 6,000\nTotal 9,000"
    pages = [{"pdf_index": 4, "printed_page": "2", "source_url": url, "text": text}]
    located = {"sections": {"promoter_intention": [{"pdf_index": 4, "source_url": url}]}}
    calls = []

    def row(name: str, shares: str) -> dict:
        return {"name_as_printed": name, "shares_held_pre_offer": shares,
                "evidence": [{"field": "name_as_printed", "pdf_index": 4, "printed_page": "2", "quote": name},
                             {"field": "shares_held_pre_offer", "pdf_index": 4, "printed_page": "2", "quote": f"{name} {shares}"}]}

    def fake_llm_call(agent_name, messages, schema_name, prompt_version, event_id, person_id=None, model=None):
        if schema_name != "IntentionHolders":
            return {"rows": []} if schema_name.endswith("Holders") else {"evidence": []}
        calls.append((len(messages), person_id, messages[-1]["content"]))
        rows = [row("Asha Example", "1,000"), row("Ravi Example", "2,000")]
        if len(messages) > 2:
            rows.append(row("Mohan Example", "6,000"))
        total = {"field": "table_total_as_printed", "pdf_index": 4, "printed_page": "2", "quote": "Total 9,000"}
        return {"rows": rows, "table_total_as_printed": "9,000", "evidence": [total]}

    monkeypatch.setattr("agents.extract.llm_call", fake_llm_call)
    result = extract_event("sample_buyback", located, pages, [], "buyback")
    assert [(n, pid) for n, pid, _ in calls] == [(2, None), (4, "completeness_retry")]
    assert calls[1][2] == ("Your rows sum to 3000 shares. The table's printed Total row is 9,000. "
                           "Rows may be missing. Return every row of the table, with evidence.")
    retry = result["completeness_retries"]["promoter_intention"]
    assert retry["first"] == {"rows": 2, "sum": "3000", "status": "rows missing"}
    assert retry["retry"] == {"rows": 3, "sum": "9000", "status": "complete"}
    assert retry["kept"] == "retry"
    assert result["completeness"]["promoter_intention"]["status"] == "complete"
    assert [r["name_as_printed"] for r in result["rows"]] == ["Asha Example", "Ravi Example", "Mohan Example"]
    assert result["counts"]["promoter_intention"]["kept"] == 6


def test_buyback_total_closes_on_the_shares_to_tender_column():
    from agents.completeness import completeness, flag_rows
    from config.event_types import event_config

    config = event_config("buyback")
    rows = [{"section": "promoter_intention", "shares_intended": "1,000", "shares_held_pre_offer": "1,000"},
            {"section": "promoter_intention", "shares_intended": "500"}]
    totals = {"promoter_intention": {"table_total_as_printed": "1,500"}}
    checks = completeness(config, rows, totals, {})
    assert checks["promoter_intention"]["status"] == "complete"
    assert checks["promoter_intention"]["share_field"] == "shares_intended"
    flag_rows(config, rows, checks)
    assert all(not row.get("flags") for row in rows)
