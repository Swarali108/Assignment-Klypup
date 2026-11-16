import fs from "node:fs";
import { request, type FullConfig } from "@playwright/test";
import { ACCOUNTS, PASSWORD, ROLES, SNAPSHOT_FILE } from "./helpers/accounts";
import { restoreTable, sql, todayIst } from "./helpers/state";

type Row = Record<string, string | number | null>;
type Snap = {
  roles: Record<
    string,
    {
      conversations: string[];
      watch: { follows?: { kind: string; key: string }[] } | null;
      prefs: Record<string, unknown> | null;
      review: { items?: { id: string; decision: unknown }[] } | null;
    }
  >;
  brief: string[][] | null;
  tables: { rm_state: Row[] | null; assignments: Row[] | null };
};

/**
 * Puts the demo data back as globalSetup found it: deletes the conversations the run created, unfollows what it
 * followed, undoes review decisions left behind, restores preferences and the client book (new.rm@ gets its setup
 * guide back), restores call statuses / assignments exactly, and resets the daily-brief flags (new.rm@ sees the
 * brief again on its next sign-in).
 */
export default async function globalTeardown(config: FullConfig) {
  if (!fs.existsSync(SNAPSHOT_FILE)) return;
  const snap = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, "utf8")) as Snap;
  const baseURL = config.projects[0].use.baseURL ?? "http://localhost:3000";
  const notes: string[] = [];

  for (const role of ROLES) {
    const before = snap.roles[role];
    if (!before) continue;
    const ctx = await request.newContext({ baseURL });
    const login = await ctx.post("/api/auth/login", { data: { email: ACCOUNTS[role].email, password: PASSWORD } });
    if (!login.ok()) {
      notes.push(`${role}: could not sign in to clean up`);
      continue;
    }
    // conversations created during the run
    const now = (await (await ctx.get("/api/chat/conversations")).json()) as { id: string }[];
    for (const c of now.filter((c) => !before.conversations.includes(c.id))) await ctx.delete(`/api/chat/conversations/${c.id}`, { data: {} });
    // followed names
    const w = await ctx.get("/api/watch");
    if (w.ok() && before.watch) {
      const key = (i: { kind: string; key: string }) => `${i.kind}|${i.key}`;
      const had = new Set((before.watch.follows ?? []).map(key));
      const nowItems = ((await w.json()) as { follows?: { kind: string; key: string }[] }).follows ?? [];
      for (const i of nowItems.filter((i) => !had.has(key(i)))) {
        await ctx.delete(`/api/watch?kind=${encodeURIComponent(i.kind)}&key=${encodeURIComponent(i.key)}`, { data: {} });
      }
    }
    // review decisions that a test left behind
    if (before.review) {
      const decided = new Set((before.review.items ?? []).filter((i) => i.decision).map((i) => i.id));
      const r = await ctx.get("/api/review");
      if (r.ok()) {
        for (const i of ((await r.json()) as { items: { id: string; decision: unknown }[] }).items.filter((i) => i.decision && !decided.has(i.id))) {
          await ctx.delete(`/api/review?id=${encodeURIComponent(i.id)}`, { data: {} });
          notes.push(`undid a leftover review decision ${i.id}`);
        }
      }
    }
    // preferences and client book (new.rm@ goes back to "never signed in")
    if (before.prefs) {
      const { book_count, ...prefs } = before.prefs as Record<string, unknown> & { book_count?: number };
      await ctx.put("/api/me/preferences", { data: prefs });
      const cur = (await (await ctx.get("/api/me/preferences")).json()) as { book_count: number };
      if (cur.book_count !== (book_count ?? 0)) {
        if (!book_count) await ctx.delete("/api/me/book", { data: {} });
        else notes.push(`${role}: client book size differs from before (${cur.book_count} vs ${book_count})`);
      }
    }
    await ctx.dispose();
  }

  // The brief "shown" flag: restore what it was; new.rm@ always goes back to "not shown yet today".
  if (snap.brief !== null) {
    const day = todayIst();
    const was = new Map(snap.brief.map(([email, , shown]) => [email, shown]));
    for (const role of ROLES) {
      const email = ACCOUNTS[role].email;
      if (role !== "newrm" && was.has(email)) sql(`UPDATE user_brief SET shown = ${was.get(email)} WHERE email = '${email}' AND day = '${day}'`, "write");
      else sql(`DELETE FROM user_brief WHERE email = '${email}' AND day = '${day}'`, "write");
    }
  }
  // new.rm@ is "never signed in": drop its last-visit row too, or the first real sign-in would show a since-last-visit comparison.
  sql(`DELETE FROM user_seen WHERE email = '${ACCOUNTS.newrm.email}'`, "write");
  // Call statuses, notes and RM assignments changed through the UI (rows restored exactly, first-call stamp included).
  if (snap.tables?.rm_state) notes.push(...restoreTable("rm_state", ["event_id", "person_id"], snap.tables.rm_state));
  if (snap.tables?.assignments) notes.push(...restoreTable("assignments", ["event_id", "person_id"], snap.tables.assignments));
  if (notes.length) console.warn(`[e2e teardown] ${notes.join("; ")}`);
}
