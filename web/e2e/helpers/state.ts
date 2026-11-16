import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/** The app's SQLite file (local demo mode). E2E_DB overrides; null when it cannot be found. */
export function appDb(): string | null {
  const candidates = [process.env.E2E_DB, path.resolve(__dirname, "..", "..", "..", "api", "state", "app.sqlite")].filter(Boolean) as string[];
  return candidates.find((p) => fs.existsSync(p)) ?? null;
}

/** Run one SQL statement with the sqlite3 CLI; returns stdout, or null when the CLI/DB/table is unavailable. */
export function sql(statement: string, mode: "read" | "write" = "read"): string | null {
  const db = appDb();
  if (!db) return null;
  const r = spawnSync("sqlite3", mode === "read" ? ["-readonly", "-separator", "|", db, statement] : [db, statement], { encoding: "utf8", timeout: 15_000 });
  return r.status === 0 ? r.stdout : null;
}

export function todayIst(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

type Row = Record<string, string | number | null>;

/** Every row of a table (sqlite3 -json), or null when the DB/table is not there. */
export function tableRows(table: string): Row[] | null {
  const db = appDb();
  if (!db) return null;
  const r = spawnSync("sqlite3", ["-readonly", "-json", db, `SELECT * FROM ${table}`], { encoding: "utf8", timeout: 15_000 });
  if (r.status !== 0) return null;
  return r.stdout.trim() ? (JSON.parse(r.stdout) as Row[]) : [];
}

const lit = (v: string | number | null | undefined) => (v === null || v === undefined ? "NULL" : typeof v === "number" ? String(v) : `'${String(v).replace(/'/g, "''")}'`);

/**
 * Puts a table's rows back the way `before` had them, touching only rows that were added or changed since
 * (matched on the key columns). Returns what it did, for the teardown log.
 */
export function restoreTable(table: string, keys: string[], before: Row[]): string[] {
  const now = tableRows(table);
  if (now === null) return [];
  const id = (r: Row) => keys.map((k) => String(r[k])).join("|");
  const was = new Map(before.map((r) => [id(r), r]));
  const done: string[] = [];
  for (const r of now) {
    const old = was.get(id(r));
    if (old && JSON.stringify(old) === JSON.stringify(r)) continue;
    const where = keys.map((k) => `${k} = ${lit(r[k])}`).join(" AND ");
    sql(`DELETE FROM ${table} WHERE ${where}`, "write");
    if (old) {
      const cols = Object.keys(old);
      sql(`INSERT INTO ${table} (${cols.join(", ")}) VALUES (${cols.map((c) => lit(old[c])).join(", ")})`, "write");
    }
    done.push(`${table}:${id(r)} ${old ? "restored" : "removed"}`);
  }
  return done;
}
