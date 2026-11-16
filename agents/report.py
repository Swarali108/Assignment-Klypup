"""Write report.md from the outputs on disk. Code only; nothing is recomputed.

Every amount is printed with links to the pages that verified its inputs
(url#page=N), so each figure in the report can be traced.
"""

from __future__ import annotations

from collections import Counter

from tools.people_index import STOP_RULES
from decimal import Decimal



def build_report(spec, extracted: dict, people_doc: dict, ranked: dict, briefs: list[dict], cost: dict) -> str:
    """The whole report as Markdown."""
    people = {person["person_id"]: person for person in people_doc["people"]}
    brief_by_id = {brief["person_id"]: brief for brief in briefs}
    parts = [
        f"# Call list: {spec.company} ({spec.event_type})",
        _event_section(spec, people_doc),
        "## Ranked people",
        _table(ranked["callable"], people),
        "## Briefs",
        *[_person_section(entry, people[entry["person_id"]], brief_by_id.get(entry["person_id"])) for entry in ranked["callable"]],
        "## Entities (not called directly)",
        _table(ranked["entities"], people),
        "## No money from this event (context, not called)",
        _context_table(ranked.get("context") or []),
        "## Follow-on: also seen in other processed events",
        _follow_on_section(people_doc),
        "## What we didn't trust",
        _distrust_section(extracted, people_doc),
        "## Cost",
        _cost_section(cost),
    ]
    return "\n\n".join(part for part in parts if part) + "\n"


def figure_links(figure: dict) -> str:
    """Markdown links to every page behind a figure's inputs, or "no evidence link"."""
    links: list[str] = []
    for item in figure.get("inputs") or []:
        for evidence in item.get("evidence") or []:
            if evidence.get("link"):
                link = f"[{item['field']} {_page_label(evidence)}]({evidence['link']})"
                if link not in links:
                    links.append(link)
    return ", ".join(links) or "no evidence link"


def _event_section(spec, people_doc: dict) -> str:
    """Type, documents, price basis and listing date."""
    price = people_doc.get("price_basis") or {}
    listing = people_doc.get("listing") or {}
    lines = [
        "## Event",
        f"- Event id: {spec.event_id}",
        f"- Type: {spec.event_type}",
        f"- Company: {spec.company}",
        "- Documents:" if spec.documents else "- Documents: none (built from exchange records)",
        *[f"  - {doc.doc_type}: {doc.url}" for doc in spec.documents],
        *_records_lines(people_doc),
    ]
    if price.get("kind") not in (None, "unknown") and price.get("low"):
        value = _rupees(price["low"]) if price["low"] == price["high"] else f"{_rupees(price['low'])} to {_rupees(price['high'])}"
        lines.append(f"- Price basis: {price['kind']} {value} ({figure_links(price)})")
    else:
        lines.append(f"- Price basis: unknown ({price.get('reason', 'not verified')})")
    if listing.get("status") == "verified":
        lines.append(f"- Listing date: {listing['date_as_printed']} ({figure_links(listing)})")
    elif listing.get("status") == "scheduled":
        lines.append(f"- Listing date: scheduled for {listing['date_as_printed']} per the offer document's timetable; "
                     f"not confirmed by a listing notice ({figure_links(listing)})")
    elif listing:
        lines.append(f"- Listing date: unknown ({listing.get('reason', 'not verified')})")
    allotment = people_doc.get("allotment") or {}
    if allotment.get("status") == "verified":
        lines.append(f"- Allotment date: {allotment['date_as_printed']} ({figure_links(allotment)})")
    elif allotment:
        lines.append(f"- Allotment date: unknown ({allotment.get('reason', 'not verified')})")
    for key, label in (("buyback_dates", "Buyback dates"), ("sale", "Sale")):
        if people_doc.get(key):
            lines.append(f"- {label}: {_facts_text(people_doc[key])}")
    return "\n".join(lines)


