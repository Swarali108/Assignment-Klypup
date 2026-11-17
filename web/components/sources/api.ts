/** Fetchers and shapes for the Sources page, "Check for new filings now" and the auto-processing log (admin only). */
import { apiFetch } from "@/lib/api";

export type SourceState = "on" | "off" | "blocked" | "failed" | "not checked";

export interface SourceRow {
  id: string;
  name: string;
  owner: "SEBI" | "NSE" | "BSE" | "Other";
  url: string;
  what: string;
  terms_url: string;
  state: SourceState;
  reason: string;
  risk: { level: "low" | "high" | "unknown" | string; label: string };
  last_checked: string | null;
  items: number;
  records?: number | null;
  errors: string[];
  error_count: number;
}

export interface SourcesResponse {
  refreshed_at: string | null;
  switch: { name: string; value: "on" | "off"; reader: "installed" | "missing" };
  sources: SourceRow[];
}

export interface EstimateStep {
  step: string;
  model: string | null;
  cost_usd_low: number;
  cost_usd_high: number;
}

export interface EstimateEvent {
  event_id: string;
  company: string | null;
  event_type: string;
  low: number;
  high: number;
  fits: boolean;
  status: string;
}

export interface CheckEstimate {
  today: string;
  timezone: string;
  spent_today_usd: number;
  cap_usd: number;
  remaining_usd: number;
  ceiling_usd: number;
  steps: EstimateStep[];
  events: EstimateEvent[];
  low: number;
  high: number;
  basis: string;
  last_checked: string | null;
}

export interface EstimateReply {
  state: "estimate";
  estimate: CheckEstimate;
  token: string;
  expires_at: string;
  ttl_s: number;
}

export interface StartReply {
  state: "running";
  job_id: string;
  ceiling_usd: number;
  stream_url: string;
}

/** One progress event of a check (server-sent). */
export interface CheckEvent {
  stage: "start" | "source" | "classify" | "events" | "process" | "finish";
  at?: number;
  // source
  source?: string;
  name?: string;
  status?: string;
  items?: number;
  reason?: string;
  // process
  state?: "start" | "done";
  event_id?: string;
  company?: string | null;
  cost_usd?: number | null;
  estimate_usd?: number | null;
  seconds?: number | null;
  // events / finish
  events?: number;
  new?: number;
  skipped?: number;
  error?: string | null;
  spent_usd?: number;
  spent_today_usd?: number;
  cap_usd?: number;
  ceiling_usd?: number | null;
  processed?: number;
  needs_approval?: number;
  events_new?: number;
  trigger?: string;
}

export interface ProcessedEntry {
  event_id: string;
  company?: string | null;
  status: "ok" | "failed" | "waiting" | "skipped" | "needs_approval" | string;
  reason?: string | null;
  cost_usd?: number | null;
  estimate_usd?: number | null;
  seconds?: number | null;
  run_id?: string | null;
  at?: string | null;
}

export interface Cycle {
  id: string;
  trigger: "schedule" | "check-now" | string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "done" | "failed";
  cap_usd: number;
  ceiling_usd: number | null;
  day: string;
  spent_usd: number;
  spent_today_usd?: number;
  sources: { id: string; name: string | null; status: string; items: number; reason: string }[];
  events_found: number;
  events_new: number;
  processed: ProcessedEntry[];
  error: string | null;
}

export interface AutoLog {
  today: { day: string; timezone: string; spent_usd: number; cap_usd: number; remaining_usd: number; runs: number };
  scheduler: { state: string; enabled: boolean; every_hours: number; next_run_at: string | null; last_run_at: string | null };
  needs_approval: { event_id: string; company: string | null; reason: string | null; estimate_usd: number | null; at: string | null }[];
  runs_today: ProcessedEntry[];
  cycles: Cycle[];
}

/** Fired on window when a check finishes, so the auto-spend chip refetches. */
export const CHECK_FINISHED = "finsight:check-finished";

export const sourcesApi = {
  sources: () => apiFetch<SourcesResponse>("/sources"),
  autoLog: () => apiFetch<AutoLog>("/discovery/auto-log"),
  estimate: () => apiFetch<EstimateReply>("/discovery/check-now", { method: "POST", body: JSON.stringify({}) }),
  confirm: (token: string) => apiFetch<StartReply>("/discovery/check-now", { method: "POST", body: JSON.stringify({ confirm: token }) }),
  job: (jobId: string) => apiFetch<{ job_id: string; state: string; events: CheckEvent[] }>(`/discovery/jobs/${encodeURIComponent(jobId)}`),
};

/** Dollars precise enough for tiny model costs: $0.0021, $0.012, $1.00. */
export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  if (n === 0) return "$0.00";
  if (Math.abs(n) < 0.01) return `$${n.toFixed(4)}`;
  if (Math.abs(n) < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-15T10:20:26+00:00" → "15 Nov, 15:50 IST" (fixed +05:30; no locale or clock involved). */
export function istStamp(iso: string | null | undefined): string {
  if (!iso) return "never";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "–";
  const d = new Date(t + 330 * 60_000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${hh}:${mm} IST`;
}

const KIND_WORD: Record<string, string> = {
  bulk_deal: "Bulk deal",
  block_deal: "Block deal",
  insider_sale: "Insider sale",
  buyback: "Buyback",
  ipo: "IPO",
  ofs: "Offer for sale",
};

/**
 * The type and week (or month) an event id already carries, so rows for the same company can be told apart:
 * "gallantt_ispat_bulk_deal_2026w44" → "Bulk deal · week 44"; "dcw_limited_buyback_202610" → "Buyback · Oct 2026".
 * Empty when the id does not follow that shape (nothing is invented).
 */
export function eventKindAndPeriod(eventId: string): string {
  const m = /^(?:.*_)?(bulk_deal|block_deal|insider_sale|buyback|ipo|ofs)(?:_(?:\d{4}w(\d{1,2})|(\d{4})(\d{2})))?$/.exec(eventId);
  if (!m) return "";
  const kind = KIND_WORD[m[1]];
  const period = m[2] ? `week ${Number(m[2])}` : m[3] ? `${MONTHS[Number(m[4]) - 1] ?? m[4]} ${m[3]}` : "";
  return period ? `${kind} · ${period}` : kind;
}
