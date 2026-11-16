# Demo rebuild: RM call-list app (design)

Date: 2026-11-15 · Due: 2026-11-16 end of day · Status: **awaiting owner approval**

## Intent

Turn the existing money-event → RM call-list prototype into a **demo-worthy showcase**: someone watching
should see an RM open the app, know who to call today and why, trust every number in one click, prepare a
2-minute call, and watch a brand-new event get processed live. It is a demo only; it does not need to
become a multi-user product later. Built on **Next.js + FastAPI**, run **locally**.

## What exists (from the audit, `../../../../audit/`)

- Python pipeline (`run.py`, `agents/`, `tools/`, `config/`): fetch → PDF pages → keyword page finder →
  cheap-LLM quote extraction → code verification → people/families → money rules → rank → LLM brief → report.
  16 events processed into `outputs/`. 262 offline tests pass.
- **Strength:** no invented number was found in any audited event; arithmetic is exact and shows working.
- **Weaknesses that show in a demo:**
  - Ranking is not RM-usable. Buyback lists rank "not tendering" holders first (30 of 33 buyback people get
    no money). SEDEMAC's largest holder ranks 18/19. Past "scheduled" listings fill "Today's calls".
    A fund ("…Mauritius") sits in the callable list.
  - Bad text: "up to Up to 3,702,694 Equity Shares shares offered". One brief says "retained 42,000" (true: 29,400).
  - Recall gaps: wrapped names lose their numbers (26 of 27 rejected values are really in the table row),
    a seller dropped because one OCR page is garbled, roles "unknown" though printed (HD Fire), lock-in
    wording variants missed.
  - Two buyback announcements are scanned images (no OCR) → no call list.
  - Streamlit UI: engineer-facing (file and field names on screen, cost and pipeline charts on main pages),
    glassmorphism and animated background, no call/notes state, long audit-trail prep sheets.

## Goals

1. **Numbers you can trust in one click:** every figure opens the source page image with the quote highlighted.
2. **A call list an RM would accept:** cash-now people first, households grouped, non-recipients out of the
   call list, unknown amounts below known ones, past dates treated as past.
3. **Fewer "unknown"s** where the document actually prints the value.
4. **A modern, calm UI** built for the RM's morning, with ops detail moved out of the way.
5. **Visible smart tech:** live processing with streamed progress, plain-English "Ask", money calendar,
   relationship graph.

## Non-goals

Auth and multiple users, deployment, OCR for scanned PDFs (shown honestly as "scanned; not readable yet"),
new event types (ESOP buybacks, acquisitions), a full evaluation harness, edge-case polish, perfect mobile
(basic responsive only).

## Anti-goals (failure even if it "works")

- Any number on screen that is not from a verified field (the LLM never writes digits the RM sees).
- Internal jargon on RM screens (`ranked.json`, `money_now_crore`, etc.).
- A demo path that breaks live because it depends on a slow or blocked fetch (NSE can block cloud IPs; demo locally from cache).

## Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| **A. FastAPI over the existing files + Next.js** (chosen) | Reuses `outputs/` JSON and `run.py` as is; no DB migration; a small SQLite file only for RM notes/outcomes. Fastest path to a real UI. | **Chosen**: fits a 1.5-day demo. |
| B. Next.js static export reading JSON at build time | Simplest, but no live processing, no Ask, no saved notes: loses the best demo moments. | Rejected. |
| C. Move data into Postgres + job queue | Production-shaped, but days of work the demo does not need. | Rejected (owner: demo only). |

Owner decided: Next.js + FastAPI, local, demo only, due 2026-11-16 EOD, no heavy verification.

## Design

### Layout

```
aurelia/
  api/        FastAPI app (new). Python 3.12, same deps + fastapi, uvicorn, pypdfium2.
  web/        Next.js app (new). TypeScript, App Router, Tailwind, shadcn/ui, cmdk, Recharts, react-force-graph.
  agents/ tools/ config/ run.py   existing pipeline (fixed in place)
  app.py ui/  old Streamlit app, left untouched
```

### Pipeline fixes (in place, offline-verifiable, re-run from the LLM cache)

1. **Ranking** (`agents/rank.py`, `config/ranking.py`): priority tiers: (1) cash now or within 30 days
   (OFS/IPO proceeds at or recently after listing, buyback acceptance, exchange OFS settlement); (2) fresh
   unlocks, valued where the split is known, else ranked by holding with "value unknown"; (3) retained
   holders; buyback **non-tendering holders leave the call list** (shown as "context" on the event page).
   Unknown amounts sort below known ones in the same tier. Listing dates in the past count as past.
   Holders whose name reads as a fund/company go to entities. Households grouped (one slot, members inside).