def _records_lines(people_doc: dict) -> list[str]:
    """For a structured event: the records file, its sources' status, and each record's link and row."""
    source = people_doc.get("records_source")
    if not source:
        return []
    lines = [f"- Exchange records: {source.get('records_used', 0)} used from {source.get('records_file')} "
             f"(refreshed {source.get('refreshed_at') or 'unknown'})"]
    for name, status in sorted((source.get("source_status") or {}).items()):
        lines.append(f"  - source {name}: {status if not isinstance(status, dict) else _facts_text(status)}")
    if source.get("records_missing"):
        lines.append(f"  - record ids not in the file (not used): {', '.join(source['records_missing'])}")
    for person in people_doc.get("people") or []:
        for item in person.get("evidence") or []:
            if item.get("link"):
                lines.append(f"  - [{item.get('row_ref') or item.get('record_id')}]({item['link']}): {item.get('quote')}")
    return lines


def _facts_text(facts: dict) -> str:
    """Event-level facts as "key: value" pairs. A missing value reads "unknown"."""
    parts = []
    for key, value in facts.items():
        if isinstance(value, dict):
            value = value.get("display") or value.get("reason") or "unknown"
        parts.append(f"{key.replace('_', ' ')}: {value if value not in (None, '') else 'unknown'}")
    return "; ".join(parts)


