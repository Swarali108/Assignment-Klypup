"""Markdown exports: a whole conversation (export.md) and one person's call pack (callpack.md). Code only, $0.

Nothing here calls a model. Exports carry what the RM saw (answers, cards as tables, sources as links to the
public filings, per-turn cost) and never anything secret: confirm tokens, session data, emails, internal ids and
step internals are never copied (each line is built from named fields), and every cell is flattened to one line.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from api.chat import script, tools

def _cell(value: object) -> str:
    """One table cell: a single line, pipes escaped."""
    text = " ".join(str(value if value is not None else "").split())
    return text.replace("|", "\\|") or "—"


def _table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def _source_links(item: dict) -> list[str]:
    """'[Red herring prospectus p. 18](https://...)' for each name / amount source on a call card."""
    refs = list(item.get("name_evidence") or [])
    for figure in item.get("amounts") or []:
        for inp in figure.get("inputs") or []:
            refs.extend(inp.get("evidence") or [])
    seen, out = set(), []
    for ref in refs:
        url = ref.get("source_url")
        if not url or not url.startswith(("http://", "https://")):
            continue
        page = ref.get("printed_page") or ref.get("pdf_index")
        label = f"{ref.get('doc_label') or 'Source'}" + (f" p. {page}" if page else "")
        key = (url, page)
        if key not in seen:
            seen.add(key)
            anchor = f"#page={ref['pdf_index']}" if ref.get("pdf_index") else ""
            out.append(f"[{label}]({url}{anchor})")
    return out[:8]


def card_md(card: dict) -> str:
    """One chat card as Markdown."""
    kind, title, items = card.get("kind"), card.get("title") or "", card.get("items") or []
    head = f"**{title}**" + (f" (showing {len(items)} of {card['total']})" if card.get("total", 0) > len(items) else "")
    if card.get("outside_window"):
        head += f" — outside {card['outside_window'].get('words')} ({card['outside_window'].get('span')})"
    if kind == "people":
        rows = [[n, (i.get("person") or {}).get("name"), (i.get("person") or {}).get("role"),
                 (i.get("event") or {}).get("company"), (i.get("amount") or {}).get("display"),
                 (i.get("timing") or {}).get("label"), (i.get("confidence") or {}).get("level")]
                for n, i in enumerate(items, start=1)]
        return head + "\n\n" + _table(["#", "Name", "Role", "Company", "Money", "When", "Confidence"], rows)
    if kind == "person" and items:
        item = items[0]
        rows = [["Role", (item.get("person") or {}).get("role")], ["Company", (item.get("event") or {}).get("company")],
                ["Event", (item.get("event") or {}).get("type_label")], ["Tier", item.get("tier_label")],
                ["Money", (item.get("amount") or {}).get("display")], ["When", (item.get("timing") or {}).get("label")],
                ["Confidence", (item.get("confidence") or {}).get("level")], ["Why now", item.get("why_now") or item.get("why")]]
        if (item.get("match") or {}).get("unsure"):
            rows.append(["Unsure match", item["match"].get("reason")])
        text = head + "\n\n" + _table(["Field", "Value"], rows)
        brief = (item.get("brief") or {}).get("lines") or []
        if brief:
            text += "\n\nBrief:\n" + "\n".join(f"- {_cell(line)}" for line in brief)
        links = _source_links(item)
        if links:
            text += "\n\nSources: " + " · ".join(links)
        return text
    if kind == "events":
        rows = [[i.get("company"), i.get("type_label"), i.get("status"), i.get("people_count"), i.get("cash_cr"),
                 (i.get("money_date") or {}).get("display")] for i in items]
        return head + "\n\n" + _table(["Company", "Type", "Status", "People", "Cash (₹ Cr)", "Money date"], rows)
    if kind == "calendar":
        rows = [[i.get("display"), i.get("label"), (i.get("event") or {}).get("company"), i.get("people_count"),
                 i.get("total_cr")] for i in items]
        return head + "\n\n" + _table(["Date", "What", "Company", "People", "Known total (₹ Cr)"], rows)
    if kind == "script":
        return head + "\n\n" + script_md(card)
    if kind == "lineage":
        rows = [[LEAD_WORDS.get(n.get("kind"), n.get("kind")), "↳ " * depth + str(n.get("label") or ""),
                 STATUS_WORDS.get(n.get("status"), n.get("status")), n.get("detail")]
                for n, depth in _tree_order(card.get("nodes") or items)]
        return head + ("\n\n" + _table(["Lead", "What", "Status", "Detail"], rows) if rows else "")
    return head


# The words the lineage card shows for each lead kind and status (api/CONTRACT.md), never the internal slugs.
LEAD_WORDS = {"person": "Person", "same_person": "Same person, another event", "family": "Same household",
              "household": "Same household", "filing": "Related filing", "process": "Event to process",
              "linkedin": "Public LinkedIn profile", "web": "Mentions on the web", "event": "Event", "figure": "Figure"}
STATUS_WORDS = {"followed": "Followed", "candidate": "Not run", "skipped": "Not run", "processed": "Processed",
                "stopped": "Stopped", "failed": "Failed"}


def _tree_order(nodes: list) -> list[tuple[dict, int]]:
    """[(node, depth)] with each node right after its parent (flat items without parents keep their order)."""
    nodes = [n for n in nodes if isinstance(n, dict)]
    ids = {n.get("id") for n in nodes if n.get("id")}
    children: dict = {}
    for n in nodes:
        parent = n.get("parent") if n.get("parent") in ids else None
        children.setdefault(parent, []).append(n)
    out: list[tuple[dict, int]] = []
    seen: set = set()

    def walk(parent, depth: int) -> None:
        for n in children.get(parent, []):
            if id(n) in seen:
                continue
            seen.add(id(n))
            out.append((n, depth))
            if n.get("id"):
                walk(n["id"], depth + 1)

    walk(None, 0)
    return out + [(n, 0) for n in nodes if id(n) not in seen]


def script_md(card: dict) -> str:
    """A script card's sections."""
    parts = []
    for section in card.get("sections") or []:
        parts.append(f"*{section['heading']}*\n" + "\n".join(f"- {_cell(line)}" for line in section["lines"]))
    return "\n\n".join(parts)