2. **Display and brief text** (`agents/rules_*.py`, `agents/brief.py`): fix the doubled "up to Up to … shares
   shares"; the "OFS proceeds at listing" rule keeps its "(not stated in this event's documents)" qualifier
   unless the quote really says when sellers are paid; **briefs use placeholders and code writes every digit**.
3. **Recall** (`agents/verify.py`, `config/lock_in.py`, `agents/people.py`): a pdfplumber table-row check as a
   second way to verify a value in the holder's row (recovers wrapped names); a name verified on any page of
   the same document counts when the cited page's text is garbled; printed roles carried through; lock-in
   wording variants ("eighteen months", "pre – Issue", "in excess of Promoters' Contribution").
4. **Scanned PDFs:** marked "scanned: needs OCR" in status (no OCR now).
5. Re-run every event from cache: extraction calls replay at $0; briefs whose fields change re-call the cheap model (cents).

Tests: tier 1 only (ranking order and amount/brief digits on fixtures). UI verified by eye.

### API (FastAPI, `api/`)

- `GET /events` · `GET /events/{id}` (summary, documents, price/listing facts, status) ·
  `GET /events/{id}/people` (ranked call list + entities + context holders) · `GET /people/{event}/{person}`
  (call card, amounts with working, timing, evidence refs, family) · `GET /today` (cross-event call queue,
  date-aware, household-grouped) · `GET /calendar` (money dates) · `GET /network` (households + cross-event links) ·
  `GET /feed` (discovery items + status) · `GET /ops` (cost/time per event, verification counts).
- `GET /evidence/page.png?doc=…&page=…&quote=…` renders the cached PDF page with the quote highlighted
  (pdfplumber search → bbox; pypdfium2 render). `GET /docs/{sha}.pdf` serves cached PDFs.
- `POST /events/from-links` (propose doc types from links, no model call where rules settle it) ·
  `POST /events/{id}/run` (runs `run.py --step all` in a subprocess) · `GET /jobs/{id}/stream` (SSE step progress).
- `POST /ask` (question → fixed filter JSON via the cheap model → results computed by code; never writes numbers).
- `GET/PUT /rm/{event}/{person}` (status: to call / called / not now / not a fit, notes, follow-up date) in SQLite.
- `GET /export/calls.csv` (CRM-ready: stable ids, numeric amounts, ISO dates).

### Web (Next.js, `web/`)

- **Today:** call queue (cards: name, household, why, ₹ amount, timing pill, confidence, one-line reason),
  quick actions (called / snooze / note), filters (event, timing, confidence, min amount).
- **Person (drawer or page):** 2-minute call card on top (brief with copy, why now, amount + working, timing,
  confidence and why); evidence below as page thumbnails with highlights; household members; RM status + notes.
- **Events:** live feed (discovered, ready, processing, failed with plain reason) → event page (facts strip,
  call list, entities and context holders) → "Process now" with streamed step progress; "Add from links".
- **Calendar:** money becoming available by date (listings, unlocks, buyback payments).
- **Network:** household and relationship graph.
- **Ask (⌘K):** search plus plain-English questions ("promoters with cash in hand above ₹50 crore").
- **Trust & Ops:** verification counts, rejected values, cost and time per event (cost under $2/event is a selling point).
- **Visual direction:** calm, light-first with dark mode, one accent colour, Inter with tabular numerals, solid
  surfaces (no glassmorphism, glows, purple gradients or animated background), skeleton loading, honest empty
  states. Copy in RM language.

### Left to the builder

Component choices inside shadcn/ui, chart styling, exact SQL schema, the filter-language shape for Ask,
exact tier thresholds (documented in `config/ranking.py` with a one-line reason each).

## Calls I made (owner can override)

- Keep the product name **AURELIA** (no time for branding work).
- Keep the old Streamlit app untouched beside the new one.
- Light-first theme with dark mode toggle.
- No OCR this round.

## Execution (summary; full plan follows approval)

Orchestrator workflow (`../../../../WORKFLOW.md`), parallel builders in git worktrees on a local branch:
- Wave 1, in parallel: (G1) ranking + display + brief fixes · (G2) recall fixes · (G3) FastAPI ·
  (G4) Next.js design system + screens against the API contract (mocked until G3 lands).
- Integrate → re-run all events from cache → wire the UI to the real API → one review pass + fix blockers →
  agent browser run of the demo script → owner acceptance check.
