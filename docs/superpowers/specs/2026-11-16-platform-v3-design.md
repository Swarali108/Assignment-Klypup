# Platform v3: person trail, admin console, production mode, business + engineering extras (2026-11-16)

Owner asks: no sample or demo data at all in production; select a person → see the whole process the pipeline used to
find them; admin can run the pipeline manually; plus extras the owner picked: Head of RMs outcomes dashboard, human
review queue, watchlists + in-app alerts, accuracy dashboard, model switcher + cost comparison, run diff + data
freshness, system health page.

## Core
1. **Person trail ("How we found them")** — on the person page: source documents → pages the locator chose (score, why)
   → each extracted quote (model, cached/fresh, prompt version) → every check per field (passed / rejected + reason;
   table-row check) → name merges + strong-model checks + family links → money rules (formula, inputs with pages, lock-in
   rule citation) → rank (tier, score parts) → brief (model, placeholders, fallback) → enrichment (LinkedIn / web, match
   level) → cost and time attributable to this person. Built from extract.json, people.json, ranked.json, briefs.json,
   trace.json, cost.json, enrichment cache. `GET /api/people/{e}/{p}/trail`.
2. **Admin pipeline console** (`/admin/pipeline`): run an event (all steps or one step), cached vs fresh (fresh → estimate
   + confirm), re-run one person's brief, live logs (SSE), run history with **diff** (people added/removed, amounts,
   tiers changed) and **data freshness** (fetched date per fact, stale badges, re-check when a new event touches a person).
3. **Production mode** (`APP_ENV=production`): no demo users seeded, no demo accounts on the login page, first admin from
   `ADMIN_EMAIL` + `ADMIN_PASSWORD` (or a CLI), no sample book download, no chat mock, template/example events excluded.
   Local demo mode unchanged.

## Business extras
4. **Head of RMs dashboard** (`/team`, new role `head` + admin): assign people to RMs; outcomes per RM and per event type:
   calls logged, meetings booked, follow-ups due, won (new money in, amount entered by the RM), time from event to first
   call — the Part C pilot metrics, live.
5. **Human review queue** (`/review`, admin/head): unsure name matches, unsure person-vs-organisation, low-confidence rows →
   confirm / reject / merge; decisions persist (DB + `outputs/overrides.json`), re-rank the event, and show in the trail.
6. **Watchlists + in-app alerts**: follow a person or company; bell in the top bar; alerts when a followed name appears in a
   new event, a lock-in ends within N days, a block deal / insider sale lands, or a re-run changes their amount.

## Engineering extras
7. **Accuracy dashboard** (`/ops/accuracy`): eval.check_people results — hit rate per field, every miss with its page
   link, re-run button.
8. **Model switcher + cost comparison** (chat): choose from an allow-list (ChatGPT models + open-source models priced from
   OpenRouter /models); "compare" runs one question on two models side by side with cost and latency.
9. **System health** (`/ops/health`): scheduler, sources (blocked?), cache size + hit rate, today's spend vs caps (model
   $/day, Bright Data requests/month), failed jobs with retry.
