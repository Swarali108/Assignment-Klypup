/**
 * Gallery / placeholder data in the API contract shape, built by scripts/make_fixtures.py from real
 * outputs (SEDEMAC IPO, Spacenet OFS) and the API contract's own examples.
 */
import raw from "./fixtures.json";
import type { AskResponse, CallItem, Evidence, EventSummary, JobStep, PersonCard, Summary } from "@/lib/types";

export const fixtures = raw as unknown as {
  summary: Summary;
  today: CallItem[];
  person: PersonCard;
  evidence: Evidence;
  events: EventSummary[];
  steps: JobStep[];
  ask: AskResponse | null;
};
