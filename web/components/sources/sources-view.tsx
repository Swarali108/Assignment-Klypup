"use client";

import { useState } from "react";
import { AlertCircle, Ban, ChevronDown, CircleCheck, CircleDashed, ExternalLink, Radar, ShieldAlert } from "lucide-react";
import { EmptyState, ErrorState, SkeletonCard } from "@/components/ds";
import { useLoad } from "@/lib/insights";
import { cn } from "@/lib/utils";
import { BrightDataCard } from "./brightdata-card";
import { istStamp, sourcesApi, type SourceRow, type SourceState, type SourcesResponse } from "./api";

const STATE: Record<SourceState, { label: string; icon: typeof CircleCheck; cls: string }> = {
  on: { label: "On", icon: CircleCheck, cls: "bg-positive-soft text-positive ring-positive/15" },
  off: { label: "Off", icon: Ban, cls: "bg-secondary text-muted-foreground ring-border" },
  blocked: { label: "Blocked", icon: ShieldAlert, cls: "bg-caution-soft text-caution ring-caution/15" },
  failed: { label: "Could not be read", icon: AlertCircle, cls: "bg-negative-soft text-negative ring-negative/15" },
  "not checked": { label: "Not checked yet", icon: CircleDashed, cls: "bg-info-soft text-info ring-info/15" },
};

const OWNER_COPY: Record<string, { title: string; blurb: string }> = {
  SEBI: { title: "SEBI", blurb: "Offer documents, buybacks and takeover letters from SEBI's public filing lists, plus draft offer documents as an early warning." },
  NSE: { title: "NSE", blurb: "Exchange announcements (allotment, listing, OFS, buyback, acquisitions), block and bulk deals, insider disclosures." },
  BSE: { title: "BSE", blurb: "The same signals from BSE: corporate announcements, deals and insider disclosures." },
};

export function StateChip({ state, className }: { state: SourceState; className?: string }) {
  const s = STATE[state] ?? STATE["not checked"];
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-2 text-xs font-medium ring-1 ring-inset", s.cls, className)}>
      <Icon className="size-3.5" aria-hidden />
      {s.label}
    </span>
  );
}

/** The Sources page body: one card per publisher (SEBI, NSE, BSE), each source with its state, why, terms, risk, last check, counts and errors. */
export function SourcesView() {
  const [res, retry] = useLoad(sourcesApi.sources);
  if (res.state === "loading")
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  if (res.state === "error") return <ErrorState title="Sources could not be loaded" reason={res.reason} onRetry={retry} />;
  if (!res.data.sources.length)
    return (
      <EmptyState icon={Radar} title="No sources configured">
        Add a source in the discovery settings and it shows here with its terms and risk.
      </EmptyState>
    );
  return <Sources data={res.data} />;
}

function Sources({ data }: { data: SourcesResponse }) {
  const owners = ["SEBI", "NSE", "BSE", "Other"].filter((o) => data.sources.some((s) => s.owner === o));
  const exchangeOff = data.switch.value === "off";
  return (
    <div className="space-y-6">
      <p className="text-[13px] leading-relaxed text-muted-foreground">
        NSE and BSE reading is <span className="font-semibold text-foreground">{exchangeOff ? "off" : "on"}</span>
        {data.switch.reader === "missing" && !exchangeOff ? " but the exchange reader is not installed in this build" : ""}. Switch:{" "}
        <code className="rounded bg-secondary px-1 py-0.5 text-[12px] break-words text-foreground">{data.switch.name}=on|off</code>. Every site gets at least 2 seconds
        between requests, every page is cached, and a 401, 403 or 429 stops that source for the run.
        {data.refreshed_at ? <span className="tnum"> Last check {istStamp(data.refreshed_at)}.</span> : " No check has run yet."}
      </p>
      {owners.map((owner) => (
        <OwnerCard key={owner} owner={owner} rows={data.sources.filter((s) => s.owner === owner)} />
      ))}
      <BrightDataCard />
    </div>
  );
}

