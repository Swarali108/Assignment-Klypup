# Deploying FinSight: Vercel + Railway + Neon, all in Singapore

This guide takes the demo from `./demo.sh start` on a laptop to a public URL with three managed services.
Each one runs in Singapore, so a page load never crosses an ocean:

| Piece | Runs on | Region | What it does |
| --- | --- | --- | --- |
| Web app (`web/`, Next.js 16) | **Vercel** | `sin1` (Singapore) | Pages, the sign-in gate, and the `/api/*` proxy to the API |
| API + pipeline + discovery (FastAPI, `run.py`, `discover.py`) | **Railway** | Southeast Asia, `asia-southeast1-eqsg3a` (Singapore) | Every `/api` route, processing runs, evidence rendering |
| App database (users, call notes, chat history, preferences) | **Neon Postgres** | AWS Asia Pacific (Singapore), `aws-ap-southeast-1` | The small app state. Pipeline outputs stay on files |
| Model calls | OpenRouter | (its own) | Only for processing new events and model-written chat answers |

Every platform fact below was checked against the vendor's own docs on 2026-11-15. The [appendix](#appendix-sources)
lists each source. Prices are **estimates**: check them again before you commit money.

You need about **45 minutes** the first time. Steps 1 to 3 are each about 10 minutes, and the smoke test takes 5.

---

## Contents

