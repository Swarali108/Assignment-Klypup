import type { APIRequestContext } from "@playwright/test";
import { ACCOUNTS, authFile, type Role } from "./helpers/accounts";
import { test, expect } from "./fixtures";

type Perm = "view" | "edit_rm" | "export" | "ask" | "team" | "review" | "process" | "ops";
type Call = { perm: Perm; method: "GET" | "POST" | "PUT" | "DELETE"; url: string; body?: unknown };

const P = "sedemac_ipo/p_manish_sharma";
/** Every guarded route, by the permission its guard asks for (api/auth.py PERMISSIONS; api/main.py and the routers). */
const CALLS: Call[] = [
  { perm: "edit_rm", method: "PUT", url: `/api/rm/${P}`, body: { status: "to_call" } },
  { perm: "edit_rm", method: "GET", url: "/api/team/rms" },
  { perm: "edit_rm", method: "POST", url: `/api/people/${P}/enrichment`, body: { kinds: ["web"], confirmed_requests: 0 } },
  { perm: "export", method: "GET", url: "/api/export/calls.csv" },
  { perm: "ask", method: "POST", url: "/api/ask", body: { question: "who is on the list" } },
  { perm: "ask", method: "POST", url: "/api/chat/compare", body: { question: "hi", models: ["openai/gpt-6-luna", "qwen/qwen3.8-flash"] } },
  { perm: "team", method: "GET", url: "/api/team" },
  { perm: "team", method: "PUT", url: `/api/assignments/${P}`, body: { rm_email: null } },
  { perm: "review", method: "GET", url: "/api/review" },
  { perm: "review", method: "POST", url: "/api/review/decide", body: { id: "holder|none|none", action: "confirm" } },
  { perm: "review", method: "DELETE", url: "/api/review?id=holder%7Cnone%7Cnone" },
  { perm: "process", method: "POST", url: "/api/events/from-links", body: { urls: [] } },
  { perm: "process", method: "POST", url: "/api/events", body: {} },
  { perm: "process", method: "POST", url: "/api/events/vectras_ipo/run" },
  { perm: "process", method: "POST", url: "/api/discovery/check-now", body: {} }, // without a token this only estimates
  { perm: "ops", method: "GET", url: "/api/ops" },
  { perm: "ops", method: "GET", url: "/api/ops/tokens" },
  { perm: "ops", method: "GET", url: "/api/ops/health" },
  { perm: "ops", method: "GET", url: "/api/ops/accuracy" },
  { perm: "ops", method: "POST", url: "/api/ops/accuracy/run", body: {} },
  { perm: "ops", method: "GET", url: "/api/admin/events" },
  { perm: "ops", method: "GET", url: "/api/admin/jobs" },
  { perm: "ops", method: "GET", url: "/api/admin/events/vectras_ipo/history" },
  { perm: "ops", method: "GET", url: "/api/admin/events/vectras_ipo/diff" },
  { perm: "ops", method: "POST", url: "/api/admin/run", body: { event_id: "vectras_ipo", step: "rank" } },
  { perm: "ops", method: "GET", url: "/api/sources" },
  { perm: "ops", method: "GET", url: "/api/discovery/auto-log" },
];

/** Reads open to every signed-in role (the "view" permission). */
const VIEW_READS = ["/api/today", "/api/summary", "/api/events", "/api/calendar", "/api/network", "/api/feed", "/api/chat/models", "/api/chat/conversations", "/api/watch", "/api/alerts", "/api/me/preferences", "/api/assignments", "/api/enrichment/status", `/api/people/${P}`, `/api/people/${P}/trail`, `/api/rm/${P}`];

const HAS: Record<Role, Perm[]> = {
  admin: ["view", "edit_rm", "export", "ask", "team", "review", "process", "ops"],
  head: ["view", "edit_rm", "export", "ask", "team", "review"],
  rm: ["view", "edit_rm", "export", "ask"],
  viewer: ["view"],
  newrm: ["view", "edit_rm", "export", "ask"],
};

async function call(api: APIRequestContext, c: Call) {
  if (c.method === "GET") return api.get(c.url);
  return api.fetch(c.url, { method: c.method, data: c.body ?? {}, headers: { "content-type": "application/json" } });
}

