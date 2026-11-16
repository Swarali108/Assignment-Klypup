"use client";

/** Types and fetchers for the admin pages: pipeline console, system health, accuracy (api/CONTRACT.md "Admin"). */
import { apiFetch } from "@/lib/api";

export interface AdminEvent {
  event_id: string;
  company: string;
  event_type: string;
  type_label: string;
  supported: boolean;
  processed: boolean;
  people_count: number;
  running: boolean;
  last_run: { run_id: string; ended_at: string; status: string; total_cost_usd: string } | null;
}

export interface StepChoice {
  step: string;
  label: string;
}

export interface RunEstimate {
  low: number;
  high: number;
  seconds_low: number;
  seconds_high: number;
  breakdown: { step: string; model: string | null; calls: number; cost_usd_low: number; cost_usd_high: number }[];
  basis: string;
}

export type RunResponse =
  | { needs_confirm: true; estimate: RunEstimate; confirm_token: string; expires_at: number; message: string }
  | { needs_confirm: false; job_id: string; event_id: string; state: string; step: string; fresh: boolean; stream_url: string; log_url: string };

export interface RunRow {
  run_id: string;
  started_at: string;
  ended_at: string;
  wall_s: number | null;
  calls: number;
  cached_calls: number;
  cost_usd: number;
  status: string;
  error: string | null;
  snapshot: boolean;
}

export interface DiffPerson {
  person_id: string;
  name: string | null;
  group?: string;
  tier?: string | null;
  amount?: string | null;
}

export interface RunDiff {
  event_id: string;
  runs_with_snapshot: string[];
  older: string | null;
  newer: string | null;
  available: boolean;
  added: DiffPerson[];
  removed: DiffPerson[];
  changed: { person_id: string; name: string | null; changes: { field: string; before: string | number | null; after: string | number | null }[] }[];
  unchanged: number;
}

export interface Health {
  checked_at: string;
  stale_after_days: number;
  running: string[];
  scheduler: { available: boolean; reason?: string; error?: string; [k: string]: unknown };
  sources: { refreshed_at: string | null; sources: { id: string; name: string; status: string; items: number | null; reason: string | null; url: string }[] };
  caches: { key: string; label: string; files: number; bytes: number }[];
  spend: {
    date: string;
    today: SpendFigures;
    all_time: SpendFigures;
    daily_cap_usd: number | null;
    daily_cap_used: number | null;
    event_budget_usd: number;
    budget_mode: string;
    provider_cache: { hit_rate: number | null };
  };
  brightdata: { available: boolean; reason?: string; error?: string; requests?: number | null; cap: number | null; used_share?: number | null };
  failed_runs: { event_id: string; company: string; run_id: string; at: string; reason: string; running: boolean }[];
}

export interface SpendFigures {
  calls: number;
  cached_calls: number;
  paid_calls: number;
  cost_usd: number;
  cache_hit_rate: number | null;
}

export interface AccuracyResult {
  ran_at: string;
  overall: { people: number; fully_right: number; value_fields: number; hits: number; wrong: number; missing: number; invented: number; hit_rate: number | null };
  fields: { field: string; label: string; value_fields: number; hit: number; wrong: number; missing: number; blank_ok: number; invented: number; hit_rate: number | null }[];
  events: { event_id: string; people: number; value_fields: number; hits: number; hit_rate: number | null }[];
  events_missing: string[];
  misses: {
    person_id: string;
    event_id: string;
    name: string;
    field: string;
    label: string;
    outcome: "wrong" | "missing" | "invented";
    gold: string | number | null;
    pipeline: string | number | null;
    pages: { label: string; url: string; cached: boolean; quote: string | null }[];
  }[];
}

export const adminApi = {
  events: () => apiFetch<{ count: number; events: AdminEvent[]; steps: StepChoice[] }>("/admin/events"),
  run: (body: { event_id: string; step: string; person_id?: string | null; fresh: boolean; confirm_token?: string }) =>
    apiFetch<RunResponse>("/admin/run", { method: "POST", body: JSON.stringify(body) }),
  history: (eventId: string) =>
    apiFetch<{ event_id: string; runs: RunRow[]; diff: RunDiff }>(`/admin/events/${encodeURIComponent(eventId)}/history`),
  diff: (eventId: string, older: string, newer: string) =>
    apiFetch<RunDiff>(`/admin/events/${encodeURIComponent(eventId)}/diff`, { query: { older, newer } }),
  callable: (eventId: string) =>
    apiFetch<{ callable: { person: { id: string; name: string } }[] }>(`/events/${encodeURIComponent(eventId)}/people`),
  health: () => apiFetch<Health>("/ops/health"),
  accuracy: () => apiFetch<{ result: AccuracyResult | null }>("/ops/accuracy"),
  runAccuracy: () => apiFetch<{ result: AccuracyResult }>("/ops/accuracy/run", { method: "POST" }),
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-15T10:20:26Z" -> "15 Nov, 15:50 IST" (fixed +05:30, no locale or clock involved). */
export function istStamp(iso: string | null | undefined): string {
  if (!iso) return "–";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "–";
  const d = new Date(t + 330 * 60_000);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} IST`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export const pct = (n: number | null | undefined, digits = 0) => (n === null || n === undefined ? "–" : `${(n * 100).toFixed(digits)}%`);