- [Architecture](#architecture)
- [Before you start](#before-you-start)
- [Step 1: Neon (database, Singapore)](#step-1-neon-database-singapore)
- [Step 2: Railway (API, Singapore)](#step-2-railway-api-singapore)
- [Step 3: Vercel (web app, sin1)](#step-3-vercel-web-app-sin1)
- [Step 4: Close the loop (origins and cookies)](#step-4-close-the-loop-origins-and-cookies)
- [Step 5: Smoke test](#step-5-smoke-test)
- [Where the data lives, and first-boot seeding](#where-the-data-lives-and-first-boot-seeding)
- [Demo users](#demo-users)
- [Running the pipeline and discovery in production](#running-the-pipeline-and-discovery-in-production)
- [Custom domain and cookies](#custom-domain-and-cookies)
- [Preview environments](#preview-environments)
- [Cost estimate](#cost-estimate)
- [Security checklist](#security-checklist)
- [Troubleshooting](#troubleshooting)
- [Rollback](#rollback)
- [Local check before you deploy](#local-check-before-you-deploy)
- [Appendix: sources](#appendix-sources)

---

## Architecture

```mermaid
flowchart LR
    B["Browser<br/>(RM, admin, viewer)"]
    subgraph V["Vercel"]
        MW["Sign-in gate (proxy.ts)<br/>Routing Middleware, all regions"]
        FN["Next.js pages + server components<br/>Functions in sin1 (Singapore)"]
        RW["/api/* rewrite<br/>(external rewrite to API_ORIGIN)"]
    end
    subgraph R["Railway: Southeast Asia (Singapore)"]
        API["FastAPI: python -m api<br/>one process, one replica"]
        PIPE["run.py / discover.py<br/>subprocesses of the API"]
        VOL[("Volume at /data<br/>outputs, events, cache, cost_log")]
    end
    NEON[("Neon Postgres<br/>aws-ap-southeast-1<br/>pooled URL (PgBouncer)")]
    OR["OpenRouter<br/>(model calls)"]
    SRC["SEBI filings<br/>(public documents)"]

    B -- "HTTPS, same origin" --> MW
    MW --> FN
    B -- "/api/* (cookie travels)" --> RW
    RW -- "HTTPS" --> API
    MW -- "GET /api/auth/me" --> API
    FN -- "server-side fetch, cookie forwarded" --> API
    API --> VOL
    PIPE --> VOL
    API -- "users, notes, chat" --> NEON
    API -. "new processing, model answers" .-> OR
    PIPE -. "download filings" .-> SRC
```

The browser only ever talks to the Vercel domain. `/api/*` is rewritten to the Railway API, so the session cookie
is first-party and no CORS is needed. The API keeps a CSRF check: a write must be JSON and, when the browser sends an
`Origin`, that origin must be in `ALLOWED_ORIGINS`.

> Region note: Vercel's **Functions** (pages, server components) run in the region you pick (`sin1`). The sign-in gate
> in `web/proxy.ts` is **Routing Middleware**, which Vercel deploys to all regions whatever you pick. It makes one
> small call to the API per page view.

---

## Before you start

**Accounts.** A GitHub account with this repository pushed to it, plus accounts on Vercel, Railway and Neon. Optional:
an OpenRouter key, needed only to process new events or get model-written chat answers.

**Tools on your machine.**

- `openssl`, to make secrets.
- `curl`, for the smoke test.
- Optional: `psql` to look inside Neon, and the [Railway CLI](https://docs.railway.com/cli) for `railway ssh`.

**Make the secrets now and keep them in a password manager:**

```bash
openssl rand -hex 32   # SESSION_SECRET (signs the session cookie; 64 hex characters)
```

**Decide the names.** This guide uses these placeholders. Replace them everywhere:

| Placeholder | Example |
| --- | --- |
| `<web-domain>` | `finsight.vercel.app` (or your own, e.g. `finsight.example.com`) |
| `<api-domain>` | `finsight-api-production.up.railway.app` |
| `<neon-pooled-url>` | `postgresql://neondb_owner:•••@ep-xxxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require` |

---

## Step 1: Neon (database, Singapore)

The region **cannot be changed after the project is created**, so pick Singapore now.

1. Open the Neon Console and click **New Project**.
2. **Project name:** `finsight`.
3. **Region:** **AWS Asia Pacific (Singapore)**, id `aws-ap-southeast-1`. The cloud provider is part of the region.
4. Under **Services**, **Postgres database** is on by default. Expand it to choose the Postgres version. The app was
   verified against Postgres 17.
5. Click **Create project**.

Neon creates:

- a branch named `production` (named `main` if created through the API or CLI);
- a database `neondb`;
- an owner role `neondb_owner`.

### Get the two connection strings

Click **Connect** in the top navigation. In the **Connect to your branch** modal:

- **Pooled (use this for the app).** Leave **Connection pooling** on, which is the default. The host gets a
  `-pooler` suffix:

  ```text
  postgresql://neondb_owner:<password>@ep-xxxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
  ```

- **Direct (keep for admin work).** Turn **Connection pooling** off. The host has no `-pooler` suffix. Use this one
  for `psql` sessions, `pg_dump` / `pg_restore`, and anything that needs session features.

**Why the pooled URL works with this app.** Neon's pooler is PgBouncer in **transaction mode**. In that mode
SQL-level `PREPARE`, `SET`, `LISTEN` and session advisory locks are not supported. psycopg 3 prepares a statement
automatically once it has run more than `prepare_threshold` times on one connection. `api/db.py` turns that off with
`prepare_threshold=None` on every connection, which psycopg's docs recommend behind a pooler. The app uses none of
the other unsupported features.

This was verified locally against Postgres 17 behind PgBouncer 1.26 in `pool_mode=transaction` with
`max_prepared_statements=0`. That covered sign-in, call notes, chat, preferences, the client book and deletes, with
no errors. That local run used `sslmode=disable`, so TLS with `channel_binding=require`, and Neon itself, are not
yet exercised. The [smoke test](#step-5-smoke-test) is the first run against Neon.

**`sslmode=require&channel_binding=require`.** Keep both exactly as Neon gives them. Neon requires TLS on every
connection. The API image's libpq (from `psycopg[binary]` 3.3.9) supports channel binding.

**Tables.** You create nothing by hand. On start, the API runs `CREATE TABLE IF NOT EXISTS` for `users`, `rm_state`,
`chat_conversations` and `chat_messages`, adds any missing columns, and then seeds the demo users.

### Optional: a dedicated app role

`neondb_owner` works. For least privilege, create a role with SQL over the **direct** URL. Roles made in the Console
get `neon_superuser`; roles made with SQL get only basic privileges:

```sql
CREATE ROLE finsight_app WITH LOGIN PASSWORD '<12+ mixed characters, 60+ bits of entropy>';
GRANT USAGE, CREATE ON SCHEMA public TO finsight_app;   -- CREATE: the app creates its own tables on first start
```

Then build the pooled URL with `finsight_app` and its password instead of `neondb_owner`.

### Scale to zero (cold starts)

On the Free plan, compute suspends after **5 minutes** of inactivity. This cannot be turned off on Free. The next
query wakes it "within a few hundred milliseconds." The API opens a fresh connection per request with a 10-second
connect timeout, so the first click after a quiet spell is only slightly slower. Paid plans can turn scale to zero off.

---

## Step 2: Railway (API, Singapore)

The API image is `Dockerfile` at the **repo root**. It has to be at the root because the API runs `run.py` and imports
`agents/`, `tools/`, `config/` and `ui/components.py`. Railway uses a root-level `Dockerfile` automatically, and the
build log says `Using detected Dockerfile!`.

> **Why there is no `railway.json` here.** Railway now marks Config as Code (`railway.json` / `railway.toml`) as
> deprecated. New services cannot opt into it, and existing files stop being read on **2026-12-01**. Its
> replacement, Infrastructure as Code (`.railway/railway.ts`), does not yet document a Dockerfile path or cron
> schedule. Every Railway setting below is therefore made in the dashboard, and this table is the record of it:
>
> | Setting | Value |
> | --- | --- |
> | Source | this repo, production branch; **Root Directory empty** |
> | Builder | Dockerfile (auto-detected at the root) |
> | Start command | **empty** (the image's `CMD ["python", "-m", "api"]`) |
> | Region | Southeast Asia, `asia-southeast1-eqsg3a` |
> | Replicas | **1** (see the next paragraph) |
> | Healthcheck path | `/api/health` (timeout: default 300 s) |
> | Volume | mounted at `/data` |
> | Public domain | generated, `*.up.railway.app` |

**Keep exactly one replica and one process.** Running jobs and their live progress are held in the API process's
memory. A Railway volume can also attach to only one service. `python -m api` starts a single uvicorn worker on
purpose.

### 2.1 Create the service

1. In Railway, click **New Project → Deploy from GitHub repo**, pick this repository, and pick the branch you deploy
   from.
2. Open the service's **Settings** and set:
   - **Root Directory:** leave **empty**.
   - **Start Command:** leave **empty**.
   - **Region:** choose **Southeast Asia (Singapore)**, identifier `asia-southeast1-eqsg3a`.
   - **Healthcheck Path:** `/api/health`.

   Railway's dashboard groups these settings under its own section headings, which can move between releases.

### 2.2 Add the volume (persistent files)

1. Press `⌘K` (or right-click the project canvas), choose to create a **Volume**, and select the API service when
   prompted.
2. Set its **mount path** to `/data`.

The default size is 0.5 GB on Free/Trial, 5 GB on Hobby and 50 GB on Pro. Hobby and Pro can resize. The shipped data
is about 9 MB, plus whatever filings you download later.

Two Railway behaviours matter here:

- The volume is mounted **when the container starts, not during the build**. The seeding therefore happens in
  `python -m api` at start-up (see [first-boot seeding](#where-the-data-lives-and-first-boot-seeding)), never in the
  Dockerfile.
- A service with a volume has a **short downtime on every redeploy**, even with a healthcheck, because two
  deployments cannot mount the same volume at once.

### 2.3 Variables

In the service's **Variables** tab, add these:

| Name | Example | Required? | Secret? | What it does |
| --- | --- | --- | --- | --- |
| `APP_ENV` | `production` | **yes** | no | Turns on production mode: the API refuses to start without a `SESSION_SECRET` of 32+ characters and never writes a generated secret file; **no demo users are seeded** (see `ADMIN_EMAIL`); the login page shows no demo accounts; no sample book download; the chat preview mock is forced off; `events/example*.json` and any event whose document link is not `http(s)` are left out of every list. Local mode (unset) is unchanged |
| `SESSION_SECRET` | output of `openssl rand -hex 32` | **yes** | **yes** | Signs the session cookie. Changing it signs everyone out |
| `DATABASE_URL` | `<neon-pooled-url>` | **yes** (for Neon) | **yes** | Users, call notes, chat, preferences. Unset means SQLite on the volume (`/data/api/state/app.sqlite`) |
| `ALLOWED_ORIGINS` | `https://<web-domain>` | **yes** | no | Comma-separated origins allowed to **write** (POST/PUT/PATCH/DELETE). Set means it **replaces** the localhost default. Add each custom domain |
| `COOKIE_SECURE` | `1` | recommended | no | `1`: the cookie is always `Secure`. `0`: never. Unset: `Secure` when the request came over HTTPS (`X-Forwarded-Proto`) |
| `DATA_DIR` | `/data` | **yes** (with the volume) | no | Writable files live here. See [seeding](#where-the-data-lives-and-first-boot-seeding) |
| `RAILWAY_RUN_UID` | `0` | **yes** (with the volume) | no | The image runs as a non-root user (uid 10001). Railway documents that non-root images hit permission errors on volumes, and that this variable is the fix. Without it the API exits at start with that advice |
| `LLM_API_KEY` | your OpenRouter key | no | **yes** | Needed only to process new events and for model-written chat answers. Without it, everything already processed still works, including exact-lookup questions |
| `LLM_MODEL` | `anthropic/claude-haiku-5.5` | with a key | no | The cheap model. Keep this value: the shipped `cache/llm` was made with it, so reruns replay at $0 |
| `LLM_MODEL_STRONG` | `anthropic/claude-sonnet-5.5` | with a key | no | Used only for identity pairs that code cannot settle |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | no | no | This is already the default |
| `MAX_WORKERS` | `2` | recommended | no | PDF-reading worker processes during a run (default 8). 2 suits a small container |
| `HOST` | `0.0.0.0` | no | no | The image already sets `0.0.0.0`. Use `::` if another Railway service will call the API over the private network |
| `PORT` | (injected) | no | no | Railway injects it, and `python -m api` listens on it. **Do not set it yourself** |
| `FINSIGHT_WARM` | `1` | no | no | `0` skips pre-rendering the top evidence pages at start |
| `DISCOVERY_ENABLED` | `1` | no | no | The in-API scheduler: `1` (default) checks the sources every `DISCOVERY_EVERY_HOURS` while the API runs; `0` turns it off. See [scheduled discovery](#running-the-pipeline-and-discovery-in-production) |
| `DISCOVERY_EVERY_HOURS` | `3` | no | no | Hours between automatic checks (default 3) |
| `AUTO_PROCESS_DAILY_CAP_USD` | `1.00` | no | no | Most the automatic runs may spend per day (India time, default $1.00). `0` processes nothing automatically; everything waits as "Needs approval" |
| `EXCHANGE_SOURCES` | `off` | no | no | `on` (default) also reads NSE and BSE; `off` reads SEBI only. Set `off` in production unless you have checked the exchanges answer your server (they likely refuse cloud addresses) |
| `DISCOVERY_SINCE_DAYS` | `30` | no | no | How far back a check looks (default 30 days) |
| `AUTO_PROCESS_MAX_EVENTS` | `25` | no | no | At most this many events are processed in one check (default 25) |
| `ADMIN_EMAIL` | `head.of.rms@yourfirm.com` | **yes** (production) | no | With `APP_ENV=production` no demo users are created. The first admin is created from this email and `ADMIN_PASSWORD` the first time the API starts (or on the first sign-in attempt). An existing user is never overwritten. If either is unset nobody is created and the API logs a warning |
| `ADMIN_PASSWORD` | a long random password | **yes** (production) | **yes** | The first admin's password. Change it after the first sign-in; the variable is only read when the user does not exist yet |
| `DEMO_ACCOUNTS` | `1` | no | no | Production only. Also creates the rm, head, viewer and new-RM demo accounts (password `demo1234`, public) and shows their buttons on the login page. The admin demo account is never offered in production. rm and head can still spend through chat (up to $0.05 a question, $0.50 a confirmed action, no daily total), so set a spending limit on the OpenRouter key. Unset it to hide the buttons and refuse those accounts at sign-in |
| `ADMIN_NAME` | `Administrator` | no | no | Display name of that first admin |
| `STALE_AFTER_DAYS` | `14` | no | no | A source filing fetched longer ago than this shows a "Stale" badge on the call card, the event page and in the evidence viewer |
| `MODEL_DAILY_CAP_USD` | `5` | no | no | Shown on `/ops/health` as the day's model-spend limit. Unset: the page says no daily limit is set. It is a display limit; the per-event budget (`BUDGET_MODE`) is what stops a run |
| `BRIGHTDATA_MONTHLY_CAP` | `50000` | no | no | Monthly Bright Data request limit shown on `/ops/health` (only when the Bright Data counter is part of the build) |
| `NEXT_PUBLIC_APP_ENV` | `production` | recommended (web service) | no | Web service only. Set `APP_ENV=production` on the web service too (or this name); it forces the chat preview mock off and redirects `/sample_book.csv`. The login page also asks the API, so it hides the demo accounts either way |

You can add `DATABASE_URL` as a Railway reference to a shared variable if you prefer: `${{shared.DATABASE_URL}}`.

### 2.4 Public domain

1. Open **Settings → Networking → Public Networking** and click **Generate Domain**. You get
   `<something>.up.railway.app`, which is your `<api-domain>`. Railway issues and renews its TLS certificate.
2. If Railway asks for a target port, give the port in the deploy log line
   `Uvicorn running on http://0.0.0.0:<port>`, which is the injected `PORT`. A wrong target port is the usual cause
   of "Application failed to respond".

### 2.5 Deploy and watch the log

Push or click **Deploy**. A healthy first boot logs:

```text
DATA_DIR /data: seeded {'outputs': 154, 'events': 20, 'cache': 696, 'api/state': 0, 'cost_log.csv': 1}
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:<port> (Press CTRL+C to quit)
```

Then check it:

```bash
curl -s https://<api-domain>/api/health
# {"ok": true, "db": "postgres"}
```

`/api/health` runs `SELECT 1` against the database. It returns **503** with `{"ok": false, "db": ..., "error": "<kind>"}`
when the database is unreachable. The URL is never echoed. Railway calls it **only during a deploy**, to decide when
to switch traffic, and does not watch it afterwards.

---

## Step 3: Vercel (web app, sin1)

1. In the Vercel dashboard, select **Create New → Project**. Under **Import Git Repository**, click **Import** next to this repository.
2. **Root Directory:** click **Edit** and choose **`web`**. Vercel detects Next.js. Keep the default build command
   and output.
3. **Environment Variables**, scoped to **Production** and **Preview**:

   | Name | Example | Required? | Secret? | Notes |
   | --- | --- | --- | --- | --- |
   | `API_ORIGIN` | `https://<api-domain>` | **yes** | no | Where `/api/*` goes, and where server components and the sign-in gate call the API. No trailing slash (one is stripped anyway). **Read at build time for the rewrite, so redeploy after changing it** |

4. Click **Deploy**.

**Region `sin1`.** `web/vercel.json` already contains `"regions": ["sin1"]`, so Functions run in Singapore. On a new
project the default would be `iad1` (Washington, D.C.). Hobby allows one region, which is all this needs. To check
or change it in the dashboard, open **Settings → Functions → Function Regions**.

**No caching of API responses.** `web/vercel.json` also sends `x-vercel-enable-rewrite-caching: 0` on `/api/*`.
Vercel's CDN honours upstream `Cache-Control` on external rewrites by default for projects created on or after
2026-04-06. Every API response is per-user, and the evidence images now say `Cache-Control: private`, so the CDN
must never keep them. Both guards are in place.

**Node.js.** Vercel's default for new projects is Node 26.x, which is the version the app was built with locally.
22.x and 24.x are also available.

**Streams.** The CDN waits up to **120 s** for the first byte from an external backend. After that, a stream may run
as long as data keeps arriving at least once every 120 s. The processing stream (`/api/jobs/<id>/stream`) sends a
keep-alive every 0.4 s, and the chat stream sends its first event immediately. On the Railway side, an HTTP request
may run up to **15 minutes** if data keeps flowing, so a single page watching a run longer than that is cut off. The
job keeps running and its state is at `GET /api/jobs/<id>`.

Your web URL is the Production domain Vercel shows, `<web-domain>`.

---

## Step 4: Close the loop (origins and cookies)

The API must know the web origin, or every **write** (sign-in, call notes, chat) is refused with
`403 Requests from this site are not allowed`.

1. On Railway, set `ALLOWED_ORIGINS=https://<web-domain>`. Add more origins comma-separated, for example
   `https://finsight.vercel.app,https://finsight.example.com`.
2. On Railway, make sure `COOKIE_SECURE=1`.
3. Deploy the variable change if Railway shows it as pending, and wait until the new deployment is live.

**Why this works.** The browser posts to `https://<web-domain>/api/...` with `Origin: https://<web-domain>`. The
rewrite passes the request on to Railway, where `api/guard.py` compares the `Origin` with `ALLOWED_ORIGINS`. Origin
forwarding was verified through Next.js locally (`next start`). Smoke-test step 4 confirms it on Vercel. Exact
match only: scheme and host, trailing slash and case ignored.

---

## Step 5: Smoke test

Run these from your laptop, replacing the placeholders.

```bash
WEB=https://<web-domain>
API=https://<api-domain>

# 1. API and database
curl -s $API/api/health                      # {"ok": true, "db": "postgres"}

# 2. Sign in through Vercel exactly as a browser does; the cookie must be Secure, HttpOnly, SameSite=Lax
curl -s -D - -o /dev/null -c /tmp/finsight.jar \
  -H 'Content-Type: application/json' -H "Origin: $WEB" \
  -d '{"email":"rm@finsight.demo","password":"demo1234"}' $WEB/api/auth/login | grep -i '^set-cookie'
#   set-cookie: finsight_session=...; HttpOnly; Max-Age=43200; Path=/; SameSite=lax; Secure

# 3. Seeded data is there (19 events in the shipped data)
curl -s -b /tmp/finsight.jar $WEB/api/events | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])"

# 4. The CSRF check refuses a foreign origin
curl -s -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' -H 'Origin: https://evil.example' \
  -d '{"email":"rm@finsight.demo","password":"demo1234"}' $WEB/api/auth/login       # 403

# 5. Chat answers from rules with no model call (works without LLM_API_KEY)
curl -s -b /tmp/finsight.jar -H 'Content-Type: application/json' -H "Origin: $WEB" \
  -d '{"message":"Cash in hand above ₹50 Cr"}' $WEB/api/chat | grep -c '^event:'   # > 0, ends with "event: done"
```

Then in a browser:

1. Open `https://<web-domain>`. You land on `/login`.
2. Sign in as `rm@finsight.demo`.
3. **Today** lists calls. Open a call card and click **Called**. Reload, and the status is still there, because it is
   stored in Neon.
4. Visit **Events**, **Calendar** and **Network**.
5. Sign in as `admin@finsight.demo` and open **Trust & Ops**.
6. Sign in as `viewer@finsight.demo`. Logging a call is refused.

The same walk was scripted with a headless browser against the env-driven split (web on one port and the API on
another, with `API_ORIGIN`, `ALLOWED_ORIGINS` and `APP_ENV=production` set). Sign-in, the call card, logging an
outcome, chat, events, calendar, network and Trust & Ops worked with no console errors, and the viewer's write was
refused by role.

---

## Where the data lives, and first-boot seeding

| Data | Where in production | Survives a redeploy? |
| --- | --- | --- |
| Users, call notes, chat history, preferences, client book | Neon (`DATABASE_URL`) | yes (Neon) |
| Processed events `outputs/`, event specs `events/` (incl. `events/auto/`), model replay cache `cache/llm/`, downloaded filings `cache/fetch/` and parsed pages `cache/pages/`, discovery logs `cache/runs/`, `cost_log.csv`, `api/state/` (job backups; SQLite if no `DATABASE_URL`) | the Railway volume at `/data` | yes (volume) |
| Code, Python packages | the image | rebuilt each deploy |

**How it is wired.** `python -m api` (in `api/__main__.py`) calls `api/datadir.py` before the server starts. When
`DATA_DIR` is set, it does three things:

1. It copies the files shipped in the image (the repo's committed `outputs/`, `events/`, `cache/llm/` and
   `cost_log.csv`) into `/data` using the seed rule below.
2. It replaces `/app/outputs`, `/app/events`, `/app/cache` and `/app/api/state` with symlinks into `/data`, so the
   pipeline, discovery and API write to the volume without code changes.
3. It makes `/app/cost_log.csv` a symlink to `/data/cost_log.csv` and points `COST_LOG_PATH` there, so every model call's cost row lands on the volume, including runs started from a shell.

**The seed rule.** It runs on every boot and is tracked per file in `/data/.seed-manifest.json`:

| On the volume | Shipped in this image | Result |
| --- | --- | --- |
| missing | present | **copied**. This covers the first boot, and a new event committed later |
| present, unchanged since it was seeded | a different (newer) version | **updated** to the shipped version |
| present, changed in production (a re-run, a new discovery) | anything | **kept**. Work done in production wins |

Nothing on the volume is ever deleted. A file you remove there comes back on the next boot if the image still ships
it.

Unset `DATA_DIR` (the local demo, the tests) and nothing changes: files stay in the checkout exactly as before.

**Filings are not in git.** `cache/fetch` and `cache/pages` start empty. Evidence links still open the original
filing at the right page. For the highlighted page images, re-run an event once in production (see below). It
downloads the filings onto the volume, and every model call replays from `cache/llm` at $0.

---

## Demo users

The API seeds the demo accounts on every start into whichever database it uses. It never overwrites an existing
user, so it is safe to repeat.

| Account | Role | Password |
| --- | --- | --- |
| `admin@finsight.demo` | admin | `demo1234` |
| `rm@finsight.demo` | rm | `demo1234` |
| `viewer@finsight.demo` | viewer | `demo1234` |
| `new.rm@finsight.demo` | rm (sees the first-sign-in guide) | `demo1234` |

To seed by hand:

```bash
railway ssh -- sh -c 'cd /app && python -m api.seed_users'   # prints "Demo users added: N"
```

The login page lists these accounts and the password. That suits a showcase, but anyone with the URL can sign in as
admin. See the [security checklist](#security-checklist).

---

## Running the pipeline and discovery in production

**From the app (admin).** Paste a filing link in chat, or use **Events → process**. The API runs `run.py` as a
subprocess in the same container and writes to the volume. Each run has a cost estimate and a confirm step. An rm
user can confirm up to $0.50 per action, and an admin is unlimited but still confirms.

**From a shell in the running container:**

```bash
railway ssh -- sh -c 'cd /app && python run.py --event events/<id>.json --step all'
railway ssh -- sh -c 'cd /app && python discover.py --since 7d --process 10 --max-cost 1.00'
```

`railway ssh` opens a shell inside the deployed container. Because `/app/outputs`, `/app/events`, `/app/cache` and
`/app/cost_log.csv` are symlinks into `/data`, these commands write to the same volume as the API. The first time,
it asks you to register an SSH key with Railway.

> **Untested here.** Railway's page does not say which working directory or environment an SSH session gets, hence
> the explicit `cd /app`. Check that the session sees the service variables before a run that needs the model:
> `railway ssh -- sh -c 'test -n "$LLM_API_KEY" && echo key present'`. If it does not, prefix the command with the
> variables it needs.

**Scheduled discovery inside the API (signals v2).** While the API runs, `api/scheduler.py` checks every source
every `DISCOVERY_EVERY_HOURS` (default 3) and then processes new events, oldest first, while today's automatic spend
(`cost_log.csv` rows whose run id starts with `auto-`, counted per India day) stays under
`AUTO_PROCESS_DAILY_CAP_USD` (default $1.00). Before each run, that event's estimate (its costliest comparable run
so far) must fit in what is left, so a run is never started that is expected to cross the cap; an event that does not
fit waits as **Needs approval** on the Sources page. Admins can also press **Check for new filings now**: it shows
an estimate first and runs only after Confirm, never spending past the confirmed ceiling. A lock file
(`api/state/scheduler.lock`, released by the operating system when the process exits) lets only one API process on
a machine run the loop, and a second lock keeps a scheduled check and a check-now from overlapping. On Railway this
writes straight to the volume, so it removes the "a cron service cannot see the volume" problem below. **Run one
scheduler, not two:** either keep `DISCOVERY_ENABLED=1` on Railway and disable the GitHub Action, or keep the Action
and set `DISCOVERY_ENABLED=0`. The locks do not reach across machines.

**Scheduled discovery: the GitHub Action (alternative).** `.github/workflows/discover.yml` runs every 3 hours from
08:00 to 20:00 IST. It commits `events/auto`, `outputs`, `cache/llm` and `cost_log.csv` when something changed. With
Railway deploying from that branch, each such commit redeploys the API. The seed rule then brings in the new and
updated files, and leaves anything already changed in production alone.

Remember that a redeploy with a volume has a short downtime. If that matters, point the Action at a branch Railway
does not deploy, or narrow its cron.

**Why not a Railway cron service?** Railway can run a service on a cron schedule (in UTC, at least 5 minutes
apart, and the process must exit when done). But a volume attaches to **one** service only, so a separate cron
service could not write into the API's `/data`. Running discovery there would produce results the API never sees.
If you later want it anyway, the cron service would have to call the running API instead of writing files, and
there is no such endpoint today.

**Exchange sites may refuse cloud servers.** Two shipped events take documents from `nsearchives.nseindia.com`,
and with `EXCHANGE_SOURCES=on` discovery also reads NSE and BSE (an owner's decision, against those sites' terms; see
`decision_log.md` row 15). NSE in particular is likely to refuse requests from data-centre addresses. By design
nothing works around that: no proxies, no IP rotation, no CAPTCHA solving, at least 2 seconds between requests to a
site, and a 401, 403 or 429 stops that source for the run and shows it as **blocked** on the Sources page. In
production either set `EXCHANGE_SOURCES=off`, or leave it on and expect "blocked". If a run fails with `HTTP 403`
for an exchange document link, use the SEBI copy of the same document, or process the event on a laptop and commit
`outputs/<id>` and `cache/llm`. The next deploy seeds them.

---

## Custom domain and cookies

1. **Web.** Add the domain under the Vercel project's **Settings → Domains** and follow its DNS instructions.
2. **Add it to `ALLOWED_ORIGINS`** on Railway, for example
   `https://finsight.example.com,https://finsight.vercel.app`. Deploy the change and wait for the new deployment.
3. **API (optional).** Railway custom domains need the `CNAME` **and** `TXT` records Railway shows, and the
   certificate is automatic. If you do this, set `API_ORIGIN` on Vercel to the new API URL and **redeploy Vercel**.

**Cookie facts.** `finsight_session` is `HttpOnly`, `SameSite=Lax` and `Path=/`, lasts 12 hours, and has **no**
`Domain` attribute. It belongs to the exact host the browser used, so `finsight.vercel.app` and `finsight.example.com`
each need their own sign-in. Behind HTTPS with `COOKIE_SECURE=1` it is also `Secure`. Because `/api` is proxied
through the web domain, the cookie is first-party: no third-party-cookie or CORS settings are involved.

---

## Preview environments

- **Vercel previews** get their own URLs. Every write from a preview URL is refused (403) unless that origin is in
  `ALLOWED_ORIGINS`, and sign-in is itself a write. **A preview outside the list cannot sign in at all.** Add a
  stable preview alias to the list if you want to use previews.
- **Neon branches** are copy-on-write clones of the database, and the Neon-managed Vercel integration can create one
  for each preview deployment. Give a preview API its own branch URL so test sign-ins and notes never touch
  production.
- A full preview stack also needs a second Railway environment with its own volume, because one volume serves one
  service. For a showcase, one production stack is usually enough.

---

## Cost estimate

These are **estimates** from the vendors' published prices on 2026-11-15, for a showcase with light traffic. Check
the current price pages before you rely on them.

| Service | Low-traffic showcase | Notes |
| --- | --- | --- |
| Vercel **Hobby** | **$0** | Free, with monthly included usage (for example 1,000,000 function invocations, 100 GB fast data transfer, 4 active CPU-hours). One function region. Instant Rollback goes only to the previous deployment |
| Vercel **Pro** | **$20 per developer seat per month** + usage | Up to 5 function regions, rollback to any earlier production deployment, longer logs |
| Railway **Hobby** | **$5/month**, which includes $5 of usage | Container rates: RAM $10 per GB-month, CPU $20 per vCPU-month, volume storage $0.15 per GB-month, egress $0.05 per GB. The API container idled at **76 MiB** of RAM and 0.1% CPU locally (`docker stats`, 2026-11-15), which is under $1 of RAM a month. Processing runs use much more while they run (PDF workers; keep `MAX_WORKERS=2`). Expect the **$5** subscription to cover a quiet showcase, and **$5 to $10/month** with some processing |
| Railway **Pro** | **$20/month**, which includes $20 of usage | |
| Neon **Free** | **$0** | 100 CU-hours per project per month, 1 GB storage per project, 10 branches. Scale to zero after 5 minutes, which cannot be turned off |
| Neon **Launch** | usage only | $0.106 per CU-hour, $0.35 per GB-month. No monthly minimum, and invoices under $0.50 are not collected |
| OpenRouter | **$0** for viewing | Reruns of shipped events replay from `cache/llm` at $0. A new event was designed to cost under $2 (see `docs/cost_report.md` for measured costs) |

**A realistic showcase total is about $5 to $10 a month.** That is Vercel Hobby, Railway Hobby, Neon Free, and model
spend only when someone processes a new event.

---

## Security checklist

- [ ] **Rotate the OpenRouter key that shipped in the original zip.** Treat it as public. Create a new key, put it
      only in Railway's `LLM_API_KEY`, and revoke the old one.
- [ ] `SESSION_SECRET` is 32 or more random characters (`openssl rand -hex 32`), set only on Railway, and kept in a
      password manager. `APP_ENV=production` makes the API refuse to start without it.
- [ ] `DATABASE_URL` is set only on Railway. Prefer a dedicated role with only what the app needs (see Step 1). Keep
      the direct URL out of the app.
- [ ] `ALLOWED_ORIGINS` lists only your web origins. Use no wildcards; the check is exact.
- [ ] `COOKIE_SECURE=1`.
- [ ] Mark secrets as secret on each platform. Vercel offers a **Secret** type that cannot be read back after saving.
      Nothing secret goes in `web/`, and `API_ORIGIN` is not a secret.
- [ ] `.env` is never deployed. `.dockerignore` excludes `.env`, `.env.*`, `.venv`, `api/state` and `web/`. The image
      was checked: there is no `.env` inside it.
- [ ] **The demo passwords are public.** They are on the login page. Anyone with the URL can sign in as admin and,
      with `LLM_API_KEY` set, spend model money; every action still needs a confirm and an estimate. For a public
      showcase, either leave `LLM_API_KEY` unset (all viewing and rules-based answers still work), or give the key a
      spending limit if your provider offers one. Real users need a real user list and no demo accounts. That is
      not built.
- [ ] The Railway domain is public too. Every data route still needs a signed session, and `/api/health` reveals
      only `ok` and the database kind.
- [ ] One replica only (see Step 2).
- [ ] **With `RAILWAY_RUN_UID=0` the API process runs as root on Railway.** The image's non-root user (uid 10001)
      applies everywhere else. Railway documents this variable as the fix for volumes owned by root. Accept it, or
      change the entrypoint to fix the volume's ownership and then drop to uid 10001 (not built).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Sign-in or a note fails with **403 "Requests from this site are not allowed"** | The page's origin is not in `ALLOWED_ORIGINS` (a new custom domain, a preview URL, `http` vs `https`, a typo) | Set `ALLOWED_ORIGINS` on Railway to the exact origin the address bar shows, scheme included, and wait for the redeploy |
| **415 "Send JSON"** | A client posted without `Content-Type: application/json` | Send JSON. The web app always does |
| Sign-in succeeds but every page goes back to **/login** | The cookie was not stored or not sent: `COOKIE_SECURE=1` while serving plain `http`, or the browser is on a different host from the one that set the cookie | Use the `https://` Vercel or custom domain. For a plain-http test, set `COOKIE_SECURE=0` |
| All signed-in users are signed out after a deploy | `SESSION_SECRET` changed | Keep it stable. Change it only to force everyone out |
| API deploy fails with **`APP_ENV=production needs SESSION_SECRET`** | The secret is missing or shorter than 32 characters | Set `SESSION_SECRET` (`openssl rand -hex 32`) |
| API exits: **`DATA_DIR=/data is not writable ... RAILWAY_RUN_UID=0`** | The volume is root-owned and the image runs as non-root | Set `RAILWAY_RUN_UID=0` on the service |
| Healthcheck never passes / **"Application failed to respond"** | Wrong target port on the domain, or **Start Command** overridden | Clear the Start Command. Make the domain's port match the `Uvicorn running on ...:<port>` log line. Do not set `PORT` |
| `/api/health` returns **503** with `"error": "OperationalError"` | Neon is unreachable: wrong URL or password, the role was removed, or a typo in `sslmode` / `channel_binding` | Copy the pooled URL again from **Connect**. Test it with `psql "<url>" -c 'select 1'` |
| First request after a quiet spell is slow | Neon scale to zero (Free: after 5 minutes) | Expected. It wakes in a few hundred milliseconds. On paid plans you can turn scale to zero off |
| `prepared statement "_pg3_0" does not exist` (or similar) | Code that skips `api/db.py`'s `connect()` against the pooled URL | Always go through `api/db.py`, which sets `prepare_threshold=None`, or use the direct URL for that tool |
| Events page is empty after deploy | `DATA_DIR` was not set, or the volume is mounted at another path | Set `DATA_DIR` to the volume's mount path (`/data`). The log must show `DATA_DIR /data: seeded {...}` |
| Evidence image says the document is not stored | Filings are not in git (`cache/fetch` is empty) | Re-run the event once in production. Model calls replay at $0 |
| A production run fails with **HTTP 403** on an `nseindia.com` link | The exchange refuses cloud addresses, and the pipeline never retries a 401/403 | Use the SEBI copy of the document, or process locally and commit the outputs (see above) |
| Pages load but every `/api` call is **404** or points at `127.0.0.1` | `API_ORIGIN` was missing when Vercel built the app (the rewrite is fixed at build time) | Set `API_ORIGIN` on Vercel and **redeploy** |
| A live processing view stops after a long time | Railway caps an HTTP request at 15 minutes, even while data flows | The job continues. Reload the page, or read `GET /api/jobs/<id>` |
| A new event committed by the Action does not appear | Railway has not redeployed, or the file was changed in production (production wins) | Check that Railway deploys from the branch the Action pushes to. Look at `/data/.seed-manifest.json` |

---

## Rollback

- **Web (Vercel).** On the project page, open the Production Deployment tile and choose **Instant Rollback**. Hobby
  can roll back to the immediately previous production deployment, and Pro to any earlier one. Environment variables
  are **not** rolled back. After a rollback, new pushes do not go live until you **Manage → promote** a deployment
  (or run `vercel promote <deployment>`).
- **API (Railway).** In **Deployments**, open the **⋯** menu on an earlier deployment and choose **Rollback**. Railway
  restores that deployment's image **and its variables**. Do not count on the volume going back. Railway's rollback
  page does not mention volumes, and the older image's seed rule never overwrites files changed in production. To
  restore files, use a **volume backup**. Backups can be manual (up to 50% of the volume size) or scheduled daily (kept 6 days),
  weekly (27 days) or monthly (89 days). A restore mounts a new volume and redeploys.
- **Database (Neon).** A branch can be reset to its parent. For a point-in-time copy before risky work, create a
  branch first and keep it.

Turn on Railway's scheduled **daily** volume backups in the service's **Backups** tab on day one.

---

## Local check before you deploy

Everything here was run on 2026-11-15:

```bash
.venv/bin/python -m pytest -q                          # 361 passed (19 of them for these settings: tests/test_deploy_env.py)
(cd web && npm run lint && API_ORIGIN=https://api.example.test npm run build)
docker build -t finsight-api .
mkdir -p /tmp/finsight-data
CID=$(docker run -d -p 127.0.0.1:8130:8000 -e APP_ENV=production -e SESSION_SECRET=$(openssl rand -hex 32) \
  -e DATA_DIR=/data -v /tmp/finsight-data:/data finsight-api)
sleep 5; curl -s http://127.0.0.1:8130/api/health       # {"ok": true, "db": "sqlite"}
docker logs "$CID" | grep DATA_DIR                      # DATA_DIR /data: seeded {...}
docker stop "$CID" && docker rm "$CID"
```

The image was checked to:

- run as uid 10001;
- contain no `.env`;
- import `run`, `discover` and `api.main`;
- seed 154 output files, 20 event files and 696 cache files into an empty volume, then 0 files on a second boot;
- exit with a clear message when `APP_ENV=production` has no `SESSION_SECRET`.

The local demo is unchanged. `./demo.sh start` still runs the API on `127.0.0.1:8000` and the web app on `:3000`, with
SQLite and no new variables.

---

## Appendix: sources

All of these were read on **2026-11-15**. Where a page showed a "last updated" date, it is given.

**Neon**

- Regions: `aws-ap-southeast-1` = AWS Asia Pacific (Singapore), and the region cannot be changed later.
  <https://neon.com/docs/introduction/regions>
- Creating a project: the region is chosen at creation; defaults are branch `production` (Console) / `main` (API or
  CLI), database `neondb` and role `neondb_owner`. <https://neon.com/docs/manage/projects>
- Connection strings: the `-pooler` host, `sslmode=require&channel_binding=require`, and the Connect modal pooling
  toggle. <https://neon.com/docs/connect/connect-from-any-app>
- Pooling: PgBouncer `pool_mode=transaction`, `max_client_conn=10000`, the unsupported features, and when to use
  the direct URL. <https://neon.com/docs/connect/connection-pooling>
- Scale to zero: 5 minutes, wakes "within a few hundred milliseconds", cannot be turned off on Free.
  <https://neon.com/docs/introduction/scale-to-zero>
- Branching: copy-on-write branches, a branch per preview through the Vercel integration, reset from parent.
  <https://neon.com/docs/introduction/branching>
- Roles: Console roles get `neon_superuser`, and SQL `CREATE ROLE` gets basic privileges only.
  <https://neon.com/docs/manage/roles>
- Plans: Free limits and Launch prices (page updated 2026-11-12). <https://neon.com/docs/introduction/plans>

**psycopg 3**

- `prepare_threshold=None` disables prepared statements, which is advised behind poolers.
  <https://www.psycopg.org/psycopg3/docs/advanced/prepare.html>

**Railway**

- Regions: `asia-southeast1-eqsg3a` = Southeast Asia Metal, Singapore. <https://docs.railway.com/reference/deployment-regions>
- Volumes:
  - one per service;
  - sizes 0.5 GB / 5 GB / 50 GB;
  - `RAILWAY_RUN_UID=0` for non-root images;
  - redeploy downtime.

  <https://docs.railway.com/reference/volumes>
- Volumes guide: created from `⌘K` or the canvas; mounted at start, not at build or pre-deploy.
  <https://docs.railway.com/volumes>
- Volume backups: manual up to 50%; daily, weekly and monthly retention; how restore works.
  <https://docs.railway.com/volumes/backups>
- Config as Code is deprecated: new services cannot opt in, and the cutoff is 2026-12-01.
  <https://docs.railway.com/infrastructure-as-code> and <https://docs.railway.com/reference/config-as-code>
- Infrastructure as Code DSL (no documented Dockerfile path or cron field).
  <https://docs.railway.com/infrastructure-as-code/reference>
- Dockerfiles: a root `Dockerfile` is auto-detected, and `RAILWAY_DOCKERFILE_PATH` sets another path.
  <https://docs.railway.com/guides/dockerfiles>
- Monorepos: Root Directory pulls only that folder, and the config file does not follow it.
  <https://docs.railway.com/guides/monorepo>
- Healthchecks: a 300 s default, used at deploy only, uses `PORT`, comes from `healthcheck.railway.app`.
  <https://docs.railway.com/reference/healthchecks>
- PORT is injected; bind to `0.0.0.0` (uvicorn needs `--host 0.0.0.0 --port $PORT`); `::` is recommended for
  private networking. <https://docs.railway.com/networking/troubleshooting/application-failed-to-respond> and
  <https://docs.railway.com/private-networking>
- Private networking: `SERVICE_NAME.railway.internal`. <https://docs.railway.com/reference/private-networking>
- Public networking: Generate Domain, custom domains need `CNAME` + `TXT`, automatic TLS.
  <https://docs.railway.com/reference/public-networking>
- Limits: 15-minute HTTP requests while data flows, 5 minutes idle.
  <https://docs.railway.com/networking/public-networking/specs-and-limits>
- Variables: `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_VOLUME_MOUNT_PATH`, `${{shared.VAR}}` references.
  <https://docs.railway.com/reference/variables>
- Cron jobs: UTC, at least 5 minutes apart, must exit, overlapping runs skipped.
  <https://docs.railway.com/reference/cron-jobs>
- `railway ssh`: a shell in the deployed container, `railway ssh -- <command>`. <https://docs.railway.com/cli/ssh>
- Deployment actions: Rollback restores the image and variables. <https://docs.railway.com/deployments/deployment-actions>
- Pricing: plans and container rates. <https://docs.railway.com/reference/pricing/plans>

**Vercel**

- Monorepos: Root Directory at import (page updated 2026-08-11). <https://vercel.com/docs/monorepos>
- Function region: default `iad1`, `"regions"` in `vercel.json`, Hobby gets a single region, Routing Middleware runs
  in all regions (page updated 2026-08-11). <https://vercel.com/docs/functions/configuring-functions/region>
- Region list: `sin1` = ap-southeast-1, Singapore (page updated 2026-08-11). <https://vercel.com/docs/regions>
- Rewrites to external origins: visitor headers forwarded, `Cache-Control` honoured by default for projects created
  on or after 2026-04-06, `x-vercel-enable-rewrite-caching: 0` to opt out (page updated 2026-08-11).
  <https://vercel.com/docs/rewrites>
- CDN origin timeout of 120 s to first byte, then data at least every 120 s (changelog, 2025-05-08).
  <https://vercel.com/changelog/cdn-origin-timeout-increased-to-two-minutes>
- Next.js `rewrites` to an external URL, and the routing order (page updated 2026-09-28).
  <https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites>
- Next.js on Vercel (page updated 2026-11-14). <https://vercel.com/docs/frameworks/full-stack/nextjs>
- Environment variables: Production / Preview / Development, changes apply to new deployments only, Config vs Secret
  types (page updated 2026-09-17). <https://vercel.com/docs/environment-variables>
- Node.js versions: 26.x default, 24.x and 22.x (page updated 2026-02-27).
  <https://vercel.com/docs/functions/runtimes/node-js/node-js-versions>
- Hobby plan: free, included usage, comparison with Pro, $20 per developer seat (page updated 2026-11-12).
  <https://vercel.com/docs/plans/hobby>
- Instant Rollback: Hobby gets the previous deployment only, env vars are not rolled back, undo by promoting (page
  updated 2026-07-07). <https://vercel.com/docs/instant-rollback>
