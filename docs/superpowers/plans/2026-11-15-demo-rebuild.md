# FinSight demo rebuild: implementation plan

> **For agentic workers:** executed through the orchestrator workflow (the orchestrator workflow):
> parallel builders in explicit git worktrees, one writer per file set. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A polished, demo-ready RM call-list product (Next.js UI + FastAPI over the existing Python pipeline) with RM-usable rankings, fewer unknowns, and one-click evidence, done by 2026-11-16 EOD.

**Architecture:** The pipeline is fixed in place and re-run from its LLM cache. A new FastAPI app (`api/`) turns `outputs/`, `events/`, discovery files and cached PDFs into RM-language JSON, runs the pipeline as a streamed job, answers plain-English filters, and stores RM notes in SQLite. A new Next.js app (`web/`) is the only UI shown in the demo.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pdfplumber 0.11.10 (+ its pypdfium2), sqlite3; Next.js (App Router, TypeScript), Tailwind CSS, shadcn/ui, lucide-react, cmdk, Recharts, react-force-graph-2d, sonner.

**Spec:** `docs/superpowers/specs/2026-11-15-demo-rebuild-design.md`

## Global Constraints

- Every number shown in the UI comes from a stored, verified pipeline field or code arithmetic on such fields. The LLM never writes digits the RM sees.
- No internal jargon on any screen: no file names (`ranked.json`), field names (`money_now_crore`), "pipeline", "LLM" or "extract".
- Business audience: every screen finished and polished; designed empty, loading and error states; consistent spacing and type; tabular numerals for all numbers; ₹ in Indian format (₹1,23,45,678 / "₹92.05 Cr").
- Visual: light-first with a dark-mode toggle, solid surfaces, one accent colour, Inter. No glassmorphism, glows, purple gradients, animated backgrounds or emoji icons.
- UI builders use the `impeccable` skill (and `ui-ux-pro-max` for component/pattern choices) before writing UI.
- Tests: tier 1 only (ranking order, amount/brief digits). UI is verified by eye in a real browser. No edge-case polishing.
- Never print `.env` values. Never push. Local commits on branch `demo-rebuild` only.
- Python: `.venv/bin/python`. Ports: API 8000, web 3000.
- Nothing in the product mentions any employer or tracker.

## Review Focus

1. An event with 0 callable people (Jio, Goa) must show a designed "no one to call, here's why" state, not a blank page. Owned by Task 6 (event page) via API `call_list.empty_reason` (Task 3).
2. A person whose amount is unknown must show "Amount not disclosed" plus the reason, never ₹0. Owned by Task 3 (API `amount.value_cr = null`) and Task 5.
3. A scanned document (Genus, Medi Assist) must show "Scanned filing: text not readable yet". Owned by Task 3 (`doc.scanned`) and Task 6.
4. A live run that fails must end the progress view with a plain reason and keep the old call list. Owned by Task 3 (job `state=failed, reason`) and Task 6.
5. Evidence whose quote cannot be found on the rendered page must still show the page (no highlight) with the quote text beside it. Owned by Task 3 (`/evidence/page.png` falls back) and Task 5.

---

## Setup (orchestrator, before Wave 1)

- [ ] `git stash push -m "zip CRLF line endings, content identical to HEAD"` (working tree differs from HEAD only by CR; verified with `git diff --ignore-cr-at-eol --stat` = empty), then `git switch -c demo-rebuild`.
- [ ] Add the spec, this plan and `.gitignore` lines (`.venv/`, `api/state/`, `web/node_modules/`, `web/.next/`) and commit.
- [ ] `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt fastapi uvicorn[standard]`.
- [ ] Worktrees: `git worktree add ../wt-<g> -b demo/<g> demo-rebuild` for g in `rank`, `recall`, `api`, `web`; in each, symlink `cache/fetch` and `cache/pages` to the main checkout's (PDFs and parsed pages are git-ignored).

## Wave 1 (parallel)

### Task 1: RM-usable ranking, display text, digit-safe briefs (worktree `wt-rank`)

**Files:**
- Modify: `agents/rank.py`, `config/ranking.py`, `agents/brief.py`, `agents/rules_ipo.py`, `agents/rules_buyback.py`, `agents/rules_ofs.py` (display/why/amount text functions only), `agents/report.py` (only if it reads changed fields)
- Test: `tests/test_demo_ranking.py` (new); update `tests/test_ipo_regression.py` / `tests/fixtures/` snapshots to the new intended order