test.describe("API permission matrix", () => {
  test("anonymous: 401 on every guarded route, reads and writes", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL });
    for (const c of CALLS) expect((await call(api, c)).status(), `${c.method} ${c.url}`).toBe(401);
    for (const url of VIEW_READS) expect((await api.get(url)).status(), `GET ${url}`).toBe(401);
    await api.dispose();
  });

  for (const role of ["viewer", "rm", "head"] as Role[]) {
    test(`${role}: 403 on every route whose permission it lacks, 200 on the reads it has`, async ({ playwright, baseURL }) => {
      const api = await playwright.request.newContext({ baseURL, storageState: authFile(role) });
      const refused: string[] = [];
      for (const c of CALLS) {
        const res = await call(api, c);
        if (HAS[role].includes(c.perm)) {
          // allowed role: only the harmless reads are called (a write here would change real data)
          if (c.method === "GET") expect(res.status(), `${role} ${c.method} ${c.url}`).toBe(200);
        } else {
          expect(res.status(), `${role} ${c.method} ${c.url} (needs ${c.perm})`).toBe(403);
          refused.push(`${c.method} ${c.url}`);
        }
      }
      for (const url of VIEW_READS) expect((await api.get(url)).status(), `${role} GET ${url}`).toBe(200);
      expect(refused.length).toBe(CALLS.filter((c) => !HAS[role].includes(c.perm)).length);
      await api.dispose();
    });
  }

  test("viewer: 403 on every write and spend endpoint, by name", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL, storageState: authFile("viewer") });
    const spend = CALLS.filter((c) => c.method !== "GET" || ["export", "ops", "team", "review"].includes(c.perm));
    expect(spend.length).toBeGreaterThan(15);
    for (const c of spend) expect((await call(api, c)).status(), `${c.method} ${c.url}`).toBe(403);
    await api.dispose();
  });

  test("rm: 403 on every admin endpoint (ops, process, team, review)", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL, storageState: authFile("rm") });
    for (const c of CALLS.filter((c) => ["ops", "process", "team", "review"].includes(c.perm))) {
      expect((await call(api, c)).status(), `${c.method} ${c.url}`).toBe(403);
    }
    await api.dispose();
  });

  test("admin can read every ops page's data", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL, storageState: authFile("admin") });
    for (const c of CALLS.filter((c) => c.method === "GET")) expect((await call(api, c)).status(), `${c.method} ${c.url}`).toBe(200);
    await api.dispose();
  });

  test("the chat itself is open to a viewer for free questions but never spends", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL, storageState: authFile("viewer") });
    const res = await api.post("/api/chat", { data: { conversation_id: null, message: "Process Vectras IPO again" } });
    expect(res.status()).toBe(200);
    const text = await res.text();
    expect(text).toContain("event: estimate");
    const est = JSON.parse(/event: estimate\ndata: (.*)/.exec(text)![1]);
    expect(est.can_confirm).toBe(false);
    expect(est.confirm_token || null).toBeNull();
    const id = JSON.parse(/event: meta\ndata: (.*)/.exec(text)![1]).conversation_id;
    await api.delete(`/api/chat/conversations/${id}`, { data: {} });
    await api.dispose();
  });
});

test.describe("write protection (CSRF)", () => {
  test("a write that is not JSON is refused before any session check", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL, storageState: authFile("admin") });
    const res = await api.fetch(`/api/rm/${P}`, { method: "PUT", data: "status=called", headers: { "content-type": "text/plain" } });
    expect(res.status()).toBe(415);
    await api.dispose();
  });

  test("a write from another site's origin is refused", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL, storageState: authFile("admin") });
    const res = await api.fetch(`/api/rm/${P}`, { method: "PUT", data: { status: "called" }, headers: { origin: "https://evil.example", "content-type": "application/json" } });
    expect(res.status()).toBe(403);
    expect((await (await api.get(`/api/rm/${P}`)).json()).status).toBe("to_call");
    await api.dispose();
  });

  test("a forged or expired session cookie is treated as signed out", async ({ playwright, baseURL }) => {
    const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { cookie: "aurelia_session=eyJmb3JnZWQiOjF9.AAAA" } });
    expect((await api.get("/api/today")).status()).toBe(401);
    await api.dispose();
  });
});

test("every account signs in with the shared demo password", async ({ playwright, baseURL }) => {
  for (const role of Object.keys(ACCOUNTS) as Role[]) {
    const api = await playwright.request.newContext({ baseURL });
    const res = await api.post("/api/auth/login", { data: { email: ACCOUNTS[role].email, password: "demo1234" } });
    expect(res.status(), role).toBe(200);
    await api.dispose();
  }
});
