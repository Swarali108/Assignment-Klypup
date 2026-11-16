/**
 * Response shapes of the local API, matching `api/CONTRACT.md` (Task 3). Optional fields are ones
 * the API sends but the design system does not depend on.
 */

export type EventType = "ipo" | "buyback" | "ofs" | string;
export type Tier = "cash_now" | "unlock" | "holding";
export type ConfidenceLevel = "high" | "medium" | "low";
/** Values seen: in_hand, due_past, scheduled, after_date, unlocked, partly_unlocked, locked_in, not_applicable, unknown. */
export type TimingStatus = string;
export type EventStatus = "ready" | "processing" | "failed" | "scanned" | "not_supported" | "not_processed";
export type RmStatus = "to_call" | "called" | "follow_up" | "meeting_booked" | "won" | "not_now" | "not_a_fit";

export interface EventRef {
  id: string;
  company: string;
  type: EventType;
  type_label?: string;
}

export interface PersonRef {
  id: string;
  name: string;
  role: string | null;
  holder_type: string;
  /** "Family trust" / "Family (HUF)" for a family vehicle; null for a person. */
  kind_label?: string | null;
}

/** value_cr is null when the amount is unknown: show `display` + `reason`, never ₹0. */
export interface Amount {
  value_cr: number | null;
  low_cr?: number | null;
  /** Short ready-made text ("₹6.08 Cr", "Amount not disclosed"). */
  display: string;
  /** Longer stored sentence ("Up to ₹6.08 crore, if all offered shares are sold"). */
  detail?: string | null;
  kind: "cash" | "shares";
  estimate: boolean;
  reason?: string | null;
  source?: string;
}

export interface Timing {
  label: string;
  status: TimingStatus;
  date_iso: string | null;
  past?: boolean;
}

export interface Confidence {
  level: ConfidenceLevel;
  reason: string;
  reasons?: string[];
}

export interface HouseholdMember {
  /** "<event_id>/<person_id>" */
  id: string;
  name: string;
  role: string | null;
  tier: Tier;
  amount: Amount;
}

export interface Household {
  id: string;
  label: string;
  reason: string;
  members: HouseholdMember[];
  printed_members?: string[];
}

export interface CallItem {
  /** "<event_id>/<person_id>" */
  id?: string;
  event: EventRef;
  person: PersonRef;
  tier: Tier;
  tier_label: string;
  amount: Amount;
  timing: Timing;
  confidence: Confidence;
  why: string;
  brief_first_line: string;
  household?: Household | null;
  household_id?: string | null;
  /** On a household slot in /today: the other members (the slot itself is the lead). */
  members?: HouseholdMember[];
  household_total_cr?: number | null;
  rank?: number;
  score?: number;
  flags?: string[];
  position?: number;
  rm: { status: RmStatus; follow_up: string | null; note?: string };
  /** The person's name matches one in the signed-in RM's client book. */
  in_book?: boolean;
  /** Where this sale was reported (an insider disclosure and an offer notice are one sale, shown once). */
  sources?: string[];
  /** On a /today slot: this holder's repeat sales at the same company, newest first (the slot is the newest). */
  trades?: TradeRef[];
  trades_total_cr?: number | null;
  trades_total_display?: string | null;
  trades_unpriced?: number;
}

/** One sale on a folded /today slot; its own row on the event page. */
export interface TradeRef {
  /** "<event_id>/<person_id>" */
  id: string;
  event: EventRef;
  date_iso: string | null;
  date_display: string;
  amount: Amount;
  sources: string[];
  /** The call status logged against this trade's own row (a call logged on the Today row is saved on the newest). */
  rm_status: RmStatus;
}

export interface TodayResponse {
  as_of: string;
  count: number;
  items: CallItem[];
}

export interface Summary {
  as_of: string;
  as_of_display?: string;
  people_to_call: number;
  people_total?: number;
  households?: number;
  cash_now_cr: number | null;
  cash_now_people?: number;
  unlock_people?: number;
  new_events_this_week: number;
  events_processed: number;
  events_total?: number;
  called?: number;
}

export interface EventDoc {
  doc_sha: string;
  label: string;
  doc_type?: string;
  note?: string;
  source_url?: string;
  /** API-relative ("/api/docs/<sha>.pdf"); resolve with `resolveApiUrl`. */
  url: string;
  pages?: number;
  scanned: boolean;
  scanned_label: string | null;
  fetched_at?: string | null;
  age_days?: number | null;
  stale?: boolean;
}

export interface MoneyDate {
  kind: string;
  label: string;
  date_iso: string | null;
  confirmed: boolean;
  display: string;
  relative: string;
}

export interface EventSummary {
  id: string;
  company: string;
  type: EventType;
  type_label?: string;
  status: EventStatus;
  status_reason: string | null;
  people_count: number;
  entities_count?: number;
  context_count?: number;
  tier_counts?: Partial<Record<Tier, number>>;
  cash_cr: number | null;
  listing_date: string | null;
  money_date?: MoneyDate;
  empty_reason: string | null;
  docs: EventDoc[];
  source?: string;
}

export interface Evidence {
  doc_sha: string;
  doc_label: string;
  /** null for an exchange record (a deal or disclosure row), which has no PDF page. */
  pdf_index: number | null;
  printed_page: string | null;
  quote: string;
  /** API-relative PDF link at the page. */
  url: string;
  source_url?: string;
  /** API-relative highlighted page PNG. */
  image_url?: string;
  /** false: PDF not on this machine; show the quote and the source link only. */
  cached?: boolean;
  /** When this document was fetched (UTC ISO), its age in days and whether it is past the stale limit. */
  fetched_at?: string | null;
  age_days?: number | null;
  stale?: boolean;
}

/** Fetched dates of the documents behind one person's or one event's facts. */
export interface Freshness {
  documents: { doc_sha: string; label: string; fetched_at: string | null; age_days: number | null; stale: boolean }[];
  oldest_fetched_at: string | null;
  newest_fetched_at: string | null;
  stale: boolean;
  stale_after_days: number;
}

export interface AmountInput {
  label: string;
  value: string;
  evidence: Evidence[];
}

export interface AmountDetail {
  key: string;
  label: string;
  status?: string;
  value_cr: number | null;
  low_cr?: number | null;
  /** Long sentence. */
  display: string;
  /** Short ("₹6.08 Cr"). */
  short?: string;
  working: string | null;
  reason?: string | null;
  inputs: AmountInput[];
  caveats?: string[];
}

export interface RmState {
  event_id?: string;
  person_id?: string;
  status: RmStatus;
  note: string;
  follow_up_date: string | null;
  updated_at: string | null;
  /** The amount (Rs Cr) the RM entered when the deal was won. */
  won_amount_cr?: number | null;
}

export interface PersonCard extends Omit<CallItem, "rm"> {
  list?: "callable" | "entities" | "context";
  brief: { lines: string[]; written_by?: string };
  why_now: string;
  tier_reason?: string;
  amounts: AmountDetail[];
  timing_detail?: Record<string, unknown>[];
  name_evidence?: Evidence[];
  rank_reasons?: string[];
  context_reason?: string | null;
  event_facts?: Record<string, unknown>;
  freshness?: Freshness;
  rm: RmState & { follow_up?: string | null };
}

export interface AskResponse {
  question: string;
  filters: Record<string, unknown>;
  chips: string[];
  people: CallItem[];
  count: number;
  interpreted_by: "assistant" | "rules" | "keyword" | string;
  explanation: string;
}

export interface JobStep {
  step: string;
  state?: "start" | "done" | "failed";
  seconds: number;
  cost_usd: number;
}
