"use client";

import { AddEventDialog } from "./add-event-dialog";
import { ProcessPanel } from "./process-panel";
import type { JobEvent, ProposalsResponse } from "./types";
import { applyEvent, initialJob, STEPS } from "./use-job";

/** Captured stream payloads (api/CONTRACT.md, job stream section). */
function run(events: JobEvent[]) {
  return events.reduce(applyEvent, initialJob());
}
const done = (i: number, s: number): JobEvent[] => [
  { step: STEPS[i].step, label: STEPS[i].label, state: "start", at: s },
  { step: STEPS[i].step, label: STEPS[i].label, state: "done", seconds: 1.8 + i, cost_usd: 0, at: s + 1.8 + i },
];
const RUNNING = run([...done(0, 0), ...done(1, 1.8), { step: "people", label: STEPS[2].label, state: "start", at: 4.6 }]);
const COMPLETE = run([...STEPS.flatMap((_, i) => done(i, i * 2)), { state: "complete", reason: null, seconds: 11.2, cost_usd: 0, at: 11.2 }]);
const FAILED = run([
  { step: "locate", label: "Find the right pages", state: "start", at: 0 },
  { step: "locate", label: "Find the right pages", state: "done", seconds: 0.2, cost_usd: 0, at: 0.2 },
  { step: "extract", label: "Read the tables", state: "start", at: 0.2 },
  { step: "extract", label: "Read the tables", state: "failed", at: 0.2 },
  { state: "failed", reason: "A document could not be downloaded while reading the tables. The previous call list is kept.", at: 0.2 },
]);

const LINK = "https://vectrasgroup.com/wp-content/uploads/2026/11/Prospectus_VEL_2026_Clean.pdf";
const PROPOSALS: ProposalsResponse = {
  proposals: [
    {
      url: LINK,
      doc_type: "prospectus",
      event_type: "ipo",
      label: "prospectus",
      type_quote: "PROSPECTUS Dated: November 03, 2026 Please read Section 26 of the Companies Act, 2013 100% Book Built Offer",
      company: "VECTRAS ENPROCON LIMITED",
      company_quote: null,
      how: "rules",
      error: null,
    },
    {
      url: "https://example.org/notice.html",
      doc_type: null,
      event_type: null,
      label: null,
      type_quote: null,
      company: null,
      company_quote: null,
      how: "rules",
      error: "not a PDF (text/html)",
    },
  ],
  suggested: { company: "VECTRAS ENPROCON LIMITED", event_type: "ipo" },
};

export function EventsGallery({ dialog }: { dialog: string | null }) {
  return (
    <div className="space-y-6">
      <ProcessPanel company="Vectras Enprocon Limited" view={RUNNING} />
      <ProcessPanel company="Vectras Enprocon Limited" view={COMPLETE} onDismiss={() => {}} />
      <ProcessPanel company="Vectras Enprocon Limited" view={FAILED} onDismiss={() => {}} onRetry={() => {}} />
      <div className="flex flex-wrap gap-3">
        <AddEventDialog asOf="2026-11-15" defaultOpen={dialog === "new"} initial={{ links: LINK, result: PROPOSALS }} />
        <AddEventDialog
          asOf="2026-11-15"
          defaultOpen={dialog === "existing"}
          initial={{ links: LINK, result: { ...PROPOSALS, proposals: PROPOSALS.proposals.slice(0, 1), existing_event_id: "vectras_ipo" } }}
        />
      </div>
    </div>
  );
}
