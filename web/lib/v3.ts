/** Typed calls for the v3 screens: team, review queue, watchlists and alerts, chat models (api/CONTRACT.md v3c). */
import { apiFetch } from "@/lib/api";

export type Rm = { email: string; name: string; role: "rm" | "head" | "admin" };
export type Assignment = { rm_email: string; rm_name: string; assigned_by: string; assigned_at: string };

export type TeamCounts = {
  assigned: number;
  calls: number;
  meetings: number;
  won: number;
  won_cr: number;
  followups_due: number;
  days_to_first_call: number | null;
  days_samples: number;
};
export type TeamDashboard = {
  as_of: string;
  total: TeamCounts;
  rms: (TeamCounts & { email: string; name: string; role: string | null })[];
  event_types: (TeamCounts & { event_type: string; type_label: string })[];
  unassigned_calls: number;
};

export type ReviewDecision = { id: string; label: string; action: string; by: string; at: string | null };
export type ReviewItem = {
  id: string;
  kind: "pair" | "holder" | "low";
  event: { id: string; company: string; type_label?: string };
  person_ids: string[];
  names: string[];
  title: string;
  why: string;
  pipeline: string;
  by: string;
  score?: number | null;
  link?: string;
  actions: { action: "confirm" | "reject" | "merge"; label: string; value?: string }[];
  decision: ReviewDecision | null;
};
export type ReviewQueue = { open: number; decided: number; items: ReviewItem[] };

export type Follow = { kind: "person" | "company"; key: string; label: string; origin_event_id: string; created_at: string };
export type Alert = { id: string; kind: "new" | "lockin" | "block" | "amount"; title: string; detail: string; link: string; created_at: string; read: boolean };

export type ChatModel = { id: string; label: string; note: string; input_per_m: number; output_per_m: number; cache_read_per_m: number | null };
export type CompareResult = {
  model: string;
  text: string;
  cards: { kind: string; title?: string }[];
  blocked: string | null;
  cost_usd: number;
  tokens?: { input: number; output: number; cached_input: number } | null;
  models_used: { model: string; calls: number; cost_usd: number }[];
  seconds: number;
};

const enc = encodeURIComponent;
const json = (body: unknown) => JSON.stringify(body);

export const v3 = {
  team: () => apiFetch<TeamDashboard>("/team"),
  rms: () => apiFetch<{ rms: Rm[] }>("/team/rms"),
  assignments: () => apiFetch<{ assignments: Record<string, Assignment> }>("/assignments"),
  assign: (eventId: string, personId: string, rmEmail: string | null) =>
    apiFetch<{ assignment: Assignment | null }>(`/assignments/${enc(eventId)}/${enc(personId)}`, { method: "PUT", body: json({ rm_email: rmEmail }) }),
  review: () => apiFetch<ReviewQueue>("/review"),
  decide: (id: string, action: string) => apiFetch<{ decision: ReviewDecision }>("/review/decide", { method: "POST", body: json({ id, action }) }),
  undo: (id: string) => apiFetch<{ undone: boolean }>("/review", { method: "DELETE", query: { id } }),
  follows: () => apiFetch<{ follows: Follow[] }>("/watch"),
  follow: (kind: "person" | "company", eventId: string, personId?: string) =>
    apiFetch<{ kind: "person" | "company"; key: string; label: string }>("/watch", { method: "POST", body: json({ kind, event_id: eventId, person_id: personId }) }),
  unfollow: (kind: string, key: string) => apiFetch<{ ok: boolean }>("/watch", { method: "DELETE", query: { kind, key } }),
  alerts: () => apiFetch<{ unread: number; items: Alert[] }>("/alerts"),
  markRead: (ids: string[] | null) => apiFetch<{ changed: number }>("/alerts/read", { method: "POST", body: json({ ids }) }),
  models: () => apiFetch<{ models: ChatModel[]; default_fast: string; default_strong: string; priced_from: string }>("/chat/models"),
  compare: (question: string, models: [string, string]) => apiFetch<{ question: string; results: CompareResult[] }>("/chat/compare", { method: "POST", body: json({ question, models }) }),
};