**Interfaces:**
- Produces in `ranked.json`: `{"callable": [...], "entities": [...], "context": [...]}`. `context` = holders who get no money from this event (buyback non-tendering, `not tendering`), each with `context_reason` (RM words).
- Each callable entry gains `call_tier: "cash_now" | "unlock" | "holding"`, `call_tier_label` (RM words, e.g. "Cash in hand", "Shares just unlocked", "Holds shares"), and `household_id: str | null` (= `family_group` id when present).
- `rank_reasons` stays; the first line becomes a plain-English "why this rank".

- [ ] **Step 1: Write failing tests** in `tests/test_demo_ranking.py` using small hand-built person dicts (shape as in `outputs/sedemac_ipo/people.json`):
  - `test_cash_now_outranks_holding`: a seller with computed proceeds in hand 20 days ago ranks above a non-seller whose retained value is 10× larger.
  - `test_buyback_non_tendering_goes_to_context`: a buyback person with participation "not tendering" is in `context`, not `callable`.
  - `test_unknown_amount_sorts_below_known_in_tier`: two cash-now sellers, one with proceeds status `unknown` → the known one ranks first.
  - `test_past_scheduled_listing_counts_as_past`: listing date 12 days before `as_of`, status `scheduled` → `call_tier == "cash_now"` and its timing label does not say "scheduled".
  - `test_fund_like_unsure_holder_is_entity`: `holder_type: "unsure"`, name "Lightspeed Venture Partners Select IV Mauritius" → in `entities`.
  - `test_promoter_unlock_with_unknown_split_not_zero`: promoter with retained value ₹966.75 Cr and a lock-in that ended 67 days ago ranks in tier `unlock` above a ₹0.24 Cr holding-only person.
  - `test_amount_display_no_doubled_words`: the amount display for shares_offered printed as "Up to 3,702,694 Equity Shares" contains neither "up to Up to" nor "shares shares".
  - `test_brief_digits_come_from_fields`: a brief generated with a stubbed model that returns a line containing "42,000" where the field says retained 29,400 is rejected or rewritten so every number in the final lines appears verbatim in the fields; with placeholders `{retained_shares}` the code fills "29,400".
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_demo_ranking.py -q` → FAIL.
- [ ] **Step 3: Implement.** Tier order cash_now > unlock > holding; within tier: known amount before unknown, then score, then name. Recency/timing weights stay in `config/ranking.py` with a one-line reason each. Briefs: the model writes text with `{field}` placeholders from a fixed list; code substitutes values; a line with any digit not from a placeholder falls back to the template.
- [ ] **Step 4: Run** the new tests plus `tests/test_rank_brief_report.py tests/test_ipo_regression.py` → PASS (update snapshots deliberately; note each changed expectation in the commit message).
- [ ] **Step 5: Commit** `feat(rank): RM call tiers, context list, digit-safe briefs`.

### Task 2: Recall fixes, fewer unknowns (worktree `wt-recall`)

**Files:**
- Create: `tools/tables.py`
- Modify: `agents/verify.py`, `agents/people.py`, `config/lock_in.py`, `agents/rule_sources.py`
- Test: `tests/test_recall.py` (new)

**Interfaces:**
- Produces: `tools.tables.row_confirms(pdf_path: str, pdf_index: int, name: str, value: str) -> bool`: true when pdfplumber's ruled-table finder on that page has one row whose cells contain the name's tokens and the value.
- Consumes: nothing new. No change to output file shapes except more fields verified.

- [ ] **Step 1: Write failing tests** (strings/fixtures only, no network): `test_row_confirms_wrapped_name` (fixture: a tiny PDF built in the test with reportlab-free pdfplumber-readable table, or skip if building PDFs is heavy and use a page-text fixture of the row-binding fallback); `test_name_ok_on_other_page_when_cited_page_garbled`; `test_lockin_variant_eighteen_months` (anchor phrase "eighteen months" matches the promoter-contribution period); `test_ofs_listing_rule_needs_payment_wording` (a quote that only says sellers reimburse expenses "upon listing" does not count as "proceeds paid at listing").
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_recall.py -q` → FAIL.
- [ ] **Step 3: Implement.** In `verify.py`, when text row-binding rejects an amount ("not in this person's row" / "value not in quote") call `row_confirms` on the cached PDF (`cache/fetch/<sha256(url)>.bin`); accept with `"verified_by": "table_row"`. Name check: if the cited page's text lacks the name but the same document has the exact name on another page, accept with `"citation_corrected": true`. Roles: carry the printed role heading through when present (investigate HD Fire `outputs/hd_fire_protect_limited_ipo_202610/extract.json` rejections). Add lock-in anchor variants.
- [ ] **Step 4: Run** new tests + full `tests/` → PASS.
- [ ] **Step 5: Measure** on cache (no LLM): `run.py --event events/sedemac_ipo.json --step extract` and HD Fire / Spacenet extract; report unknowns before → after in the commit message. These replay the LLM cache ($0); if any call is uncached, stop and report instead of calling.
- [ ] **Step 6: Commit** `feat(verify): table-row check, cross-page names, roles, lock-in variants`.

