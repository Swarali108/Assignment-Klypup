# FinSight end-to-end suite (Playwright)

The app must already be running (`./demo.sh start`): web on :3000, API on 127.0.0.1:8000. The suite never starts or stops it.

```bash
cd web
npx playwright test                       # everything: desktop 1440x900 + the @mobile subset at 390x844
npx playwright test e2e/03-chat.spec.ts   # one area
npx playwright test --project=mobile      # mobile subset only
npm run e2e:report                        # open the HTML report (../../e2e-report)
```

Every test fails on page errors, console errors and failed `/api` requests (4xx/5xx); permission tests announce the 401/403 they expect with `guard.allow()`.
Sessions are one `storageState` per role (admin, rm, viewer, head, newrm), created over the API in `global-setup.ts`.

**Cost:** the suite uses saved model answers and only a few paid calls (one call script, one two-model comparison on cheap models), well under $0.30 per run, and no Bright Data request. It never presses a public-lookup button and never runs discovery.

**Leaves the demo data as it found it:** `global-teardown.ts` deletes conversations the run created, unfollows what it followed, undoes review decisions, restores call statuses/assignments exactly, resets new.rm@'s setup guide + client book and the daily-brief flags (so new.rm@ sees the guide and the brief on the next sign-in). It needs the `sqlite3` CLI and the local `api/state/app.sqlite` (override with `E2E_DB`); without them the SQL part is skipped.

| File | Area |
| --- | --- |
| 01 | sign-in, redirects, wrong password, roles and navigation |
| 02 | setup guide (new.rm@), tour, daily brief sheet |
| 03 | control tower: chips, clarify, focus, call script, estimate + confirm, context meter, model switcher, compare, history, exports, print routes |
| 04 | Today: tiers, households, filters (remembered), logging a call, CSV |
| 05 | person page: call card vs API, evidence viewer, trail, public info, call log, watch |
| 06 | Events: feed + SEBI/NSE/BSE badges, single events, Process now, add-from-links dialog |
| 07 | Sources, Calendar, Network |
| 08 | Trust & Ops, token panel, accuracy, health, pipeline console |
| 09 | Team, assignments, review queue (decide + undo) |
| 10 | weekly short list, boardroom mode, shortcuts, home date line |
| 11 | API permission matrix, CSRF guard |
| 12 | mobile subset + no-horizontal-overflow per page |
