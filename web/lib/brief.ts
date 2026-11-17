import { apiFetch } from "@/lib/api";

export type BriefBullet = { topic: string; text: string; link: string };
export type Brief = {
  day: string;
  bullets: BriefBullet[];
  written_by: string;
  model: string | null;
  cost_usd: number;
  ask_prompt: string;
  as_of: string;
  generated_at: string;
  shown: boolean;
  cached: boolean;
};
export type Since = { last_visit: string | null; since_known: boolean; new_events: number; new_people: number; new_event_names?: string[] };

export const briefApi = {
  get: (day: string, refresh = false) => apiFetch<Brief>("/me/brief", { query: { day, refresh: refresh ? 1 : undefined } }),
  shown: (day: string) => apiFetch<{ ok: boolean }>("/me/brief/shown", { method: "POST", body: JSON.stringify({ day }) }),
  since: () => apiFetch<Since>("/me/since"),
};

/** "$0.0004", or "$0" when the words were written by code. */
export function briefCost(usd: number): string {
  if (!usd) return "$0";
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

/** Where the sheet's "Ask about this" button leaves words for the home composer. */
export const PREFILL_KEY = "finsight.prefill";
export const PREFILL_EVENT = "finsight:prefill";
