/** Fetchers for the Events screens, on top of the shared `apiFetch` (no change to lib/api.ts). */
import { apiFetch } from "@/lib/api";
import type { EventSummary } from "@/lib/types";
import type { EventDetail, EventPeople, EventRuns, EventTrace, FeedResponse, JobEvent, JobStart, ProposalsResponse } from "./types";

const enc = encodeURIComponent;

export const eventsApi = {
  list: () => apiFetch<{ count: number; events: EventSummary[] }>("/events"),
  detail: (id: string) => apiFetch<EventDetail>(`/events/${enc(id)}`),
  people: (id: string) => apiFetch<EventPeople>(`/events/${enc(id)}/people`),
  trace: (id: string) => apiFetch<EventTrace>(`/events/${enc(id)}/trace`),
  runs: (id: string) => apiFetch<EventRuns>(`/events/${enc(id)}/runs`),
  feed: () => apiFetch<FeedResponse>("/feed"),
  fromLinks: (urls: string[]) =>
    apiFetch<ProposalsResponse>("/events/from-links", { method: "POST", body: JSON.stringify({ urls }) }),
  create: (spec: { event_id: string; event_type: string; company: string; documents: { url: string; doc_type: string }[] }) =>
    apiFetch<{ event_id: string; created: boolean }>("/events", { method: "POST", body: JSON.stringify(spec) }),
  run: (id: string) => apiFetch<JobStart>(`/events/${enc(id)}/run`, { method: "POST" }),
  job: (jobId: string) => apiFetch<{ job_id: string; state: string; events: JobEvent[] }>(`/jobs/${enc(jobId)}`),
};

export const EVENT_KIND_LABEL: Record<string, string> = {
  ipo: "IPO",
  buyback: "Buyback",
  ofs_stock_exchange: "Offer for sale (exchange)",
};

export const DOC_TYPE_LABEL: Record<string, string> = {
  rhp: "Red herring prospectus",
  prospectus: "Prospectus",
  letter_of_offer: "Letter of offer",
  public_announcement: "Public announcement",
  announcement: "Exchange notice",
  news: "News article",
};

/** "VECTRAS ENPROCON LIMITED" -> "Vectras Enprocon Limited"; mixed-case names pass through. */
export function tidyCompany(name: string | null | undefined): string {
  if (!name) return "";
  const n = name.trim().replace(/\s+/g, " ");
  if (n !== n.toUpperCase()) return n;
  return n.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase());
}

/** A safe event id: lowercase slug of company + type + yyyymm (matches the server's slug rule). */
export function makeEventId(company: string, eventType: string, asOfIso: string): string {
  const slug = company
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60)
    .replace(/_+$/g, "");
  const month = asOfIso.slice(0, 7).replace("-", "");
  return [slug || "event", eventType, month].join("_");
}
