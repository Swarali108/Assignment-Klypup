# What if…

Four questions an engineer will ask, each answered from the code and the logs. All costs come
from `outputs/runs.csv` and `cost_log.csv`. They cover 24 fresh runs (nothing reused) across 18 real events
(IPOs, buybacks, an exchange offer for sale), measured on 13–16 Nov 2026. One early run that
failed before prices were configured is left out.

| First-run cost per event | |
|---|---|
| median | **$0.0098** |
| highest | $0.0206 (a 26-call IPO with 3 strong-model name checks) |
| this week's new IPO | $0.0154 |
| a rerun with nothing changed | $0.0000 (every model answer reused from `cache/llm`) |

Spend by agent across those runs: reading the tables (`extract_*`) is 71–100% of every event's
cost but one. Briefs are 0–27%. The strong-model name check (`identity`) is 0% on most events,
but on one buyback with many similar names it reached 53%, leaving the tables at 36%.

---

## 1. The budget drops to $0.50 per event. What is cut first?

**Today: nothing.** The most expensive first run on record is $0.0206, 24× under $0.50. The
limit that matters is the same one as at $2: a pathological filing. That means a huge holder
table that needs a completeness retry, dozens of callable people, and many unsure name pairs.

For that worst case there is now a switch, `BUDGET_MODE=lean` (`config/budget.py`, used in
`run.py`). It cuts in this order, cheapest loss first:

1. **The strong model for unsure name pairs** (`agents/identity.py` `ask_strong_model`). In
   lean mode `run.py` passes `_no_strong_model`, so an unsure pair stays two people and is
   flagged "identity … unsure". The RM sees a possible duplicate instead of a merge. Nothing
   wrong is invented. This is the single most expensive call per token.
2. **Model-written briefs beyond the top `LEAN_MODEL_BRIEFS` (5) people.** The rest get the
   code template (`agents/brief.py` `_template_result`). It has the same checked numbers in
   plainer words. The ranking, amounts and evidence are untouched.
3. **A hard stop in both modes.** Before every brief call, `config/budget.py`
   `model_brief_allowed` checks this run's spend in the cost log. Once it reaches 90% of the
   event budget ($2 normal, $0.50 lean), every remaining brief is a template. A run cannot
   overshoot on briefs.

**Never cut: reading the tables.** Every number on the call list is a quote the model copied
and code verified on its page. Cutting `extract_*` calls means fewer people and fewer amounts,
which is the product itself. If it ever had to shrink, the lever is `pages_from` and
`choose_pages` in `agents/extract.py` (six pages per section today, four would do for most
tables). The completeness retry is the next one (`_completeness_retry`, one extra call per
short holder table).

Test: `tests/test_trace.py::test_lean_budget_mode`. The trace view shows exactly where each
cent went per agent, so the effect of `lean` can be read off the event page.

## 2. Filings only, no news. What breaks?

**Nothing in the pipeline. It already uses no news.**

- `run.py` `load_document_pages` reads PDFs only. A news URL (`doc_type: "news"` is allowed in
  `agents/spec.py`) is recorded as `"skipped": "not a pdf"` and never reaches a model.
- Discovery (`config/sources.yaml`) reads SEBI's filing lists and SEBI RSS. The NSE and BSE
  feeds are disabled on their terms, and there is no news source.
- Every price and date comes from a filing or an exchange notice: the prospectus, the
  price-band addendum, or the basis-of-allotment advertisement.

**What is lost** is timeliness on events whose only priced document is not filed yet. An
RHP-only IPO prints ₹[●] for the price, so the call list says "up to 3,702,694 shares offered;
value unknown: no verified offer price or price band" (a live example in `events/auto/`). It
never borrows a press figure. The fix is to add the exchange notice when it appears (the
rehearsal did exactly this), not to read news.

Turning news on would *add* risk: a press number is not a quote on a regulator's page. The
rule "an invented number is the worst possible failure" means news could only ever be a lead
for discovery, never a source for a figure.

## 3. An RM types a name and asks what money they have

This works today in the control-tower chat (`api/chat/`), with no new code:

1. **Reverse lookup** (`api/chat/tools.py` `reverse_lookup`). The name is normalised with the
   pipeline's own spelling rules (`agents/identity.identity_tokens`). It is then matched
   against every holder in every processed event (`appearances()`). An exact token match beats
   a partial one, so typing a full name never pulls in a relative whose longer name contains
   it. Two holders with the same tokens but different first names stay apart.
