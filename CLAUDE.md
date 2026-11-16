# CLAUDE.md — project handover

Read this file fully before doing anything. It replaces the chat history.

## What this is

A take-home for a Forward Deployed Engineer internship (brief: `docs/` and the assignment PDF).
Part B: given a real Indian money event (IPO, buyback/acquisition, one more), return a ranked
list of people an RM should call, each with: name and role as printed, why they got money,
a ₹ range with working, timing (now vs later), confidence (separate from amount), a source
link for every fact, and a 3–4 line RM brief. It must run live on an event we have never seen,
log token cost and run time per event and per person (< $2 per event), and make repeat runs
much cheaper. **An invented number is the worst possible failure.**

Due: 15 Nov 2026. Part A is done (`docs/`). Part C (client doc), the video and the README
diagram come last.

## Hard rules (also in .cursorrules)

1. No company, person or event names in code. Events live in `events/*.json`; answer keys
   live in `eval/gold/*.json`.
2. Never fill a fact from memory. Every figure needs a source quote the code has verified on
   the page, or it is labelled an estimate with the working shown.
3. Plain Python, no agent framework. The LLM copies text from a few pages; code does
   everything else (finding pages, checking quotes, merging, arithmetic, ranking).
4. Never bypass a 401/403 or a site's terms. No LinkedIn. No personal contact details.
5. Small functions with docstrings. Tests need no network and no API key.
6. Don't write `decision_log.md`, `assumptions.md` or `whats_broken.md` for the user. They
   must be in the user's own words. You may suggest what a row should cover.
7. After each task: list files changed, assumptions made, and what could break on an unseen
   event.

## Environment

- Originally built on Windows, PowerShell (the notes below are for that setup).
- Save command output with `| Out-File -Encoding utf8 <file>`; plain `>` writes UTF-16.
  Logs go to stderr and won't be in that file.
- LLM via OpenRouter. `.env`: `LLM_API_KEY`, `LLM_BASE_URL`,
  `LLM_MODEL=anthropic/claude-haiku-5.5`, `LLM_MODEL_STRONG=anthropic/claude-sonnet-5.5`.
  Haiku price $0.10 / $0.50 per 1M tokens (prompts under 100K tokens); checked 2026-11-13.
  Sonnet isn't priced yet; price it before step 3 uses it.