### Task 3: FastAPI service (worktree `wt-api`)

**Files:**
- Create: `api/__init__.py`, `api/main.py` (app, CORS for :3000), `api/store.py` (load + cache outputs), `api/views.py` (RM view models), `api/evidence.py`, `api/jobs.py`, `api/ask.py`, `api/rm_state.py`, `api/CONTRACT.md`, `api/requirements.txt`
- Test: `tests/test_api.py` (tier 1: money fields equal stored values; unknown → null)

**Interfaces (document every response shape with an example in `api/CONTRACT.md`; wave-2 builders code against it):**
- `GET /api/summary` → KPIs for Today header: people to call, cash now ₹ total (Cr, number), new events this week, events processed, as_of.
- `GET /api/today?limit=` → call queue across events: households grouped (`members`), date-aware tiers from Task 1 (falls back gracefully when `call_tier` absent), each item: `event{id,company,type}`, `person{id,name,role,holder_type}`, `tier,tier_label`, `amount{value_cr|null, display, kind:"cash"|"shares", estimate:bool}`, `timing{label,status,date_iso|null}`, `confidence{level,reason}`, `why` (one line), `brief_first_line`, `rm{status,follow_up}`.
- `GET /api/events` (with `status: ready|processing|failed|scanned|not_supported`, `people_count`, `cash_cr`, `listing_date`, `doc` list with `scanned` flag computed from `cache/pages` text length) · `GET /api/events/{id}` (facts strip: price basis, listing, allotment, issue type, documents, cost and run time) · `GET /api/events/{id}/people` (`callable`, `entities`, `context`, `empty_reason`).
- `GET /api/people/{event_id}/{person_id}` → call card: brief lines, why now, amounts (proceeds, gain, retained: `display`, `working`, `value_cr`, `inputs[]` each with `evidence[]` = `{doc_sha, doc_label, pdf_index, printed_page, quote, url}`), timing with rule citation, confidence + reason, household members, flags in RM words, rank reasons, rm state.
- `GET /api/evidence/page.png?doc_sha=&pdf_index=&quote=` → PNG of the page at ~150 dpi with the quote's boxes highlighted (pdfplumber `Page.search`; on no match return the plain page and header `X-Highlight: none`). `GET /api/docs/{sha}.pdf`.
- `GET /api/calendar?from=&to=` → dated money items (listing, unlock end, buyback payment, OFS settlement) with people and ₹.
- `GET /api/network` → nodes (people, entities, events) and edges (household, same-person across events, holder→event) with reasons.
- `GET /api/feed` → discovery items grouped Today/Upcoming/Recent with status and next action.
- `GET /api/ops` → per event: cost USD, fresh cost, per-person cost, run seconds, step timings, verification counts (proposed/kept/rejected per section), rejection list.
- `POST /api/events/from-links {urls[]}` → proposals (reuse `tools/propose.propose`). `POST /api/events {event spec}` → writes `events/<id>.json` (validated by `agents.spec.EventSpec`).
- `POST /api/events/{id}/run` → `{job_id}`; runs `run.py --event <path> --step all` as a subprocess; `GET /api/jobs/{job_id}/stream` → SSE events `{step, state: start|done|failed, seconds, cost_usd}` then `{state: complete|failed, reason}` (parse lines with `ui.components.parse_step_line` / `parse_total_line`).
- `POST /api/ask {q}` → `{filters, people[], explanation}`; the cheap model (through `tools.llm.llm_call`) only maps the question to a fixed filter JSON (`event_type, role_contains, tier, min_cr, max_cr, timing_status, confidence, company`); code applies it. On model failure: keyword search over names/companies/roles.
- `GET/PUT /api/rm/{event_id}/{person_id}` → `{status: "to_call"|"called"|"follow_up"|"not_now"|"not_a_fit", note, follow_up_date, updated_at}` in `api/state/rm.sqlite`.
- `GET /api/export/calls.csv` → stable ids, numeric ₹, ISO dates, tier, status.

