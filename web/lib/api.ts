/**
 * Typed client for the data service.
 *
 * In the browser every request goes to the same origin ("/api/...", rewritten by Next to the data service),
 * so the session cookie travels with it. On the server (server components) the data service is called
 * directly and the visitor's cookie is forwarded.
 */
import type { EnrichKind, EnrichmentStatus, PersonEnrichment, Trail } from "@/lib/trail";
import type { AskResponse, EventSummary, PersonCard, RmState, Summary, TodayResponse } from "@/lib/types";

// Same variable as next.config.ts / proxy.ts: API_ORIGIN (API_INTERNAL_ORIGIN is the older name).
const SERVER_BASE = `${(process.env.API_ORIGIN || process.env.API_INTERNAL_ORIGIN || "http://127.0.0.1:8000").replace(/\/+$/, "")}/api`;

/** Public base for URLs the browser loads (images, PDFs, CSV, streams): always same-origin. */
export const API_BASE = "/api";

/** Turn an API-relative path from a response ("/api/...") into a URL the browser can load; absolute URLs pass through. */
export function resolveApiUrl(pathOrUrl: string): string {
  if (/^https?:\/\//.test(pathOrUrl)) return pathOrUrl;
  return pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public path: string,
  ) {
    super(message);
  }
}

export function apiUrl(path: string, query?: Record<string, string | number | boolean | null | undefined>, base: string = API_BASE): string {
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

export async function apiFetch<T>(path: string, init?: RequestInit & { query?: Parameters<typeof apiUrl>[1] }): Promise<T> {
  const { query, ...rest } = init ?? {};
  const onServer = typeof window === "undefined";
  const url = apiUrl(path, query, onServer ? SERVER_BASE : API_BASE);
  const headers: Record<string, string> = { Accept: "application/json", ...(rest.headers as Record<string, string> | undefined) };
  // Every write is JSON, even without a body: the data service refuses anything else (cross-site protection).
  if (rest.method && rest.method !== "GET") headers["Content-Type"] = "application/json";
  if (onServer) {
    const { cookies } = await import("next/headers");
    headers.cookie = (await cookies()).toString();
  }
  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store", ...rest, headers });
  } catch {
    throw new ApiError("The data service is not reachable. Start it and try again.", 0, path);
  }
  if (!res.ok) {
    if (res.status === 401 && !onServer && !window.location.pathname.startsWith("/login") && path !== "/auth/login") {
      // A full page load on purpose: it drops every cached screen of the expired session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    }
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : (body?.reason ?? "");
    } catch {}
    throw new ApiError(detail || `Request failed (${res.status})`, res.status, path);
  }
  return (await res.json()) as T;
}

export type SessionUser = {
  email: string;
  name: string;
  role: "admin" | "head" | "rm" | "viewer";
  permissions: Record<"view" | "edit_rm" | "export" | "ask" | "process" | "ops" | "team" | "review", boolean>;
  /** APP_ENV=production on the data service: no sample files or demo text. */
  production?: boolean;
};

export const api = {
  me: () => apiFetch<SessionUser>("/auth/me"),
  login: (email: string, password: string) =>
    apiFetch<SessionUser>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => apiFetch<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  summary: () => apiFetch<Summary>("/summary"),
  today: (limit?: number) => apiFetch<TodayResponse>("/today", { query: { limit } }),
  events: () => apiFetch<{ count: number; events: EventSummary[] }>("/events"),
  event: (id: string) => apiFetch<Record<string, unknown>>(`/events/${encodeURIComponent(id)}`),
  eventPeople: (id: string) => apiFetch<Record<string, unknown>>(`/events/${encodeURIComponent(id)}/people`),
  person: (eventId: string, personId: string) =>
    apiFetch<PersonCard>(`/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}`),
  rm: (eventId: string, personId: string) =>
    apiFetch<RmState>(`/rm/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}`),
  /** PUT body: {status?, note?, follow_up_date?}; "" clears the date. */
  saveRm: (eventId: string, personId: string, body: Partial<Pick<RmState, "status" | "note" | "follow_up_date" | "won_amount_cr">>) =>
    apiFetch<RmState>(`/rm/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  /** How we found them: the pipeline's own record for one person. */
  trail: (eventId: string, personId: string) =>
    apiFetch<Trail>(`/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}/trail`),
  /** Stored public profile + web mentions, a running flag, and the worst-case request estimate for a refresh. */
  enrichment: (eventId: string, personId: string) =>
    apiFetch<PersonEnrichment>(`/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}/enrichment`),
  /** Confirmed paid lookup (202, runs in the background). confirmedRequests must cover the estimate. */
  refreshEnrichment: (eventId: string, personId: string, kinds: EnrichKind[], confirmedRequests: number) =>
    apiFetch<{ started: boolean; kinds: EnrichKind[]; requests_estimated: number }>(
      `/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}/enrichment`,
      { method: "POST", body: JSON.stringify({ kinds, confirmed_requests: confirmedRequests, refresh: true }) },
    ),
  /** For the Sources page: requests used / cap this month, the LinkedIn switch. */
  enrichmentStatus: () => apiFetch<EnrichmentStatus>("/enrichment/status"),
  ask: (q: string) => apiFetch<AskResponse>("/ask", { method: "POST", body: JSON.stringify({ q }) }),
};

/** Source page image with the quote highlighted (falls back to the plain page; header X-Highlight: none). */
export function evidencePageUrl(e: { doc_sha: string; pdf_index: number | null; quote: string; image_url?: string | null }): string {
  if (e.image_url) return resolveApiUrl(e.image_url);
  return apiUrl("/evidence/page.png", { doc_sha: e.doc_sha, pdf_index: e.pdf_index ?? 0, quote: e.quote });
}

/** Cached PDF at a page. */
export function docPdfUrl(sha: string, pdfIndex?: number): string {
  return `${apiUrl(`/docs/${sha}.pdf`)}${pdfIndex ? `#page=${pdfIndex}` : ""}`;
}

/** Server-Sent Events stream for a processing job. */
export function jobStreamUrl(jobId: string): string {
  return apiUrl(`/jobs/${encodeURIComponent(jobId)}/stream`);
}

export function exportCsvUrl(): string {
  return apiUrl("/export/calls.csv");
}