- `tools/llm.py` sends only the parameters the model supports (from OpenRouter's /models).
  Haiku doesn't accept `temperature`, so the cache is what makes reruns identical.
  `cost_log.csv` has `cost_usd` (our estimate), `charged_usd` (OpenRouter's figure),
  `params`, `status`, `error`.
- `python -m tools.llm --ping` tests the key for a fraction of a cent.

## Pipeline status

| Step | File(s) | State |
| --- | --- | --- |
| 0 fetch, cache, LLM wrapper, cost and run logs | `tools/` | done |
| 1 PDF to pages, keyword page finder | `tools/pdf.py`, `agents/locate.py`, `config/sections.py` | done; hit@3 = 3/3 on SEDEMAC gold |
| 2 extract (1 cheap-LLM call per section), verify in code, merge | `agents/extract.py`, `agents/verify.py`, `agents/names.py` | works, under repair (2d below) |
| 3 same-person matching and families | — | next after 2d |
| 4 amount and timing in code | — | |
| 5 rank and RM briefs (numbers checked in code) | — | |
| 6 buyback and a third event | — | |
| 7 follow-on leads (budget, visited set, caps) | — | |
| 8 held-out IPOs, 20-person accuracy check, report/UI, README diagram | — | |

Run: `python run.py --event events/sedemac_ipo.json --step extract`. One SEDEMAC run costs
$0.0176 and 83 s; the cached rerun costs $0 and 1.1 s (see `outputs/runs.csv`).

## SEDEMAC facts checked by hand (RHP, printed pages)

- Cover (pdf 1): offer-for-sale table for 10 of 23 sellers with average cost of acquisition
  (e.g. Manish Sharma up to 45,000 shares, ₹46.00). Fresh issue "Not Applicable".
- pp. 16–17: all 23 sellers with maximum shares offered. Role is a group heading above names.
- p. 18: pre-offer holdings (e.g. Manish Sharma^ 864,000; Prof. Shashikanth Suryanarayanan
  7,150,500, 16.16%, not a seller).
- p. 24: full average-cost table (cover says so; not yet read by a human).
- Prices in the RHP are all ₹[●]. Band ₹1,287–1,352 and listing 11 Mar 2026 come only from news
  so far; the pipeline needs the final Prospectus or price-band announcement from NSE/BSE/SEBI
  added to `events/sedemac_ipo.json`.
- The RHP itself prints names inconsistently ("Capri Global Holdings/Holding",
  "SVS Trust No IV / No. IV", "Xponentia Opportunities Fund - II / Fund II"). Use these as step 3
  test cases.

## Current extract result (prompt v2) and what's wrong

32 merged rows. 11 sellers have verified shares offered; 11 sellers are `unattributed`.
Problems found in `outputs/sedemac_ipo/extract.json`:

1. Names fail "value not in quote": the model's name quote holds only part of a wrapped name.
   The name is on the page (token match works) but not wholly inside the quote.
2. Manish Sharma lost his 45,000 ("not in this person's row") and his role ("heading not above
   name"). His shares quote is inside his own name quote on pdf 20, but row binding anchors on
   the first occurrence of his name on the page, which is a paragraph mention far above the
   table.
3. Offer size and face value fail "quote not on page": the quote exists, but on a different page
   in the same call than the one cited.
4. Role conflicts null the role: "Investor Selling Shareholders" vs "Selling Shareholders" from
   two tables. Roles from different tables aren't contradictions.
5. No average-cost value survived. The model proposed only 17 fields for that section. We can't
   see why without the raw responses.

## Next task: step 2d (verify-only; must make no new model calls)

```text
1. Name check: a name passes when it is located on the cited page (token path, not inside a
   longer extracted name) and the name quote's span on that page overlaps the located name
   span. The full name no longer has to be inside the quote. Rename the failure reasons so each
   says exactly what failed.
2. Row anchor: for amounts and roles, anchor on the span of this row's own name-evidence quote
   on the same page when there is one; otherwise try every occurrence of the name that isn't
   inside a longer name. An amount passes if its quote starts inside the anchor or within
   ROW_WINDOW after it, and before the next other extracted name after the anchor. A role
   heading must sit before the anchor with no other heading between.
3. Citation repair: if a quote isn't on the cited page but is on exactly one other page in the
   same call, accept it, rewrite pdf_index and printed_page to the real page, and set
   "citation_corrected": true on that evidence object. On zero or several pages, keep the
   rejection.
4. Roles merge into a list ("roles_as_printed"), never a conflict. Amount conflicts still null
   the field.
5. Write each section's raw model response to outputs/<event_id>/raw/<section>.json, read from
   the LLM cache, so a human can see what the model proposed.
Tests (strings only): a wrapped name with a partial quote passes; Manish's 45,000 inside his own
name quote passes when an earlier paragraph mentions him; a quote cited on the wrong page is
corrected; one on two pages is rejected; two role headings merge into a list.
Acceptance: rerun extract; cost_log shows all calls cached at $0; at least 20 of 23 sellers have
verified shares offered; Manish has 45,000, 864,000 and his role.
```

Then: read `outputs/sedemac_ipo/raw/waca.json` with the user to decide the average-cost fix,
and add hand-checked seller numbers to `eval/gold/sedemac_ipo.json` so extraction accuracy is
measured, not eyeballed.

## Working style the user wants

- Direct, no flattery. Lead with what's wrong. Stress-test before agreeing.
- One step at a time: show the plan, do it, report results, wait.
- The user must be able to explain every line on the call. Prefer simple code and say why.
- Git: the owner approved local commits on branch `demo-rebuild` (2026-11-15). Commit locally; never push.