def _table(entries: list[dict], people: dict) -> str:
    """Rank, name, role, why money, amount (with links), timing, confidence."""
    if not entries:
        return "None."
    rows = [
        "| Rank | Name | Role | Why money | Amount | Timing | Confidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        person = people[entry["person_id"]]
        cells = [
            str(entry["rank"]),
            entry["name_as_printed"],
            entry.get("role_as_printed") or "unknown",
            entry["why_money"],
            _amount_cell(entry, person),
            entry["timing_display"],
            entry["confidence"],
        ]
        rows.append("| " + " | ".join(_cell(text) for text in cells) + " |")
    return "\n".join(rows)


def _context_table(entries: list[dict]) -> str:
    """Holders who get no money from this event, with the reason."""
    if not entries:
        return "None."
    rows = ["| Name | Role | Why no money |", "| --- | --- | --- |"]
    for entry in entries:
        cells = [entry["name_as_printed"], entry.get("role_as_printed") or "unknown", entry["context_reason"]]
        rows.append("| " + " | ".join(_cell(text) for text in cells) + " |")
    return "\n".join(rows)


def _amount_cell(entry: dict, person: dict) -> str:
    """The headline amount, followed by links when it is a computed figure."""
    figure = _headline_figure(person)
    if figure is None:
        return entry["amount_display"]
    return f"{entry['amount_display']} ({figure_links(figure)})"


def _headline_figure(person: dict) -> dict | None:
    """The computed figure behind amount_display: proceeds, else retained."""
    for key in ("proceeds", "retained"):
        figure = person["amounts"].get(key) or {}
        if figure.get("status") == "computed":
            return figure
        if key == "proceeds" and person.get("seller_status") in ("verified", "unverified"):
            return None
    return None


def _person_section(entry: dict, person: dict, brief: dict | None) -> str:
    """Brief, amounts with working, timing with sources, confidence and family."""
    lines = [f"### {entry['rank']}. {person['name_as_printed']}"]
    if brief:
        lines.extend(f"> {line}" for line in brief["lines"])
        source = brief["brief_source"] + (f" ({brief['fallback_reason']})" if brief.get("fallback_reason") else "")
        lines.append(f"\n- Brief source: {source}")
        if brief.get("template_problem"):
            lines.append(f"- Template brief still fails a check: {brief['template_problem']}")
    else:
        lines.append("- Brief: unknown (no brief written)")
    for key, figure in person["amounts"].items():
        lines.append(_figure_line(key.replace("_", " ").capitalize(), figure))
    for key, timing in person["timing"].items():
        lines.append(_timing_line(f"{key.replace('_', ' ').capitalize()} timing", timing))
    lines.append(f"- Confidence: {person['confidence']['level']} ({'; '.join(person['confidence']['reasons'])})")
    family = person.get("family_group")
    lines.append(f"- Family: {family['id']}: {family['reason']}" if family else "- Family: none found")
    lines.append(f"- Also seen in: {also_seen_in(person)}")
    lines.append(_rank_line(entry, person))
    return "\n".join(lines)


def _rank_line(entry: dict, person: dict) -> str:
    """Rank reasons, with links for the figure the score was built from."""
    line = f"- Rank reasons: {'; '.join(entry['rank_reasons'])}"
    key = "proceeds" if entry.get("call_tier", "cash_now" if entry["tier"] == "seller" else "holding") == "cash_now" else "retained"
    figure = person["amounts"].get(key) or {}
    if figure.get("status") == "computed":
        line += f"; evidence: {figure_links(figure)}"
    return line


def _figure_line(label: str, figure: dict) -> str:
    """One amount with its working, links and caveats, or the reason it is unknown."""
    status = figure.get("status")
    if status == "computed":
        line = f"- {label}: {figure['display']}; working: {figure['working']}; evidence: {figure_links(figure)}"
        for caveat in figure.get("caveats") or []:
            link = caveat["source"].get("link")
            line += f"; caveat: {caveat['text']}" + (f" ([source]({link}))" if link else "")
        return line
    if status == "none":
        return f"- {label}: none retained ({figure.get('working', '')}; evidence: {figure_links(figure)})"
    if status == "not_tendering":
        return f"- {label}: not tendering ({figure.get('reason', '')}; evidence: {figure_links(figure)})"
    if status == "shares_only":
        return f"- {label}: {figure['shares_display']}; value unknown: {figure['reason']}"
    word = "not applicable" if status == "not_applicable" else "unknown"
    return f"- {label}: {word} ({figure.get('reason', 'not verified')})"


def _timing_line(label: str, timing: dict) -> str:
    """When, with the rule's source pages."""
    status = timing.get("status")
    if status in ("settles", "after_date", "scheduled"):
        printed = f"; settlement as printed: \"{timing['settlement_as_printed']}\"" if timing.get("settlement_as_printed") else ""
        return f"- {label}: {timing['when']}{printed} ({figure_links({'inputs': timing.get('sources') or []})})"
    if status in ("at_listing", "in_hand"):
        text = timing["when"]
    elif status in ("locked_in", "unlocked", "partly_unlocked"):
        text = f"{timing.get('display') or 'locked in: ' + timing['period']}. {timing['note']}"
    else:
        word = "not applicable" if status == "not_applicable" else "unknown"
        return f"- {label}: {word} ({timing.get('reason', 'not verified')})"
    sources = "; ".join(rule_citation(source) for source in timing.get("sources") or [] if source.get("url"))
    todo = f" TODO: {timing['todo']}" if timing.get("todo") else ""
    return f"- {label}: {text} (rule {timing['rule']}: {sources}).{todo}"


def rule_citation(source: dict) -> str:
    """A rule's page link and the sentence quoted from this event's document."""
    quotes = " … ".join(f'"{quote}"' for quote in source.get("quotes") or [])
    return f"[{_page_label(source)}]({source['url']}#page={source['pdf_index']}) {quotes}".strip()


def also_seen_in(person: dict) -> str:
    """One line: the other processed events this person matches, with each match's strength."""
    matches = person.get("follow_on")
    if matches is None:
        return "unknown (no index lookup in this run)"
    if not matches:
        return "none found in processed events"
    return "; ".join(
        f"{match['event_id']} ({match['company']}): {match['role'] or 'role unknown'}, {match['amount']} [{match['match_strength']}]"
        for match in matches
    )


def _follow_on_section(people_doc: dict) -> str:
    """Every cross-event match, then the stop rules."""
    lines = ["| Person | Other event | Company | Role there | Amount there | Strength |", "| --- | --- | --- | --- | --- | --- |"]
    count = 0
    for person in people_doc["people"]:
        for match in person.get("follow_on") or []:
            count += 1
            cells = [person["name_as_printed"], match["event_id"], match["company"], match["role"] or "unknown",
                     match["amount"], match["match_strength"]]
            lines.append("| " + " | ".join(_cell(text) for text in cells) + " |")
    if not count:
        lines = ["No matches in other processed events."]
    counts = people_doc.get("counts") or {}
    lines.append(f"\nIndex lookups: {counts.get('index_lookups', 'unknown')}; matches: {counts.get('follow_on_matches', 'unknown')}.")
    lines.append("Stop rules: " + "; ".join(STOP_RULES) + ".")
    return "\n".join(lines)


def _distrust_section(extracted: dict, people_doc: dict) -> str:
    """Unattributed rows, rejection counts, and identity pairs sent to the model."""
    lines = ["### Holder table completeness (verified rows summed against the printed total)"]
    lines.extend(completeness_lines(extracted.get("completeness") or {}) or ["- no table this event type checks"])
    lines.append("")
    lines.append("### Unattributed rows (name failed verification; their amounts are not used)")
    unattributed = extracted.get("unattributed") or []
    lines.extend(f"- {row.get('section')}: {row.get('name_as_printed')} ({row.get('reason')})" for row in unattributed)
    if not unattributed:
        lines.append("- none")
    lines.append("\n### Rejected fields by section and reason")
    counts = Counter((item.get("section"), item.get("reason")) for item in extracted.get("rejections") or [])
    lines.append("| Section | Reason | Count |\n| --- | --- | --- |")
    lines.extend(f"| {section} | {reason} | {count} |" for (section, reason), count in sorted(counts.items()))
    lines.append("\n### Identity decisions sent to the model")
    sent = [item for item in people_doc.get("identity_log") or [] if item.get("method", "").startswith("llm")]
    lines.extend(f"- {' / '.join(item['pair'])}: {item.get('llm_outcome')} ({item.get('llm_reason', '')})" for item in sent)
    if not sent:
        lines.append("- none: every pair was settled by code")
    return "\n".join(lines)


def completeness_lines(results: dict) -> list[str]:
    """One line per completeness check, with the numbers when it was checked."""
    lines = []
    for key, result in results.items():
        if result["status"] == "not checked":
            lines.append(f"- {key}: not checked ({result['reason']})")
            continue
        line = (
            f"- {key}: {result['status']}: printed {result['against']} {result['printed_total']} "
            f"({result['printed_total_shares']} shares), verified rows sum to {result['extracted_sum']} "
            f"over {result['rows_summed']} rows"
        )
        if result["status"] == "rows missing":
            line += f"; {result['missing_shares']} shares not accounted for, so rows may be missing from this table"
        elif result["status"] == "sum exceeds printed total":
            line += f"; the rows add up to {result['missing_shares'].lstrip('-')} shares more than the total"
        elif result["status"] == "values unverified":
            line += f"; {result['missing_shares']} shares not accounted for. {result['note']}"
        if result.get("rows_without_value"):
            line += f". Rows without a verified share count are flagged \"share count not verified\""
        lines.append(line + ". No amount was changed.")
    return lines


def _cost_section(cost: dict) -> str:
    """Run totals and the per-person split."""
    totals = cost.get("totals") or {}
    wall = totals.get("wall_s")
    lines = [
        f"- Run: {cost.get('run_id') or 'unknown'}",
        f"- Model calls: {totals.get('calls', 0)} ({totals.get('cached_calls', 0)} cached)",
        f"- Cost this run: ${totals.get('cost_usd', 0):.6f}; with no cache: ${totals.get('fresh_usd', 0):.6f}",
        f"- Tokens: {totals.get('input_tokens', 0)} in, {totals.get('output_tokens', 0)} out",
        f"- Wall time: {wall:.1f} s" if isinstance(wall, (int, float)) else "- Wall time: unknown",
        "",
        "| Person | Cost this run (USD) | With no cache (USD) | Calls |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {_cell(row.get('name_as_printed') or row['person_id'])} | {row['cost_usd']:.6f} | {row['fresh_usd']:.6f} | {row['calls']} |"
        for row in cost.get("per_person") or []
    )
    return "\n".join(lines)


def _rupees(value: str) -> str:
    """"1250" as "₹1,250"."""
    return f"₹{Decimal(value):,}"


def _page_label(evidence: dict) -> str:
    """"p. 16" when the printed page is known, else "pdf 20"; an exchange record's row reference as printed."""
    if evidence.get("row_ref"):
        return str(evidence["row_ref"])
    printed = evidence.get("printed_page")
    return f"p. {printed}" if printed not in (None, "") else f"pdf {evidence.get('pdf_index')}"


def _cell(text: str) -> str:
    """Make text safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")
