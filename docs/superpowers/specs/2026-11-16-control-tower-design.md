# Control tower, assignment completeness, memorable login, RM setup guide (design addendum)

Date: 2026-11-16 · Due: today EOD · Owner rulings: assignment gaps first, then the new experience; I draft all docs
and make them engaging; chat is the home page; ChatGPT models; every money-spending action shows its cost and asks first.

## A. Close the assignment gaps (scored against the brief)
1. **Part C** (`docs/part_c.md` + PDF, ≤2 pages): 8–10 discovery questions each with "the answer that changes the design,
   and how"; 5-minute demo script with the one pilot-winning moment; 4-week pilot (RM count, outcome metrics: calls
   booked, meetings, new money in; what we need; what could stop it); compliance pushback paragraph + what to check (DPDP Act,
   SEBI/RBI marketing rules, DND/TRAI, firm's own policy) — labelled as not legal advice.
2. **Decision log** (≥6 real decisions with options / choice + why / what would change it), **what's broken** (one real
   wrong answer with evidence, what didn't work, where AI tools helped and misled, 2-week build order), **assumptions** —
   all from the real history of this codebase and the audit. Engaging: callouts, small diagrams, before→after numbers.
3. **A buyback/acquisition where people were paid**: find a real Indian event in the last 12 months (tender-offer buyback
   where promoters tender, or an ESOP buyback/acquisition with named recipients), add `events/<id>.json`, run it, keep it
   only if the call list shows paid people.
4. **Self-measured accuracy**: 20 people hand-checked against the printed pages (`eval/gold/people_20.json`) +
   `python -m eval.check_people` reporting hit rate per field (name, role, shares, amount, timing). Numbers go into README.
5. **Follow-on leads that really run**: person deep dive (below) with a budget, most-promising-first, a visited set and caps
   per branch kind.
6. **README**: diagram matches the code (every agent: given / returns / runs on model or code), < 10-minute setup,
   the chat agent included.

## B. Control tower (chat home)
- **Layout**: ChatGPT/Claude-familiar. Left: conversations list + nav. Centre: one prompt box, greeting, 4 suggestion chips,
  and a quiet "Today's briefing" strip (top 3 calls, new events) that collapses once a conversation starts.
- **Agent flow (visible as steps, each with model + cost + time)**: understand (code rules first, then `openai/gpt-6-luna`)
  → **clarify** when ambiguous (question + clickable options, e.g. "3 people match 'Sharma'") → plan (`openai/gpt-6.1-terra`
  only for multi-step questions) → tools (code: search people/events, today, calendar, person card, reverse lookup,
  process event, deep dive) → verify (code: every digit in prose must exist in tool results; otherwise removed) → answer
  (short prose + structured cards rendered from tool data).
- **Cost preview + confirmation**: any action that spends money (process an event, deep dive, multi-step research) first
  returns an itemised estimate (steps, model, calls, $ low–high, seconds; from measured history per step kind) and a confirm
  button; nothing runs until the RM confirms. Exact lookups cost $0 and run straight away.
- **Person deep dive** (reverse tree run): same person across processed events (normalised names, flags unsure matches),
  related filings in the discovery index, family/household, evidence pages; optional follow-on processing of related events
  with budget (default $0.25), max branches per kind, visited set, most promising first. Each branch is estimated and shown.
- **Models**: via OpenRouter with the existing key; prices from OpenRouter `/models` (fetched 2026-11-15) added to the price
  table with that date. Per-question cap $0.05 unless the RM confirms a larger estimate.

## C. Memorable login + RM setup guide
- **Login**: one signature, memorable visual moment (impeccable skill), still calm and premium; demo accounts listed.
- **Setup guide** on first sign-in (per user, stored in DB): (1) your coverage: event types, minimum ticket size (₹ Cr),
  (2) your book: upload a CSV of client names → people who are already clients are flagged "In your book", (3) alerts
  preference, (4) a 4-stop product tour (control tower, Today, evidence click, cost confirmation). Skippable; re-open from
  the user menu. Preferences filter the briefing and Today.

## Non-goals
Real alert delivery (email/WhatsApp), DIN extraction, OCR, new event types beyond what the paid buyback needs.
