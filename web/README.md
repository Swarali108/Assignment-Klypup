# FinSight web

Next.js (App Router) UI for the RM call list. Reads the local API at `NEXT_PUBLIC_API_URL`
(default `http://localhost:8000/api`).

```bash
npm install
npm run dev -- -p 3000     # http://localhost:3000, component gallery at /dev/gallery
npm run build && npm run lint
node --experimental-strip-types scripts/check-format.mjs   # ₹ / date formatting checks
```

Design rules and tokens: `DESIGN.md`. Design-system components: `components/ds` (import from `@/components/ds`).
Gallery fixtures are regenerated from real outputs with `../.venv/bin/python scripts/make_fixtures.py`
(run from the repo root as `.venv/bin/python web/scripts/make_fixtures.py`).
