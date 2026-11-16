import type { AmountInput, Evidence, PersonCard } from "@/lib/types";

export interface TimingPeriod {
  label: string;
  ends_on: string | null;
  display: string;
  status: string;
  share_of_retained?: string;
}

export interface TimingDetail {
  key: string;
  label: string;
  status: string;
  display: string;
  note: string | null;
  periods: TimingPeriod[];
  rule_evidence: Evidence[];
  inputs: AmountInput[];
  rule_found?: boolean | null;
}

export interface EventFacts {
  price?: { kind: string; label: string; display: string; inputs?: AmountInput[]; reason?: string | null } | null;
  money_date?: { kind: string; label: string; date_iso: string | null; confirmed: boolean } | null;
}

export type Card = PersonCard & {
  names_as_printed?: string[];
  context_reason?: string | null;
};

export function evKey(e: Evidence) {
  return `${e.doc_sha}:${e.pdf_index}:${e.quote}`;
}

export function uniqueEvidence(list: Evidence[]): Evidence[] {
  const seen = new Set<string>();
  const out: Evidence[] = [];
  for (const e of list) {
    const k = evKey(e);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(e);
  }
  return out;
}

/** Every evidence ref on the card, in reading order (amounts, timing, name, event facts), de-duplicated. */
export function allEvidence(card: Card): { evidence: Evidence; context: string }[] {
  const out: { evidence: Evidence; context: string }[] = [];
  const seen = new Set<string>();
  const push = (e: Evidence, context: string) => {
    const k = evKey(e);
    if (seen.has(k)) return;
    seen.add(k);
    out.push({ evidence: e, context });
  };
  for (const a of card.amounts ?? []) for (const i of a.inputs ?? []) for (const e of i.evidence ?? []) push(e, i.label);
  for (const t of (card.timing_detail ?? []) as unknown as TimingDetail[]) {
    for (const i of t.inputs ?? []) for (const e of i.evidence ?? []) push(e, i.label);
    for (const e of t.rule_evidence ?? []) push(e, `${t.label}: the rule`);
  }
  for (const e of card.name_evidence ?? []) push(e, "Name in the filing");
  const facts = card.event_facts as EventFacts | undefined;
  for (const i of facts?.price?.inputs ?? []) for (const e of i.evidence ?? []) push(e, i.label);
  return out;
}

/** One chip per document page (several quotes on the same page open the first). */
export function uniquePages(list: Evidence[]): Evidence[] {
  const seen = new Set<string>();
  return list.filter((e) => {
    const k = `${e.doc_sha}:${e.pdf_index}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}
