/** Types for GET /api/people/{event}/{person}/trail and the Bright Data enrichment routes (api/trail.py, api/enrichment.py). */
import type { AmountDetail, Evidence } from "@/lib/types";
import type { TimingDetail } from "@/components/person/types";

export type TrailStatus = "ok" | "warn" | "info" | "none";
type StepBase = { title: string; summary: string; status: TrailStatus };

export type TrailDocument = { label: string; url: string; source_url: string; cached: boolean; pages: number | null };
export type TrailPage = { pdf_index: number; printed_page: string | null; score: number | null; terms: string[]; used: boolean; doc_label: string | null };
export type TrailQuote = { field: string; label: string; value: string | null; quote: string | null; evidence: Evidence; page_corrected: boolean };
export type TrailRejection = { field: string; label: string; value: string; section: string; reason: string };
export type TrailMerge = { pair: string[]; score: number | null; outcome: string; method: string };
export type TrailPart = { label: string; value: string; note: string };
export type TrailPlaceholder = { key: string; value: string };

export type LinkedInCandidate = {
  name: string | null;
  headline: string | null;
  city: string | null;
  positions: { title: string | null; company: string | null; start: string | null; end: string | null }[] | null;
  education: { school: string | null; start_year: string | null; end_year: string | null }[] | null;
  profile_url: string | null;
  fetched_at: string | null;
  match: "likely" | "unconfirmed";
  reason: string;
  source?: string;
};
export type WebMention = { title: string; source: string | null; date: string | null; url: string; label?: string; fetched_at?: string };
export type LookupBlock<T> = { state: "found" | "none" | "error" | "off"; error: string | null; fetched_at?: string | null; requests?: number } & T;
export type EnrichmentRecord = {
  updated_at?: string;
  linkedin?: LookupBlock<{ candidates?: LinkedInCandidate[] }>;
  web?: LookupBlock<{ rows?: WebMention[] }>;
};

export type TrailStep = StepBase &
  (
    | { key: "documents"; documents: TrailDocument[] }
    | { key: "pages"; sections: { section: string; label: string; why: string; pages: TrailPage[] }[] }
    | { key: "quotes"; groups: { section: string; label: string; model: string | null; cached: boolean | null; calls: number | null; rows: TrailQuote[] }[] }
    | { key: "checks"; applied: string[]; passed: { label: string; section: string; page: string | number | null; corrected: boolean }[]; rejected: TrailRejection[]; conflicts: { field: string; detail: string }[] }
    | {
        key: "identity";
        names: string[];
        holder_type: string | null;
        holder_type_reason: string | null;
        merges: TrailMerge[];
        merged: number;
        family: { members: string[]; reasons: string[] } | null;
        strong_model_checks: number;
        other_filings: number;
      }
    | { key: "money"; amounts: AmountDetail[]; timing: TimingDetail[] }
    | {
        key: "rank";
        group?: string;
        rank?: number;
        tier?: string;
        score?: string;
        parts: TrailPart[];
        later?: { value_cr: string | null; score: string | null } | null;
        reasons?: string[];
      }
    | {
        key: "brief";
        written_by?: "assistant" | "template";
        model?: string | null;
        prompt_version?: string | null;
        attempts?: { n: number; problem: string | null }[];
        fallback_reason?: string | null;
        placeholders?: TrailPlaceholder[];
        template_lines?: string[] | null;
        lines?: string[];
      }
    | { key: "enrichment"; linkedin: EnrichmentRecord["linkedin"] | null; web: EnrichmentRecord["web"] | null; requests?: number; updated_at?: string }
    | {
        key: "cost";
        cost_usd?: number | null;
        fresh_usd?: number | null;
        calls?: number | null;
        seconds?: number | null;
        run?: { run_id: string | null; people: number | null; seconds: number | null; cost_usd: number | null; fresh_usd: number | null; calls: number | null; cached_calls: number | null; cached_share: number | null };
        enrichment_requests?: number;
      }
  );

export type Trail = { event: { id: string; company: string; type_label?: string }; person: { id: string; name: string }; run_id: string | null; steps: TrailStep[]; generated_from: string[] };

export type EnrichKind = "linkedin" | "web";
export type EnrichmentStatus = {
  linkedin_enabled: boolean;
  web_enabled: boolean;
  token_configured: boolean;
  month: string;
  cap: number;
  used: number;
  remaining: number;
  requests?: number;
  records?: number;
  counting?: string;
  error: string | null;
  ready: boolean;
};
export type EnrichmentEstimate = {
  kinds: Partial<Record<EnrichKind, { allowed: boolean; reason: string | null; label: string; requests: number; cached: boolean; worst_case: number }>>;
  total: number;
  cap: number;
  used: number;
  remaining: number;
  over_cap: boolean;
  month: string;
};
export type PersonEnrichment = {
  event_id: string;
  person_id: string;
  name: string;
  company: string;
  record: EnrichmentRecord | null;
  running: { kinds: EnrichKind[]; started_at: string } | null;
  estimate: EnrichmentEstimate;
  eligibility: Record<EnrichKind, { allowed: boolean; reason: string | null }>;
  status: EnrichmentStatus;
  web_label: string;
};