2. **Several matches** become a clarify card (`api/chat/clarify.py` `which_person`), one option
   per distinct person. **One match** returns their call card plus every filing they appear
   in, each with tier, ₹ amount, timing and confidence. A match is flagged *unsure* for a
   two-word name seen in several filings, or for a partial match.
3. **Deep dive** (`api/chat/deep_dive.py`) is optional and confirmed with a cost estimate
   first. It follows leads most-promising-first (value × recency). The leads are the same
   person in other events, family members printed in the same filing, related filings in the
   discovery index, and unprocessed related filings, which are estimated and processed only if
   confirmed. Each kind is capped (`config/chat.py` `DEEP_DIVE_CAPS`: 6/5/4/2), depth is
   limited to 2, a visited set stops loops, and the whole dive is capped at
   `DEEP_DIVE_BUDGET_USD = 0.25`.

Limits, said plainly: it only knows people in **processed** events. It does no web search, no
LinkedIn and no contact details. A name in no filing gets "no match", never a guess.

## 4. 500 events a week. What fails first?

500 a week is about 70 a day, or 3 an hour. The money is fine: about
500 × $0.010 ≈ $5 a week at the median, and $10 at the worst case on record. In the order they
would break:

1. **Discovery coverage (fails first).** `tools/discover.py` `read_source` reads **one listing
   page per source**, SEBI's newest 25 items. At 500 events a week that page turns over within
   a day, so anything filed between refreshes is missed. Main-board SEBI filings are also only
   part of the flow: SME IPOs and most buyback and offer-for-sale notices live on the exchanges,
   whose feeds are off for terms reasons. *Change:* paginate the SEBI lists back to the last
   seen item, refresh every few hours, and get permitted exchange access (a licensed feed or
   written permission). Do not scrape around a 403.
2. **Unbounded concurrency on one machine.** `api/jobs.py` `start` launches one thread and one
   subprocess per event with no queue. Each subprocess parses PDFs with up to 8 worker
   processes (`tools/pdf.py` `DEFAULT_MAX_WORKERS`). Twenty events at once would mean 160
   parser processes. `JOBS` is an in-memory dict that is never pruned and is lost on restart.
   Each run also copies the event's outputs aside first (`_backup`, `shutil.copytree`).
   *Change:* a persistent queue (a SQLite table is enough) with 2–4 workers and
   `MAX_WORKERS` split between them. Prune finished jobs after a day.
3. **PDF to text is the time sink.** 27 s of the rehearsal's 73 s went to text for 569 pages,
   with pdfplumber in 8 processes. At 3 events an hour that is fine. At peak (IPO weeks bunch up)
   it is the queue's bottleneck. *Change:* use a fast text pass (pdfium) for page scoring, and
   pdfplumber's layout-aware pass only on the ~60 pages a run actually reads. The page cache
   (`cache/pages/`) already makes reruns free.
4. **The CSV logs and the shared index.** The trace and run log reread the whole
   `cost_log.csv` at each step (`tools/costs.run_rows`). It grows by about 25 rows per event,
   so that is about 12,500 a week and slower every run. `outputs/index.json` (the cross-event people
   index) is read and rewritten whole by every run (`tools/people_index.link_event`), so two
   runs finishing together can lose one's update. *Change:* move cost rows, runs and the
   people index to SQLite with a run_id index and upserts. The trace's totals check
   (`tests/test_trace.py`) stays the same: every cost row of a run lands in exactly one agent
   record.
5. **Fetch limits.** `tools/fetch.py` has a 30 s read timeout, 2 retries and a 7-day cache, but
   no per-host rate limit outside discovery (which waits `POLITE_DELAY_S = 3` s). 70 RHPs a
   day at 7–10 MB each is about 0.6 GB a day from one regulator host. *Change:* a per-host
   token bucket in `fetch`, and keep downloads out of git. They already are; `cache/llm` is
   tracked because it is small and makes reruns free.

What does **not** need to change: the per-event design. Code finds the pages, the model only
copies quotes, code verifies and does the arithmetic. One event costs about a cent, and a
rerun costs nothing.
