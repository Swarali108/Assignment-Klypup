# Chat v2 + workflow deep dive (design addendum, 2026-11-16)

Owner asks: fix the broken chat flow (context lost, generic clarify, "this week" ignored); every conversation and message
visible; each conversation carries context; smart compression as context grows; prompt caching; streaming; download
reports; dig into the whole workflow to impress the evaluators.

Shapes: `api/CHAT_CONTRACT.md` v2. Calls I made: sentence-level verified streaming (raw token streaming could flash an
unverified digit); compression by the cheap model with digits verified; PDFs via print routes (no server PDF stack);
OpenAI automatic prefix caching with a ≥1,024-token stable prefix, measured from `cached_tokens`.

Workflow deep dive (to impress the evaluators): rehearse the live call on an IPO that listed in the last 30 days and
is not yet processed — fresh, from a link, timed — and fix any generic issue it shows; persist a per-run **agent trace**
(which agent ran, why, given/returns, model, tokens, cost, cached) and show it live while processing ("which agent is
running now and why") with "this run vs first run" cost; document readiness for the "change one requirement" prompts
($0.50 budget mode, filings-only, reverse lookup, 500 events/week).
