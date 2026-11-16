import fs from "node:fs";
import { request, type FullConfig } from "@playwright/test";
import { ACCOUNTS, AUTH_DIR, PASSWORD, ROLES, SNAPSHOT_FILE, authFile } from "./helpers/accounts";
import { sql, tableRows, todayIst } from "./helpers/state";

/**
 * Signs every demo role in over the API (one storageState per role) and records what the suite could change, so
 * global-teardown can put it back: conversations, followed names, preferences + client book, review decisions,
 * call statuses / assignments and the daily-brief "shown" flags.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL ?? "http://localhost:3000";
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const snapshot: Record<string, unknown> = { at: new Date().toISOString(), roles: {} as Record<string, unknown> };
  const roles = snapshot.roles as Record<string, unknown>;

  for (const role of ROLES) {
    const ctx = await request.newContext({ baseURL });
    const res = await ctx.post("/api/auth/login", { data: { email: ACCOUNTS[role].email, password: PASSWORD } });
    if (!res.ok()) throw new Error(`Could not sign in ${role} (${res.status()}). Is the app running at ${baseURL}? Start it with ./demo.sh start`);
    await ctx.storageState({ path: authFile(role) });

    const json = async (url: string) => {
      const r = await ctx.get(url);
      return r.ok() ? await r.json() : null;
    };
    roles[role] = {
      conversations: ((await json("/api/chat/conversations")) ?? []).map((c: { id: string }) => c.id),
      watch: await json("/api/watch"),
      prefs: await json("/api/me/preferences"),
      review: role === "admin" || role === "head" ? await json("/api/review") : null,
    };
    await ctx.dispose();
  }

  // Daily-brief flags (the table exists once the brief feature is deployed).
  const rows = sql(`SELECT email, day, shown FROM user_brief WHERE day = '${todayIst()}'`);
  snapshot.brief = rows === null ? null : rows.split("\n").filter(Boolean).map((l) => l.split("|"));
  snapshot.tables = { rm_state: tableRows("rm_state"), assignments: tableRows("assignments") };
  fs.writeFileSync(SNAPSHOT_FILE, JSON.stringify(snapshot, null, 2));
}
