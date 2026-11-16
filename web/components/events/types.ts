/**
 * Response shapes used by the Events screens (api/CONTRACT.md: /events, /events/{id}, /events/{id}/people,
 * /feed, /events/from-links, /events, /events/{id}/run, /jobs/{id}). Kept in this folder so shared
 * lib/types.ts stays untouched.
 */
import type { CallItem, EventRef, EventSummary, Evidence } from "@/lib/types";

export interface FactInput {
  label: string;
  value: string;
  evidence: Evidence[];
}

export interface EventDate {
  label: string;
  date_iso: string | null;
  display: string;
  relative: string;
  status: string;
  as_printed: string | null;
  inputs: FactInput[];
}

export interface EventPrice {
  kind: string;
  label: string;
  display: string;
  low: number | null;
  high: number | null;
  inputs: FactInput[];
  reason: string | null;
}

export interface EventDetail extends EventSummary {
  as_of: string;
  discovered_on?: string | null;
  price: EventPrice | null;
  dates: EventDate[];
  issue_type: string | null;
  offer_size: { display?: string; inputs?: FactInput[] } | string | null;
  run: { cost_usd: number | null; fresh_cost_usd: number | null; seconds: number | null; run_at: string | null } | null;
}

export type PeopleItem = CallItem & { context_reason?: string | null };

export interface EventPeople {
  event: EventRef;
  callable: PeopleItem[];
  entities: PeopleItem[];
  context: PeopleItem[];
  empty_reason: string | null;
}

export type FeedStatus = "ready" | "empty" | "failed" | "waiting" | "unsupported" | "scanned" | "watch" | "needs_approval";

export interface FeedItem {
  id: string;
  title: string;
  company: string;
  source: string;
  published_iso: string | null;
  published_display: string;
  link: string;
  kind_label: string;
  event_type: string | null;
  event_id: string | null;
  status: FeedStatus;
  status_label: string;
  reason: string;
  next_action: string;
  processable: boolean;
  money_date: string | null;
  money_date_display: string;
  /** Who published it: "SEBI" | "NSE" | "BSE" (signals v2). */
  source_badge?: string | null;
  /** The discovery class, e.g. "ipo_coming", "block_deal", "insider_sale". */
  signal?: string | null;
}

export interface FeedResponse {
  refreshed_at: string;
  sources_ok: string[];
  sources_with_problems: string[];
  items_total: number;
  groups: { today: FeedItem[]; upcoming: FeedItem[]; recent: FeedItem[] };
}

export interface Proposal {
  url: string;
  doc_type: string | null;
  event_type: string | null;
  label: string | null;
  type_quote: string | null;
  company: string | null;
  company_quote: string | null;
  how: string;
  error: string | null;
}

export interface ProposalsResponse {
  proposals: Proposal[];
  suggested: { company: string | null; event_type: string | null };
  /** Additive field (Task 6): an event already in the app for these links. */
  existing_event_id?: string | null;
}

export interface JobStart {
  job_id: string;
  event_id: string;
  state: "running" | "complete" | "failed";
  steps: { step: string; label: string }[];
  stream_url: string;
}

/** One Server-Sent Event from /jobs/{id}/stream (step event or the final event). */
export interface JobEvent {
  /** "agent" for an agent / code sub-step event (no step, no state); absent for step and final events. */
  type?: "agent";
  phase?: "start" | "done" | "progress";
  agent?: string;
  /** For agent events: the step the agent belongs to. */
  parent?: string | null;
  why?: string;
  given?: string;
  runs_on?: string;
  doing?: string;
  returns?: Record<string, number | boolean | null>;
  status?: string;
  ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  cached_calls?: number;
  done?: number;
  step?: string;
  label?: string;
  state?: "start" | "done" | "failed" | "complete";
  index?: number;
  total?: number;
  seconds?: number;
  cost_usd?: number;
  calls?: number;
  cached?: number;
  reason?: string | null;
  at?: number;
}

/** One agent or code step of a run (GET /api/events/{id}/trace). */
export interface TraceRecord {
  name: string;
  kind: "step" | "agent";
  step: string | null;
  label: string;
  why: string;
  given: string;
  returns: Record<string, number | boolean | null>;
  runs_on: string;
  status: string;
  ms: number;
  /** Milliseconds after the run started (live traces only). */
  start_ms?: number;
  order: number;
  calls: number;
  cached_calls: number;
  fresh_calls: number;
  failed_calls?: number;
  unpriced_calls?: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  agents?: string[];
  error?: string;
}

export interface TraceTotals {
  calls: number;
  cached_calls: number;
  fresh_calls: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  ms: number;
}

export interface EventTrace {
  event_id: string;
  run_id: string;
  started_at: string;
  source: "live" | "rebuilt from logs";
  total_ms: number;
  totals: TraceTotals;
  cost_log: { calls: number; cached_calls: number; cost_usd: number };
  balanced: boolean;
  steps: TraceRecord[];
  agents: TraceRecord[];
}

export interface RunSummary {
  run_id: string;
  started_at: string;
  status: string;
  full: boolean;
  seconds: number;
  calls: number;
  cached_calls: number;
  cached_share: number | null;
  cost_usd: number;
}

export interface EventRuns {
  event_id: string;
  count: number;
  runs: RunSummary[];
  first: RunSummary | null;
  latest: RunSummary | null;
  saved_vs_first: { cost_usd: number; seconds: number } | null;
}
