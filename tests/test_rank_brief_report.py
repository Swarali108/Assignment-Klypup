"""Ranking, briefs, per-person cost and the report. No network, no API key."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import run
from agents.brief import brief_for, write_briefs
from agents.extract import merge_rows, offer_notes
from agents.identity import family_groups
from agents.people import build_people
from agents.rules_ipo import EMPLOYEE_DISCOUNT_CAVEAT, price_basis, proceeds, retained
from agents.rank import rank_people
from agents.report import build_report
from tools.costs import per_person_cost
from tests.test_extract import _point_run_at, _write_event

URL = "https://example.test/offer.pdf"
NOTICE = "https://example.test/notice.pdf"


def _evidence(field: str, section: str, pdf_index: int = 3, url: str = URL) -> dict:
    return {"field": field, "pdf_index": pdf_index, "printed_page": "12", "quote": "q",
            "section": section, "source_url": url, "field_kept": True}


def _offer(notes: list | None = None) -> dict:
    return {"offer_price": "₹1,352", "listing_date": "March 11, 2026", "notes": notes or [],
            "evidence": [_evidence("offer_price", "announcement", 1, NOTICE),
                         _evidence("listing_date", "announcement", 1, NOTICE)]}


def _rows() -> list[dict]:
    """A person seller, a fund seller, and a promoter who does not sell."""
    return merge_rows([
        {"name_as_printed": "Asha Example", "role_as_printed": "Promoter Selling Shareholder",
         "shares_offered": "45,000", "qualifier": "Up to", "section": "selling_shareholders",
         "evidence": [_evidence("name_as_printed", "selling_shareholders"),
                      _evidence("shares_offered", "selling_shareholders")]},
        {"name_as_printed": "Asha Example", "shares_held_pre_offer": "864,000", "section": "promoter_holding",
         "evidence": [_evidence("name_as_printed", "promoter_holding", 4),
                      _evidence("shares_held_pre_offer", "promoter_holding", 4)]},
        {"name_as_printed": "Example Growth Fund LLP", "role_as_printed": "Investor Selling Shareholders",
         "shares_offered": "2,000,000", "qualifier": "Up to", "section": "selling_shareholders",
         "evidence": [_evidence("name_as_printed", "selling_shareholders", 5),
                      _evidence("shares_offered", "selling_shareholders", 5)]},
        {"name_as_printed": "Ravi Sample", "role_as_printed": "Promoters", "shares_held_pre_offer": "7,000,000",
         "section": "promoter_holding",
         "evidence": [_evidence("name_as_printed", "promoter_holding", 4),
                      _evidence("shares_held_pre_offer", "promoter_holding", 4)]},
    ])


def _people_doc(notes: list | None = None) -> dict:
    no_model = lambda *args: (_ for _ in ()).throw(AssertionError("no model call expected"))
    return build_people({"rows": _rows(), "offer_facts": _offer(notes)}, SimpleNamespace(event_id="sample_ipo"), no_model,
                        as_of=date(2026, 3, 1))


def test_retained_of_zero_shares_says_none_retained():
    person = {"name_as_printed": "Asha Example", "shares_offered": "100", "shares_held_pre_offer": "100",
              "qualifier": None, "seller_status": "verified",
              "evidence": [_evidence("shares_offered", "selling_shareholders"),
                           _evidence("shares_held_pre_offer", "promoter_holding")]}
    figure = retained(person, price_basis(_offer()))
    assert figure["display"] == "none retained"
    assert "crore" not in json.dumps(figure)


def test_middle_name_that_is_another_first_name_links_a_family():
    families = family_groups([{"name": "Ashwini Amit Dixit", "holder_type": "person"},
                              {"name": "Amit Arun Dixit", "holder_type": "person"},
                              {"name": "Ravi Arun Mehta", "holder_type": "person"}])
    assert [group["members"] for group in families] == [["Amit Arun Dixit", "Ashwini Amit Dixit"]]
    assert "the middle name 'amit' of 'Ashwini Amit Dixit' is the first name of 'Amit Arun Dixit'" in families[0]["reasons"][0]


def test_employee_discount_on_the_price_page_adds_a_caveat_to_proceeds():
    pages = [{"pdf_index": 1, "printed_page": None, "source_url": NOTICE,
              "text": "OFFER PRICE: ₹1,352* PER SHARE\n* A DISCOUNT OF ₹128 WAS OFFERED TO ELIGIBLE EMPLOYEES"}]
    notes = offer_notes(_offer(), pages)
    assert notes[0]["kind"] == "employee_discount"
    assert "ELIGIBLE EMPLOYEES" in notes[0]["quote"]
    seller = _people_doc(notes)["people"][0]
    caveats = seller["amounts"]["proceeds"]["caveats"]
    assert caveats[0]["text"] == EMPLOYEE_DISCOUNT_CAVEAT
    assert caveats[0]["source"]["link"] == f"{NOTICE}#page=1"
    assert seller["amounts"]["proceeds"]["display"].startswith("up to ₹6.08 crore")
    assert offer_notes(_offer(), [{**pages[0], "text": "OFFER PRICE: ₹1,352"}]) == []


def test_person_seller_ranks_first_entity_is_separate_and_non_seller_comes_after_sellers():
    people = _people_doc()["people"]
    ranked = rank_people(people)
    names = [entry["name_as_printed"] for entry in ranked["callable"]]
    assert names == ["Asha Example", "Ravi Sample"]
    assert [entry["name_as_printed"] for entry in ranked["entities"]] == ["Example Growth Fund LLP"]
    first, second = ranked["callable"]
    assert first["confidence"] == "medium"
    assert first["money_now_crore"] == "6.08"
    assert Decimal(first["score"]) == Decimal("6.08") * Decimal("0.7") * Decimal("1.0")
    assert Decimal(second["later_value_crore"]) > Decimal(first["money_now_crore"])
    assert (first["call_tier"], second["call_tier"]) == ("cash_now", "holding")
    assert second["rank_reasons"][0].startswith("Holds shares worth ₹")
    assert any(reason.startswith("entity:") for reason in ranked["entities"][0]["rank_reasons"])


def test_brief_with_an_invented_number_falls_back_to_the_template():
    people = _people_doc()["people"]
    ranked = rank_people(people)
    person = next(p for p in people if p["name_as_printed"] == "Asha Example")
    invented = lambda fields, person_id, event_id, **retry: [
        "Asha Example sells up to 45,000 shares.", "That is about ₹7.25 crore.", "Paid at listing."]
    brief = brief_for(person, ranked["callable"][0], "sample_ipo", invented)
    assert brief["brief_source"] == "template"
    assert "7.25" in brief["fallback_reason"]
    assert "7.25" not in " ".join(brief["lines"])
    assert brief["template_problem"] is None
    # Briefs are digit-free: the model writes placeholders and code fills in every number.
    good = lambda fields, person_id, event_id, **retry: [
        "{name} sells {shares_offered} in the offer for sale.",
        "Proceeds are {proceeds}.",
        "Money arrives {timing}."]
    brief = brief_for(person, ranked["callable"][0], "sample_ipo", good)
    assert brief["brief_source"] == "llm"
    assert brief["lines"][0] == "Asha Example sells up to 45,000 shares in the offer for sale."


def test_per_person_cost_adds_up_to_the_event_total():
    people = _people_doc()["people"]
    ids = {p["name_as_printed"]: p["person_id"] for p in people}
    rows = [
        _cost_row("r0", "extract_selling_shareholders", "", "0.004000", False),
        _cost_row("r1", "extract_selling_shareholders", "", "0", True),
        _cost_row("r1", "extract_promoter_holding", "", "0.003000", False),
        _cost_row("r1", "extract_announcement", "", "0.001317", False),
        _cost_row("r1", "identity", "Asha Example | Ravi Sample", "0.010000", False),
        _cost_row("r1", "brief", ids["Asha Example"], "0.000150", False),
    ]
    report = per_person_cost("sample_ipo", "r1", people=people, rows=rows)
    split = sum(row["cost_usd"] for row in report["per_person"])
    fresh = sum(row["fresh_usd"] for row in report["per_person"])
    assert abs(split - report["totals"]["cost_usd"]) < 0.01
    assert abs(fresh - report["totals"]["fresh_usd"]) < 0.01
    assert report["totals"]["fresh_usd"] == 0.018467
    assert report["totals"]["cached_share"] == 0.2
    by_name = {row["name_as_printed"]: row for row in report["per_person"]}
    assert by_name["Example Growth Fund LLP"]["fresh_usd"] > 0
    assert by_name["Ravi Sample"]["cost_usd"] > by_name["Example Growth Fund LLP"]["cost_usd"]


def _cost_row(run_id: str, agent: str, person_id: str, cost: str, cached: bool) -> dict:
    return {"run_id": run_id, "event_id": "sample_ipo", "agent_name": agent, "person_id": person_id,
            "model": "m", "cost_usd": cost, "cached": "true" if cached else "false", "status": "ok",
            "input_tokens": "10", "output_tokens": "5"}


def test_report_has_an_evidence_link_on_every_amount():
    people_doc = _people_doc()
    ranked = rank_people(people_doc["people"])
    briefs = write_briefs(ranked, people_doc["people"], "sample_ipo",
                          call=lambda fields, person_id, event_id, **retry: ["one", "two", "three"])
    spec = SimpleNamespace(event_id="sample_ipo", event_type="ipo", company="Example Ltd",
                           documents=[SimpleNamespace(doc_type="rhp", url=URL)])
    cost = {"run_id": "r1", "totals": {"calls": 1, "cost_usd": 0.0, "fresh_usd": 0.001}, "per_person": []}
    report = build_report(spec, {"unattributed": [], "rejections": []}, people_doc, ranked, briefs, cost)
    amount_lines = [line for line in report.splitlines() if "crore" in line and not line.startswith(">")]
    assert amount_lines
    assert all("#page=" in line for line in amount_lines), [line for line in amount_lines if "#page=" not in line]
    assert "## What we didn't trust" in report
    assert "| 1 | Asha Example |" in report


def test_step_all_writes_every_output_offline(tmp_path, monkeypatch):
    _point_run_at(tmp_path, monkeypatch)
    _write_event(tmp_path)

    def fake_extract(agent_name, messages, schema_name, prompt_version, event_id, person_id=None, model=None):
        if schema_name == "SectionHolders":
            return {"rows": []}
        return {"evidence": []}

    monkeypatch.setattr("agents.extract.llm_call", fake_extract)
    monkeypatch.setattr("agents.brief.llm_call", lambda **kwargs: {"lines": ["a", "b", "c"]})
    assert run.main(["--event", str(tmp_path / "events" / "sample_ipo.json"), "--step", "all"]) == 0
    folder = tmp_path / "outputs" / "sample_ipo"
    for name in ("locate.json", "extract.json", "people.json", "ranked.json", "briefs.json", "cost.json", "report.md"):
        assert (folder / name).is_file(), name


def test_brief_that_guesses_gender_falls_back_to_the_template():
    people = _people_doc()["people"]
    ranked = rank_people(people)
    person = next(p for p in people if p["name_as_printed"] == "Asha Example")
    gendered = lambda fields, person_id, event_id, **retry: [
        "{name} sells {shares_offered} in the offer for sale.",
        "Her proceeds are {proceeds}.",
        "Paid at listing."]
    brief = brief_for(person, ranked["callable"][0], "sample_ipo", gendered)
    assert brief["brief_source"] == "template"
    assert "her" in brief["fallback_reason"]


def test_failed_brief_is_retried_once_with_the_reason():
    people = _people_doc()["people"]
    ranked = rank_people(people)
    person = next(p for p in people if p["name_as_printed"] == "Asha Example")
    seen = []
    good = ["{name} sells {shares_offered}.", "Proceeds are {proceeds}.", "Paid at listing."]

    def fixes_on_retry(fields, person_id, event_id, **retry):
        seen.append(retry)
        return ["{name} sells {shares_offered}.", "That is ₹7.25 crore.", "Paid at listing."] if not retry else good

    brief = brief_for(person, ranked["callable"][0], "sample_ipo", fixes_on_retry)
    assert brief["brief_source"] == "llm"
    assert brief["lines"] == ["Asha Example sells up to 45,000 shares.",
                              "Proceeds are up to ₹6.08 crore, if all offered shares are sold.", "Paid at listing."]
    assert seen[1]["problem"].startswith("writes numbers instead of placeholders: 7.25. The only placeholders you may use:")
    assert [a["problem"] for a in brief["attempts"]] == ["writes numbers instead of placeholders: 7.25", None]
    always_bad = lambda fields, person_id, event_id, **retry: ["only one line"]
    fallback = brief_for(person, ranked["callable"][0], "sample_ipo", always_bad)
    assert fallback["brief_source"] == "template" and len(fallback["attempts"]) == 2


def test_step_check_reads_documents_without_a_model_call(tmp_path, monkeypatch, capsys):
    _point_run_at(tmp_path, monkeypatch)
    _write_event(tmp_path)
    monkeypatch.setattr("agents.extract.llm_call", lambda **kwargs: (_ for _ in ()).throw(AssertionError("model called")))
    assert run.main(["--event", str(tmp_path / "events" / "sample_ipo.json"), "--step", "check"]) == 0
    report = json.loads((tmp_path / "outputs" / "sample_ipo" / "check.json").read_text(encoding="utf-8"))
    document = report["documents"][0]
    assert document["fetched"] == "yes" and document["pages"] == 1 and document["low_text_pages"] == [4]
    assert set(report["lock_in_wording"].values()) == {"not found"}
    assert not (tmp_path / "cost_log.csv").exists()
    assert "lock-in wording" in capsys.readouterr().out



def test_meta_words_and_misplaced_expenses_phrase_fail_the_brief():
    from agents.brief import brief_problem

    fields = {"name": "Asha Example", "event_is": "recent", "event_age": "12 days ago",
              "gain": "up to ₹5.88 crore, before offer expenses and taxes (45,000 × (₹1,352 − ₹46.00) = ₹5.88 crore)",
              "proceeds": "up to ₹6.08 crore (45,000 × ₹1,352 = ₹6.08 crore)"}
    base = ["Asha Example sells up to 45,000 shares.", "Paid at listing."]
    assert "trigger" in brief_problem(base + ["The trigger is recent."], fields)
    assert "confidence" in brief_problem(base + ["Confidence is medium."], fields)
    assert "verified" in brief_problem(base + ["The shares are verified."], fields)
    assert "gain figure" in brief_problem(base + ["Proceeds up to ₹6.08 crore, before offer expenses and taxes."], fields)
    assert brief_problem(base + ["Gain up to ₹5.88 crore, before offer expenses and taxes."], fields) is None


def test_brief_fields_leave_out_confidence_and_reword_pipeline_words():
    people = _people_doc()["people"]
    ranked = rank_people(people)
    person = next(p for p in people if p["name_as_printed"] == "Asha Example")
    from agents.brief import brief_fields, template_brief

    fields = brief_fields(person, ranked["callable"][0])
    assert "confidence" not in fields and "trigger" not in json.dumps(fields).lower()
    assert "verified" not in json.dumps(fields, ensure_ascii=False).lower()
    lines = template_brief(fields)
    assert lines[0].startswith("Asha Example (Promoter Selling Shareholder) sells up to 45,000 shares")
    assert "verified" not in " ".join(lines).lower() and "confidence" not in " ".join(lines).lower()


def test_template_angle_is_one_short_line_from_the_lock_in_status():
    from agents.brief import _RETAINED_ANGLES, brief_problem, template_brief

    fields = {"name": "Asha Example", "role": "Promoter", "why_money": "sells shares in the offer for sale",
              "amount": "₹1 crore", "timing": "at listing", "retained": "₹2 crore (estimate)", "event_is": "recent",
              "retained_shares_timing": "Period A: 36 months from the date of Allotment; Period B: 24 months "
                                        "from the date of Allotment; Period C: 12 months from the date of Allotment"}
    lines = template_brief(fields, "locked_in")
    assert lines[2] == _RETAINED_ANGLES["locked_in"]
    assert brief_problem(lines, fields) is None
    assert template_brief({**fields, "retained": "none retained"}, "locked_in")[2] != lines[2]
    assert "Family" in template_brief({**fields, "family_link": "same surname"}, None)[2]


def test_template_that_still_fails_a_check_is_marked_not_hidden():
    people = _people_doc()["people"]
    ranked = rank_people(people)
    person = next(p for p in people if p["name_as_printed"] == "Asha Example")
    entry = {**ranked["callable"][0], "why_money": "sells " + "many " * 30 + "shares"}
    failing = lambda fields, person_id, event_id, **retry: ["One.", "Two."]
    brief = brief_for(person, entry, "sample_ipo", failing)
    assert brief["brief_source"] == "template"
    assert brief["template_problem"].startswith("line 1 has")


def test_an_employee_discount_sentence_on_another_offer_page_across_lines_is_found():
    url = "https://example.org/offer.pdf"
    offer = {"evidence": [{"field": "offer_price", "pdf_index": 9, "source_url": url, "field_kept": True},
                          {"field": "ofs_size", "pdf_index": 2, "source_url": url, "field_kept": True}]}
    pages = [{"pdf_index": 2, "source_url": url, "printed_page": "", "text":
              "THE COMPANY OFFERED A DISCOUNT OF ₹ 25.00 PER EQUITY SHARE TO\nELIGIBLE EMPLOYEES BIDDING IN THE "
              "EMPLOYEE RESERVATION PORTION. THE NET OFFER FOLLOWS."},
             {"pdf_index": 9, "source_url": url, "printed_page": "7", "text": "The Offer Price is ₹ 271.00."}]
    notes = offer_notes(offer, pages)
    assert len(notes) == 1 and notes[0]["pdf_index"] == 2 and "ELIGIBLE EMPLOYEES" in notes[0]["quote"]


def test_retry_offers_the_lock_in_end_date_as_a_placeholder():
    """A kept-shares lock-in date is offered as {locked_until} on the retry, so the brief need not write digits."""
    from agents.brief import later_values, retry_hint

    person = {"timing": {"retained": {"periods": [
        {"ends_on": "2028-04-21", "status": "locked_until"}, {"ends_on": "2027-04-21", "status": "locked_until"}]}}}
    later = later_values(person)
    assert later == {"locked_until": "21 Apr 2027"}
    hint = retry_hint("writes numbers instead of placeholders: 21, 2027", {"name": "x", **later}, later)
    assert "{locked_until}" in hint and "{name}" in hint
    assert later_values({"timing": {}}) == {}