function OwnerCard({ owner, rows }: { owner: string; rows: SourceRow[] }) {
  const copy = OWNER_COPY[owner] ?? { title: owner, blurb: "" };
  const risk = rows[0]?.risk;
  const terms = rows.find((r) => r.terms_url)?.terms_url;
  const high = risk?.level === "high";
  return (
    <section aria-labelledby={`owner-${owner}`} className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <header className="flex flex-col gap-3 border-b border-hairline px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id={`owner-${owner}`} className="text-base font-semibold">
            {copy.title}
          </h2>
          {copy.blurb ? <p className="mt-0.5 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">{copy.blurb}</p> : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
          {risk ? (
            <span
              className={cn(
                "inline-flex h-6 items-center gap-1.5 rounded-md px-2 text-xs font-medium ring-1 ring-inset",
                high ? "bg-caution-soft text-caution ring-caution/20" : "bg-positive-soft text-positive ring-positive/15",
              )}
            >
              {high ? <ShieldAlert className="size-3.5" aria-hidden /> : <CircleCheck className="size-3.5" aria-hidden />}
              {high ? "High risk" : risk.level === "low" ? "Low risk" : "Risk not assessed"}
            </span>
          ) : null}
          {terms ? (
            <a
              href={terms}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-6 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-brand"
            >
              Terms <ExternalLink className="size-3" aria-hidden />
              <span className="sr-only">(opens a new tab)</span>
            </a>
          ) : null}
        </div>
      </header>
      {risk ? <p className={cn("border-b border-hairline px-5 py-2.5 text-xs leading-relaxed", high ? "bg-caution-soft/40 text-foreground" : "text-muted-foreground")}>{risk.label}</p> : null}
      <ul className="divide-y divide-hairline">
        {rows.map((row) => (
          <SourceLine key={row.id} row={row} />
        ))}
      </ul>
    </section>
  );
}

function SourceLine({ row }: { row: SourceRow }) {
  const [open, setOpen] = useState(false);
  const reason = row.state === "not checked" ? "Read at the next check." : row.reason;
  const showReason = row.state !== "on" && reason;
  return (
    <li className="px-5 py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <p className="text-sm font-semibold text-foreground">{row.name.split("·").slice(-1)[0].trim()}</p>
            <StateChip state={row.state} className="h-5 px-1.5 text-[11px]" />
          </div>
          {showReason ? <p className="mt-1 max-w-[72ch] text-[13px] leading-relaxed text-muted-foreground">{reason}</p> : null}
        </div>
        <dl className="grid shrink-0 grid-cols-[3.5rem_3.5rem_auto] gap-x-5 text-left sm:text-right">
          <div>
            <dt className="text-[11px] text-faint">Items</dt>
            <dd className="tnum text-sm font-semibold text-foreground">{row.state === "off" ? "–" : row.items || row.records || 0}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-faint">Errors</dt>
            <dd className={cn("tnum text-sm font-semibold", row.error_count ? "text-negative" : "text-foreground")}>{row.error_count}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-faint">Last checked</dt>
            <dd className="tnum whitespace-nowrap text-[13px] text-foreground">{istStamp(row.last_checked)}</dd>
          </div>
        </dl>
      </div>
      {row.errors.length ? (
        <div className="mt-2">
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-brand"
          >
            {open ? "Hide" : "Show"} {row.errors.length === 1 ? "the error" : `${row.errors.length} errors`}
            <ChevronDown className={cn("size-3.5 transition-transform duration-200", open && "rotate-180")} aria-hidden />
          </button>
          {open ? (
            <ul className="mt-2 space-y-1 rounded-lg bg-surface-sunken px-3 py-2 text-xs leading-relaxed text-muted-foreground">
              {row.errors.map((e, i) => (
                <li key={i} className="break-words">
                  {e}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