def _money(value: object) -> str:
    try:
        return f"${float(value or 0):.4f}"
    except (TypeError, ValueError):
        return "$0"


def conversation_md(conversation: dict) -> str:
    """The whole thread as a report: each question, its answer, its cards, its cost."""
    messages = conversation.get("messages") or []
    total = sum(float(((m.get("done") or {}).get("total_cost_usd")) or 0) for m in messages if m["role"] == "assistant")
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    out = [f"# {_cell(conversation.get('title'))}", "",
           f"_Exported {stamp} · {sum(1 for m in messages if m['role'] == 'user')} questions · model spend "
           f"{_money(total)}. Every number below comes from the filings' stored data; sources link to the public "
           "filings._", ""]
    turn = 0
    for message in messages:
        if message["role"] == "user":
            turn += 1
            out += [f"## {turn}. {_cell(message.get('text'))}", ""]
            continue
        if message.get("text"):
            out += [message["text"].strip(), ""]
        clarify = message.get("clarify")
        if clarify:
            out += [f"> Asked back: {_cell(clarify.get('question'))}"]
            out += [f"> - {_cell(o.get('label'))}" for o in clarify.get("options") or []] + [""]
        estimate = message.get("estimate")
        if estimate:
            action = estimate.get("action") or {}
            out += [f"> Cost estimate for {_cell(action.get('title'))}: {_money(estimate.get('cost_usd_low'))} to "
                    f"{_money(estimate.get('cost_usd_high'))}, confirmed separately.", ""]
        for card in message.get("cards") or []:
            out += [card_md(card), ""]
        meta, done = message.get("meta") or {}, message.get("done") or {}
        models = ", ".join(f"{m['model']} ×{m['calls']}" for m in done.get("models") or []) or "no model"
        out += [f"<sub>Cost {_money(done.get('total_cost_usd'))} · {models} · tokens in {meta.get('tokens_in', 0)} "
                f"(cached {meta.get('cached_in', 0)}) · out {meta.get('tokens_out', 0)} · "
                f"{done.get('seconds', 0)} s</sub>", ""]
    return _scrub("\n".join(out).rstrip() + "\n")


def _scrub(text: str) -> str:
    """Last guard: drop anything shaped like a signed token or an API key."""
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[removed]", text)
    return re.sub(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b", "[removed]", text)


def callpack_md(event_id: str, person_id: str, script_card: dict | None) -> str | None:
    """Call card + brief + call script + evidence links for one person; None when they are not found."""
    found = tools.person_card(event_id, person_id)
    if not found["cards"]:
        return None
    card = found["cards"][0]["items"][0]
    if script_card is None:
        script_card, _removed = script.card_for(card, script.template_draft("call"), "call", "template")
    name = (card.get("person") or {}).get("name") or "Person"
    out = [f"# Call pack: {_cell(name)}", "",
           f"_{_cell((card.get('event') or {}).get('company'))} · {_cell((card.get('event') or {}).get('type_label'))}. "
           "Every number comes from the filing; sources are linked._", "",
           "## Call card", "", card_md({"kind": "person", "title": name, "items": [card]}), "",
           "## How the money was worked out", ""]
    for figure in card.get("amounts") or []:
        out.append(f"- **{_cell(figure.get('label'))}:** {_cell(figure.get('display'))}"
                   + (f" — {_cell(figure.get('working'))}" if figure.get("working") else ""))
    for timing in card.get("timing_detail") or []:
        out.append(f"- **{_cell(timing.get('label'))}:** {_cell(timing.get('display'))}")
    written = {"model": "words by the assistant, numbers by code", "template": "written by code from a template",
               "reused": "words by the assistant, numbers by code"}.get(script_card.get("written_by"), "")
    out += ["", f"## Call script ({written})", "", script_md(script_card), ""]
    links = _source_links(card)
    if links:
        out += ["## Sources", ""] + [f"- {link}" for link in links] + [""]
    return _scrub("\n".join(out).rstrip() + "\n")


def latest_script(conversations: list[dict], event_id: str, person_id: str) -> dict | None:
    """The newest call script for this person in these conversations (each {messages: [...]})."""
    best = None
    for conversation in conversations:
        for message in conversation.get("messages") or []:
            for card in message.get("cards") or []:
                who = card.get("person") or {}
                if card.get("kind") == "script" and card.get("channel", "call") == "call" and \
                        (who.get("event_id"), who.get("person_id")) == (event_id, person_id):
                    if best is None or message.get("created_at", "") >= best[0]:
                        best = (message.get("created_at", ""), card)
    return best[1] if best else None