- [ ] **Step 1: Failing test** `tests/test_api.py` with FastAPI `TestClient` against the committed `outputs/`: `test_person_amount_matches_stored` (sedemac top seller's `value_cr` equals `people.json` `crore_high` as float); `test_unknown_amount_is_null` (spacenet person: `value_cr is None`, display says not disclosed); `test_rm_state_roundtrip` (PUT then GET, using a temp sqlite path via env `RM_STATE_PATH`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** all endpoints above; read files fresh per request (small data). **Step 4: Run** → PASS; `curl` each GET endpoint once with uvicorn on :8000 and paste one example per endpoint into `api/CONTRACT.md`.
- [ ] **Step 5: Commit** `feat(api): FastAPI service for the demo UI`.

### Task 4: Next.js foundation and design system (worktree `wt-web`)

**Files:**
- Create: `web/` (create-next-app, TypeScript, App Router, Tailwind, ESLint), shadcn/ui init, `web/lib/api.ts` (typed fetch client to `http://localhost:8000/api`, base URL from `NEXT_PUBLIC_API_URL`), `web/lib/format.ts` (`formatCr(n)`, `formatINR(n)`, dates "26 Nov 2026", relative "in 11 days"), `web/components/` design system, `web/app/layout.tsx` app shell, `web/DESIGN.md` (tokens and rules).

**Interfaces:**
- Produces components (props typed against `api/CONTRACT.md` shapes; until the API lands, use fixtures copied from real `outputs/`): `AppShell` (sidebar: Today, Events, Calendar, Network, Trust & Ops; top bar: ⌘K search, theme toggle, as-of date), `CommandPalette`, `Money` (₹ Cr, tabular, estimate marker), `TimingPill`, `ConfidenceBadge`, `TierBadge`, `PersonRow`, `PersonCardHeader`, `EvidenceChip` (opens `EvidenceViewer`), `EvidenceViewer` (dialog: page image from `/api/evidence/page.png` with highlight, quote, "Open PDF at page"), `StatCard`, `SectionHeader`, `EmptyState`, `ErrorState`, `Skeleton*`, `StatusBadge` (ready/processing/failed/scanned/not supported), `RmStatusControl` (status select + note + follow-up date).
- Route stubs with polished placeholders: `/` (Today), `/events`, `/events/[id]`, `/people/[eventId]/[personId]`, `/calendar`, `/network`, `/ops`.

- [ ] **Step 1:** Invoke `impeccable` (direction for a premium wealth-intelligence product for business viewers) and `ui-ux-pro-max`; record the chosen direction, palette, type scale, spacing, radius and motion in `web/DESIGN.md`.
- [ ] **Step 2:** Scaffold, install deps, build the shell and every component above with fixture data; `npm run build` passes; `npm run lint` passes.
- [ ] **Step 3:** Screenshot the shell and a component gallery page (`/dev/gallery`) at 1440 and 390 wide; fix anything visibly off.
- [ ] **Step 4: Commit** `feat(web): Next.js shell and design system`.

## Integration 1 (orchestrator)

- [ ] Merge `demo/rank`, `demo/recall`, `demo/api`, `demo/web` into `demo-rebuild` (conflicts only possible in `tests/fixtures`; resolve to Task 1's intended order).
- [ ] `.venv/bin/python -m pytest -q` → all pass.
- [ ] Re-run every event in `events/*.json` and `events/auto/*.json` with `run.py --step all` (LLM cache replays; changed briefs re-call the cheap model; cost logged). Spot-check SEDEMAC, a buyback, Spacenet, HD Fire in the API.
- [ ] Commit `chore: re-run all events with the fixed pipeline`.

## Wave 2 (parallel, each in a fresh worktree from `demo-rebuild`; `cp -c -R` web/node_modules)

### Task 5: Today + Person call card + evidence (worktree `wt-today`)
**Files:** `web/app/page.tsx`, `web/app/people/[eventId]/[personId]/page.tsx`, `web/components/today/*`, `web/components/person/*`
- [ ] Today: header KPIs (`/api/summary`), call queue (`/api/today`) grouped by tier with household rows expandable, quick actions (Called / Follow up / Not now) via `/api/rm`, filters (event type, tier, confidence, min ₹), "Export for CRM" (`/api/export/calls.csv`).
- [ ] Person: 2-minute call card on top (name, role, company, tier, ₹ with working on hover, timing, confidence with reason, brief with copy button), "Why now", amounts with evidence chips → `EvidenceViewer`, household members, RM status + notes, collapsible "Full evidence trail".
- [ ] Verify in the browser at 1440 and 390 against the real API; commit `feat(web): Today queue and person call card`.

### Task 6: Events, live feed, add-from-links, live processing (worktree `wt-events`)
**Files:** `web/app/events/page.tsx`, `web/app/events/[id]/page.tsx`, `web/components/events/*`
- [ ] Events index: discovered feed (Today / Upcoming / Recent) and processed events grid with status badges and plain reasons (scanned, not supported, failed).
- [ ] Event page: facts strip (company, type, price, listing/allotment, documents), call list (tiered), "Also on the register" (entities) and "No money from this event" (context), designed empty state with `empty_reason`.
- [ ] "Process now" and "Add event from links" (paste URLs → proposals → confirm → run) with a live step-progress panel from SSE; failure ends with the reason; success refreshes the call list.
- [ ] Verify in browser; commit `feat(web): events, feed and live processing`.

### Task 7: Calendar, Network, Ask, Trust & Ops (worktree `wt-insights`)
**Files:** `web/app/calendar/page.tsx`, `web/app/network/page.tsx`, `web/app/ops/page.tsx`, `web/components/ask/*`, `web/components/charts/*`
- [ ] Calendar: month view + list of money dates (listing, unlock, payment) with ₹ per day; click → people.
- [ ] Network: force graph (households, people across events, holder → event) with legend, hover cards, click → person.
- [ ] Ask: in `CommandPalette`, a question mode calling `/api/ask`; results as person rows with the applied filters shown as chips ("Interpreted as: promoters · cash now · ≥ ₹50 Cr").
- [ ] Trust & Ops: "How we know" (verified vs rejected values per event, chart), cost per event vs the $2 target, run time per step, latest runs.
- [ ] Verify in browser; commit `feat(web): calendar, network, ask, trust & ops`.

## Wave 3: integrate, one review, demo run (orchestrator)

- [ ] Merge Tasks 5–7; `npm run build`; pytest.
- [ ] Add `demo.sh` (starts API on :8000 and web on :3000 with PID files; `demo.sh stop` stops them by PID) and a README "Run the demo" section.
- [ ] **One** review pass (Opus) over the branch diff, blockers only (wrong number shown, broken journey, crash). Fix blockers once.
- [ ] Agent browser run of the demo script below at 1440 (and Today/Person at 390), screenshot every screen; one UI grading pass; fix concrete user-facing failures once.
- [ ] Owner acceptance check with this script:
  1. `./demo.sh`, open http://localhost:3000.
  2. Today: top calls are people with cash now; open the first.
  3. Click the ₹ amount's evidence: the source page shows with the quote highlighted.
  4. Mark "Called", add a note, reload: it persists.
  5. Events → SEDEMAC: tiered call list; Jio: designed "no one to call" state.
  6. Events → pick an event → Process now: steps stream, then the list refreshes.
  7. ⌘K → "promoters with cash in hand above 50 crore": filtered people with chips.
  8. Calendar, Network, Trust & Ops render with real data.

## Addendum (owner, 2026-11-15 night): Neon database + simplest login with roles

### Task 8: Login, roles, Postgres (Neon) storage, security fixes (single builder, on demo-rebuild after final integration)

**Files:** Create `api/db.py`, `api/auth.py`, `api/seed_users.py`, `web/app/login/page.tsx`, `web/middleware.ts`; modify `api/main.py`, `api/rm_state.py`, `web/next.config.*` (rewrites), `web/lib/api.ts`, `web/app/layout.tsx`/shell (user menu, role-gated actions), `demo.sh`, `README.md`.

- **DB:** `DATABASE_URL` env (Neon Postgres, `sslmode=require`) via `psycopg[binary]` v3; when unset, fall back to SQLite `api/state/app.sqlite`. Tables `users(id, email unique, name, role, password_hash)` and `rm_state(...)`. Pipeline outputs stay on files.
- **Roles:** `admin` (everything: process events, add events, Trust & Ops), `rm` (view, log outcomes/notes, export, Ask), `viewer` (read-only). API enforces per endpoint (403); UI hides what the role can't do.
- **Login:** email + password (stdlib `hashlib.pbkdf2_hmac`), HMAC-signed session cookie (httpOnly, SameSite=Lax, 12 h) using `SESSION_SECRET` (generated into `api/state/` if unset). Next.js rewrites `/api/*` → `http://127.0.0.1:8000/api/*` so the cookie is same-origin; `middleware.ts` redirects to `/login` without a session. Seeded demo users `admin@finsight.demo`, `rm@finsight.demo`, `viewer@finsight.demo` (password `demo1234`), listed on the login page as "Demo accounts". Polished login screen in the design system.
- **Security:** fix all items in the security findings list (URL gate on create + redirect hops, PDF-only docs endpoint, JSON content-type + Origin check on writes, uvicorn bound to 127.0.0.1, CSV escaping).
- **Tests (tier 1):** viewer gets 403 on run/create/rm PUT; rm gets 403 on run; no session → 401; the FINDINGS tests.
