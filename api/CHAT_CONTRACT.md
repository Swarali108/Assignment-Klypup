# Control tower chat: API contract (shared by the agent backend and the web UI)

All routes need a session (see api/auth.py). Roles: viewer may ask $0 questions only; rm may confirm estimates up to
$0.50; admin unlimited (still confirms). Money-spending actions NEVER run without a confirm_token.

## POST /api/chat  → text/event-stream
Request JSON: `{ "conversation_id": str | null, "message": str, "confirm_token": str | null, "choice": str | null }`
- `message`: the RM's text (or the label of a clicked suggestion).
- `choice`: the `value` of a clicked clarify option (message may then be empty).
- `confirm_token`: from an `estimate` event; runs exactly that action.

SSE events (JSON in `data:`; `event:` = type):
- `meta`    `{conversation_id, title}` (first event)
- `step`    `{id, label, status: "running"|"done"|"failed"|"skipped", model: str|null, cost_usd: number, ms: number, detail: str|null}`
  Labels in RM words: "Understanding your question", "Checking 18 events", "Asking a quick question", "Planning",
  "Reading SEDEMAC filings", "Checking every number", "Writing the answer".
- `clarify` `{question, options: [{label, value}], allow_free_text: bool}` → turn ends; UI posts `choice`.
- `estimate` `{action: {kind: "process_event"|"deep_dive"|"research", title, target}, cost_usd_low, cost_usd_high,
   cost_inr_low|null, cost_inr_high|null, seconds_low, seconds_high,
   breakdown: [{step, model, calls, cost_usd}], basis: str, confirm_token, expires_at (unix seconds, null when this role cannot confirm), can_confirm, blocked_reason}` → turn ends; UI shows a confirm card.
- `text`    `{delta}` streamed prose. Every digit in it was verified against tool results (unverified digits are removed).
- `cards`   `{kind: "people"|"events"|"person"|"calendar"|"lineage", title, items: [...]}` items reuse the view models
   from api/CONTRACT.md (person rows, event rows, call card), so the UI reuses existing components.
- `done`    `{total_cost_usd, models: [{model, calls, cost_usd}], seconds}`
- `error`   `{message}` (RM words)

## GET /api/chat/conversations → `[{id, title, updated_at}]` (current user only)
## GET /api/chat/conversations/{id} → `{id, title, messages: [{role, text, cards[], steps[], estimate|null, created_at}]}`
## DELETE /api/chat/conversations/{id}

