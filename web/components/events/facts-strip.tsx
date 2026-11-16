import { ExternalLink, FileText, ScanLine } from "lucide-react";
import { cn } from "@/lib/utils";
import { resolveApiUrl } from "@/lib/api";
import { formatUSD } from "@/lib/format";
import { EvidenceChip, FreshnessBadge } from "@/components/ds";
import type { Evidence } from "@/lib/types";
import type { EventDetail, FactInput } from "./types";

function firstEvidence(inputs: FactInput[] | undefined): Evidence[] {
  const seen = new Set<string>();
  const out: Evidence[] = [];
  for (const i of inputs ?? [])
    for (const e of i.evidence.slice(0, 1)) {
      const k = `${e.doc_sha}:${e.pdf_index}`;
      if (!seen.has(k)) {
        seen.add(k);
        out.push(e);
      }
    }
  return out.slice(0, 2);
}

function Fact({
  label,
  value,
  sub,
  evidence,
  muted,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  evidence?: Evidence[];
  muted?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 bg-surface px-5 py-4">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("tnum text-[15px] font-semibold leading-snug text-foreground", muted && "font-medium text-muted-foreground")}>{value}</dd>
      {sub ? <dd className="tnum text-xs leading-snug text-muted-foreground">{sub}</dd> : null}
      {evidence?.length ? (
        <dd className="mt-1 flex flex-wrap gap-1.5">
          {evidence.map((e) => (
            <EvidenceChip
              key={`${e.doc_sha}-${e.pdf_index}`}
              evidence={e}
              className="h-auto min-h-6 max-w-full min-w-0 items-start justify-start py-1 text-left leading-snug break-words whitespace-normal"
            />
          ))}
        </dd>
      ) : null}
    </div>
  );
}

function dateStatusNote(status: string, asPrinted: string | null): string | null {
  if (status === "scheduled") return asPrinted ? `Scheduled: “${asPrinted}”` : "Scheduled date from the filing";
  if (status === "verified") return asPrinted ? `Printed as “${asPrinted}”` : null;
  return null;
}

const EXCHANGE_TYPES = new Set(["block_deal", "insider_sale", "ofs_stock_exchange"]);

/** What an event with no filing documents was read from (only what the event payload already says). */
function noDocsNote(event: EventDetail): string {
  if (EXCHANGE_TYPES.has(event.type)) return `Read from the exchange's own ${(event.type_label ?? "deal").toLowerCase()} records; there is no filing PDF for this event.`;
  return "No filing documents are attached to this event yet.";
}

/** Company facts: price basis, key dates, issue type, documents and the last read. */
export function FactsStrip({ event }: { event: EventDetail }) {
  const offer = typeof event.offer_size === "string" ? event.offer_size : event.offer_size?.display ?? null;
  const facts: React.ReactNode[] = [];

  facts.push(
    <Fact
      key="price"
      label={event.price?.label ?? "Price"}
      value={event.price?.display ?? "Not disclosed"}
      muted={!event.price?.display}
      sub={event.price?.reason ?? undefined}
      evidence={firstEvidence(event.price?.inputs)}
    />,
  );
  for (const d of event.dates ?? []) {
    facts.push(
      <Fact
        key={d.label}
        label={d.label}
        value={d.date_iso ? d.display : "Not confirmed"}
        muted={!d.date_iso}
        sub={d.date_iso ? [d.relative, dateStatusNote(d.status, d.as_printed)].filter(Boolean).join(" · ") : "No date printed in the filings read"}
        evidence={firstEvidence(d.inputs)}
      />,
    );
  }
  facts.push(<Fact key="type" label="Issue type" value={event.issue_type ?? event.type_label ?? "–"} sub={offer ?? undefined} />);

  const cols = facts.length >= 4 ? "lg:grid-cols-4" : facts.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-2";
  const run = event.run;

  return (
    <section aria-label="Event facts" className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <dl className={cn("grid grid-cols-1 gap-px bg-hairline sm:grid-cols-2", cols)}>{facts}</dl>
      <div className="border-t border-hairline px-5 py-4">
        <h3 className="mb-2.5 text-xs text-muted-foreground">Filings read</h3>
        {event.docs.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">{noDocsNote(event)}</p>
        ) : null}
        <ul className="flex flex-col gap-2">
          {event.docs.map((d) => (
            <li key={d.doc_sha} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
              <span className="inline-flex min-w-0 items-center gap-2 font-medium text-foreground">
                <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                {d.label}
              </span>
              {d.pages ? <span className="tnum text-xs text-muted-foreground">{d.pages.toLocaleString("en-IN")} pages</span> : null}
              {d.note && d.note !== event.company ? <span className="min-w-0 truncate text-xs text-faint max-sm:basis-full">{d.note}</span> : null}
              {d.scanned ? (
                <span className="inline-flex h-5 items-center gap-1 rounded-md bg-caution-soft px-1.5 text-[11px] font-medium text-caution ring-1 ring-inset ring-caution/15">
                  <ScanLine className="size-3" aria-hidden /> {d.scanned_label ?? "Scanned filing: text not readable yet"}
                </span>
              ) : null}
              <FreshnessBadge fetchedAt={d.fetched_at} ageDays={d.age_days} stale={d.stale} />
              <a
                href={d.url ? resolveApiUrl(d.url) : d.source_url}
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-brand-ink underline-offset-4 hover:underline max-sm:ml-0"
              >
                Open PDF <ExternalLink className="size-3" aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      </div>
      {run?.run_at ? (
        <p className="tnum border-t border-hairline bg-surface-sunken/50 px-5 py-2.5 text-xs text-muted-foreground">
          Last read {new Date(run.run_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" })}
          {run.seconds !== null ? ` · took ${Math.round(run.seconds)} s` : ""}
          {run.fresh_cost_usd !== null ? <span data-tech>{` · ${formatUSD(run.fresh_cost_usd)} to read from scratch`}</span> : null}
        </p>
      ) : null}
    </section>
  );
}
