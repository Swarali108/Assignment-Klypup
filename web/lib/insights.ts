"use client";

/**
 * Types, fetchers and a small loading hook for the Calendar, Network and Trust & Ops screens.
 * Kept apart from lib/api.ts and lib/types.ts so other screens can change those freely.
 */
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { CHAT_MOCK } from "@/lib/chat";
import type { EventRef, Tier } from "@/lib/types";

export type CalendarKind = "listing" | "unlock" | "buyback_payment" | "buyback_closing" | "ofs_sale" | string;

export interface CalendarPerson {
  id: string;
  person_id: string;
  name: string;
  tier: Tier;
  value_cr: number | null;
  value_kind: "cash" | "shares";
  /** True when the amount is an estimate (an "up to" figure or a value at offer price). */
  estimate?: boolean;
}

export interface CalendarItem {
  date_iso: string;
  display: string;
  relative: string;
  kind: CalendarKind;
  label: string;
  event: EventRef;
  confirmed: boolean;
  past: boolean;
  people: CalendarPerson[];
  total_cr: number | null;
  people_count: number;
  unknown_count: number;
  /** A dated listing with nobody to call yet: shown as a listing day, never as ₹0. */
  listing_only?: boolean;
}

export interface CalendarResponse {
  from: string | null;
  to: string | null;
  as_of: string;
  count: number;
  items: CalendarItem[];
}

export interface NetNode {
  id: string;
  type: "event" | "person" | "entity";
  label: string;
  event?: EventRef;
  people_count?: number;
  event_id?: string;
  person_id?: string;
  role?: string | null;
  tier?: Tier;
  list?: string;
  value_cr?: number | null;
  estimate?: boolean;
  company?: string;
  also_in?: string[];
  event_count?: number;
  money_events?: number;
  in_household?: boolean;
  event_types?: string[];
  /** Company dots: individuals to call across this company's events (a name counted once; funds excluded). */
  to_call?: number;
  /** Company dots: holders drawn linked to this company, split into people and companies/funds. */
  linked_people?: number;
  linked_entities?: number;
  /** Company dots: every money event behind the dot, most people to call first (the dot opens events[0]). */
  events?: { event: EventRef; date_iso: string | null; to_call: number }[];
}

export interface NetEdge {
  source: string;
  target: string;
  kind: "holds" | "household" | "same_person" | string;
  reason: string;
}

export interface NetworkResponse {
  nodes: NetNode[];
  edges: NetEdge[];
  legend: Record<string, string>;
}

export interface OpsStep {
  step: string;
  label: string;
  seconds: number;
  calls: number;
  cached: number;
  cost_usd: number;
}

export interface OpsSection {
  section: string;
  proposed: number;
  kept: number;
  rejected: number;
}

export interface OpsRejection {
  who: string;
  what: string;
  value: string;
  reason: string;
  section: string;
}

export interface OpsEvent {
  event: EventRef;
  cost_usd: number;
  fresh_cost_usd: number;
  per_person_usd: number;
  fresh_per_person_usd: number;
  model_calls: number;
  cached_share: number;
  people: number;
  run_seconds: number;
  run_at: string | null;
  steps: OpsStep[];
  verification: { sections: OpsSection[]; proposed: number; kept: number; rejected: number };
  rejections: OpsRejection[];
}

export interface OpsRun {
  event_id: string;
  started_at: string;
  seconds: number;
  cost_usd: number;
  status: string;
  error: string | null;
}

export interface OpsResponse {
  target_usd: number;
  events: OpsEvent[];
  totals: {
    events: number;
    fresh_cost_usd: number;
    max_fresh_cost_usd: number;
    avg_fresh_cost_usd: number;
    proposed: number;
    kept: number;
    rejected: number;
  };
  recent_runs: OpsRun[];
}

/** GET /api/ops/tokens (CHAT_CONTRACT v2). `by_model` rows: any field may be missing on an older service. */
export interface OpsTokenModel {
  model: string;
  calls?: number;
  input_tokens?: number;
  cached_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  saved_usd?: number;
}
export interface OpsTokens {
  questions: number;
  avg_cost_usd: number;
  /** 0–1: share of input tokens served from the provider's prompt cache */
  cache_hit_rate: number;
  cached_tokens: number;
  input_tokens?: number;
  saved_usd_by_cache: number;
  compressions: number;
  tokens_saved_by_compression: number;
  total_cost_usd?: number;
  by_model: OpsTokenModel[];
}

export const insightsApi = {
  calendar: () => apiFetch<CalendarResponse>("/calendar"),
  network: () => apiFetch<NetworkResponse>("/network"),
  ops: () => apiFetch<OpsResponse>("/ops"),
  /** null when this data service does not record chat tokens yet (404). */
  opsTokens: async (): Promise<OpsTokens | null> => {
    if (CHAT_MOCK) return (await import("@/lib/chat-mock")).mockOpsTokens();
    try {
      return await apiFetch<OpsTokens>("/ops/tokens");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },
};

export type Loadable<T> =
  | { state: "loading" }
  | { state: "error"; reason: string }
  | { state: "ready"; data: T };

/** Fetch once on mount; `retry()` fetches again (used by the error state's button). */
export function useLoad<T>(fetcher: () => Promise<T>): [Loadable<T>, () => void] {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    let live = true;
    fetcher()
      .then((data) => live && setResult({ state: "ready", data }))
      .catch((e: unknown) =>
        live && setResult({ state: "error", reason: e instanceof Error ? e.message : "The data could not be loaded." }),
      );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);
  const retry = useCallback(() => {
    setResult({ state: "loading" });
    setAttempt((a) => a + 1);
  }, []);
  return [result, retry];
}