## GET /api/me/preferences → `{onboarded: bool, event_types: [str], min_ticket_cr: number|null, alerts: "daily"|"weekly"|"off",
   book_count: int}`;  PUT same shape (partial ok)
## POST /api/me/book  (JSON `{names: [str]}` parsed client-side from CSV; ≤ 5,000) → `{book_count}`; DELETE clears.
People rows/cards gain `in_book: bool` when the person's normalised name matches a book name.

## Suggestion chips (home): "Who came into money this week?", "What money does Manish Sharma have?",
   "Cash in hand above ₹50 Cr", "Process a new IPO from a link".

---
# v2 (2026-11-16): memory, compression, prompt caching, verified streaming, call scripts, history, exports

**Why:** the owner's test showed the chat forgets context ("script for the call" after a Kusum deep dive → generic clarify),
ignores time windows ("this week" listed 12–25-day-old money), and offers generic clarify options.

## Conversation memory (server)
- Every turn builds its context as: **[stable system prefix ≥ 1,024 tokens, byte-identical across turns]** + conversation
  state (rolling summary + focus entities) + the last K raw turns + the new message. The stable prefix is first so
  provider prompt caching hits (OpenAI models cache prefixes automatically; record `cached_tokens` from usage).
- **Focus entities**: people/events the conversation is about (from tool results and clicks). A message with no explicit
  entity ("ready me a script for the call", "him", "its about kusum") binds to the current focus; clarify only when two or
  more focus entities fit. Clarify options must be the candidate entities/slots, never the generic home suggestions.
- **Smart compression**: when the context passes a threshold (config/chat.py, e.g. 3,000 tokens of history), older turns are
  summarised by the cheap model into a state block (facts as references to tool data, entities, open questions; no new
  digits — verified). Each compression is recorded.
- **Time windows**: "today / this week / this month / last N days / upcoming" filter by money date; if nothing falls in the
  window, say so plainly and offer the nearest results ("No one this week; the latest were 12–25 days ago").

## SSE additions
- `text` `{delta, final: bool}` — streamed **sentence by sentence**; each sentence passes the digit verifier before it is sent.
- `context` `{prompt_tokens, cached_tokens, history_tokens_before, history_tokens_after, compressed: bool, turns_kept,
   focus: [{kind: "person"|"event", event_id, person_id|null, label}]}` (once per turn, before `done`).
- `focus` `{focus: [...same...]}` whenever the focus changes.
- `cards` kind `"script"`: `{title, person: {event_id, person_id, name}, sections: [{heading, lines: [str]}]}` — call script
  (opening, why now, 3 questions, likely objections + answers, next step); every number filled by code from the call card.
- `done` adds `tokens: {input, output, cached_input}`, `saved_usd_by_cache`.

## New endpoints
- `GET /api/chat/conversations?q=` (search titles + message text) → `[{id, title, updated_at, messages, cost_usd}]`
- `GET /api/chat/conversations/{id}` messages gain `meta: {models: [{model, calls, cost_usd}], tokens_in, tokens_out,
   cached_in, cost_usd, context_tokens, compressed, focus}`
- `GET /api/chat/conversations/{id}/export.md` — the whole thread as a clean Markdown report (answers, cards as tables,
   sources as links, per-turn cost).
- `GET /api/people/{event_id}/{person_id}/callpack.md` — call card + brief + call script + evidence links.
- `GET /api/ops/tokens` → `{questions, avg_cost_usd, cache_hit_rate, cached_tokens, saved_usd_by_cache, compressions,
   tokens_saved_by_compression, by_model: [...]}`
- Web print routes produce PDFs via the browser: `/history/{id}/print`, `/people/{e}/{p}/print`.

## v2 as built (backend notes for the UI; all additive)
- `text` events: one per verified sentence, `{delta, final: false}`; each prose block ends with `{delta: "", final: true}`
  (a turn may have two blocks, e.g. an estimate summary). Concatenating `delta`s still gives the full text.
- Order at the end of every turn: optional `focus` → `context` → `done`. `done.tokens = {input, output, cached_input}`
  and `done.saved_usd_by_cache` (net of the provider's cache-write premium, so it can be negative on a first call).
- `cards` kind `script` also carries `channel: "call"|"whatsapp"|"email"`, `written_by: "model"|"template"|"reused"`,
  `facts: {amount, timing, company, event, confidence}` and `items: []` (so list renderers never break). Call sections:
  Opening · Why now (for you, not to read out) · Three questions · Likely objections · Next step. WhatsApp: Greeting ·
  WhatsApp message · After sending. Email: Subject · Email · After sending.
- A `people`/`calendar` card shown as a time-window fallback has `outside_window: {words, from, to, span}` and a title
  starting "Nearest money dates, outside …"; never render it as inside the window.
- Clarify option values (post as `choice`): `person:<event_id>/<person_id>`, `script:<event_id>/<person_id>|<call|whatsapp|email>`,
  `deep:<e>/<p>`, `lookup:<name>`, `process:<event_id>`, `ask:<text>`. Options are always real people or actions on the
  focused person, never the home chips.
- Message `meta` also has `cache_write`, `saved_usd_by_cache`, `seconds`, `provider_calls`, `local_cache_hits`, `by_step`.
- `GET /api/ops/tokens` needs the ops permission (admin); it also returns `total_cost_usd`, `input_tokens`,
  `provider_calls`, `local_cache_hits`, and per model `cache_write_tokens` and `cache_hit_rate`.
- Settings (config/chat.py): `CHAT_COMPRESS_TOKENS` (default 3000), `CHAT_KEEP_TURNS` (default 4).

---
# v3a (2026-11-16): deep dive public lookups

- A deep dive estimate gains breakdown rows for Bright Data lookups: `{step, model: null, calls: <worst-case requests>, cost_usd: 0, brightdata_requests: n, cached, kind: "linkedin"|"web"}`.
  They are listed only when a Bright Data token is set, the holder is a person (LinkedIn), the switch is on (`LINKEDIN_ENRICHMENT`), and the worst case fits the monthly cap (`BRIGHTDATA_REQUEST_CAP`).
  A saved copy (cache hit) shows 0 requests. The confirm token's target is `<event>/<person>|<approved event ids>|<linkedin,web>`; only the kinds named there run.
- `lineage` nodes of kind `linkedin` (parent: "Public LinkedIn profile", children: one per candidate, at most 3) carry `match: "likely"|"unconfirmed"` and the reason in `detail`;
  kind `web` children (at most 5) carry title, `source` link and the label "from web search, not verified". Node `status` may be `candidate | skipped | processed | failed | followed`.

# v2.1 (2026-11-16): review fixes
- `POST /api/chat` accepts `focus: [{kind, event_id, person_id, label}] | null`. When present it REPLACES the server's focus
  (each person is checked against the data; the pending clarify is cleared). Removing someone from the "Talking about" chip
  therefore takes effect on the next turn. `null`/absent keeps the stored focus.
- Message `meta.context` is the streamed `context` event, stored exactly (provider figures); the web app replays it on reopen.
- `GET /api/people/{event_id}/{person_id}/callscript` -> `{script: <script card>, source: "chat"|"template"}`: the script the
  print page shows (the newest one from this user's chats, else the code template). The PDF never writes its own script.
- Name matching in memory is by coverage: a message names someone when it holds their given (first) name or two of their
  name words; the entity explaining the most words wins, the focus only breaks ties. A leftover request word ("when",
  "keep", "tomorrow s") is never a name unless a lookup or the memory finds someone; otherwise the focus is used.
