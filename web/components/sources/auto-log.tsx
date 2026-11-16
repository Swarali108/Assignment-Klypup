"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertCircle, ArrowRight, Bot, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { EmptyState, ErrorState, SectionHeader, SkeletonList } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { useLoad } from "@/lib/insights";
import { cn } from "@/lib/utils";
import { istStamp, sourcesApi, usd, type AutoLog, type Cycle, type ProcessedEntry, eventKindAndPeriod } from "./api";

const STATUS_WORD: Record<string, string> = {
  ok: "processed",
  failed: "failed",
  waiting: "waiting for a document",
  skipped: "skipped",
  needs_approval: "needs approval",
};

/** "its estimate…" → "Its estimate…". */
const sentence = (t: string) => (t ? t[0].toUpperCase() + t.slice(1) : t);

function schedulerLine(s: AutoLog["scheduler"]): string {
  const every = s.every_hours === Math.round(s.every_hours) ? `${s.every_hours} hours` : `${s.every_hours.toFixed(1)} hours`;
  if (!s.enabled || s.state === "off") return "Automatic checks are off on this server. Use Check for new filings now.";
  if (s.state === "another process") return `Automatic checks run every ${every} in another API process on this machine.`;
  if (s.state === "running") return `Automatic checks run every ${every}.${s.next_run_at ? ` Next at ${istStamp(s.next_run_at)}.` : ""}`;
  return `Automatic checks: ${s.state}.`;
}

/** What ran automatically, what it cost, today's spend against the cap, and what waits for approval. */
export function AutoLogView() {
  const [res, retry] = useLoad(sourcesApi.autoLog);
  return (
    <section id="auto-log" aria-labelledby="auto-log-title" className="scroll-mt-24 space-y-4">
      <SectionHeader
        title={<span id="auto-log-title">Auto-processing</span>}
        description="New events are processed automatically, oldest first, while today's spend stays under the daily cap. Anything that does not fit waits for an admin."
      />
      {res.state === "loading" ? <SkeletonList rows={3} /> : null}
      {res.state === "error" ? <ErrorState title="The auto-processing log could not be loaded" reason={res.reason} onRetry={retry} /> : null}
      {res.state === "ready" ? <Log data={res.data} /> : null}
    </section>
  );
}

function Log({ data }: { data: AutoLog }) {
  const t = data.today;
  const share = t.cap_usd > 0 ? Math.min(1, t.spent_usd / t.cap_usd) : 1;
  const full = t.cap_usd <= 0 || t.spent_usd >= t.cap_usd;
  return (
    <div className="space-y-6">
      <div className="rounded-xl border bg-surface px-5 py-5 shadow-(--shadow-card)">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[13px] text-muted-foreground">Spent automatically today ({t.day}, India time)</p>
            <p className="tnum mt-1 text-[26px] font-semibold leading-none tracking-[-0.02em] text-foreground">
              {usd(t.spent_usd)} <span className="text-base font-medium text-muted-foreground">of {usd(t.cap_usd)}</span>
            </p>
          </div>
          <p className="tnum text-[13px] text-muted-foreground">
            {usd(t.remaining_usd)} left · {t.runs} {t.runs === 1 ? "run" : "runs"} today
          </p>
        </div>
        <div
          className="relative mt-4 h-2 overflow-hidden rounded-full bg-secondary"
          role="meter"
          aria-valuemin={0}
          aria-valuemax={t.cap_usd}
          aria-valuenow={t.spent_usd}
          aria-label="Today's automatic spend against the daily cap"
        >
          <span className={cn("absolute inset-y-0 left-0 rounded-full transition-[width] duration-500 ease-out", full ? "bg-caution" : "bg-brand")} style={{ width: `${share * 100}%` }} />
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          {schedulerLine(data.scheduler)} {data.scheduler.last_run_at ? `Last check finished ${istStamp(data.scheduler.last_run_at)}.` : ""}
        </p>
      </div>

      {data.needs_approval.length ? (
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <h3 className="flex items-center gap-2 border-b border-hairline px-5 py-3 text-sm font-semibold">
            <ShieldAlert className="size-4 text-caution" aria-hidden /> Needs approval
            <span className="tnum rounded bg-caution-soft px-1.5 text-[11px] text-caution">{data.needs_approval.length}</span>
          </h3>
          <ul className="divide-y divide-hairline">
            {data.needs_approval.map((w) => (
              <li key={w.event_id} className="flex flex-col gap-2.5 px-5 py-3.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{w.company ?? w.event_id}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{sentence((w.reason ?? "").replace(/^Needs approval:\s*/, ""))}</p>
                </div>
                <Button asChild size="sm" variant="outline" className="self-start">
                  <Link href={`/events/${encodeURIComponent(w.event_id)}?process=1`}>
                    Review and process <ArrowRight />
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {data.cycles.length === 0 ? (
        <EmptyState icon={Bot} title="No automatic check has run yet">
          {data.scheduler.state === "running" || data.scheduler.state === "another process"
            ? `The first runs about a minute after the data service starts, then every ${data.scheduler.every_hours} hours. Check for new filings now runs one at once.`
            : "Automatic checks are off on this server. Check for new filings now runs one at once."}
        </EmptyState>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <h3 className="border-b border-hairline px-5 py-3 text-sm font-semibold">Recent checks</h3>
          <ol className="divide-y divide-hairline">
            {data.cycles.map((c) => (
              <CycleRow key={c.id} cycle={c} />
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

const RUNS_SHOWN = 10;

function CycleRow({ cycle }: { cycle: Cycle }) {
  const [showAll, setShowAll] = useState(false);
  const ok = cycle.sources.filter((s) => s.status === "ok").length;
  const tried = cycle.sources.filter((s) => s.status !== "disabled").length;
  const blocked = cycle.sources.filter((s) => s.status === "blocked");
  const ran = cycle.processed.filter((p) => p.status !== "needs_approval");
  const held = cycle.processed.length - ran.length;
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-sm font-semibold text-foreground">
          {cycle.trigger === "check-now" || cycle.trigger === "manual" ? "Checked now by an admin" : "Scheduled check"}
          <span className="tnum font-normal text-muted-foreground"> · {istStamp(cycle.started_at)}</span>
        </p>
        <p className="tnum text-[13px] text-muted-foreground">
          {cycle.status === "running" ? "running" : `spent ${usd(cycle.spent_usd)}`}
          {cycle.ceiling_usd !== null && cycle.ceiling_usd !== undefined ? ` (at most ${usd(cycle.ceiling_usd)} confirmed)` : ""}
        </p>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
        {ok} of {tried} sources read
        {blocked.length ? `; blocked: ${blocked.map((b) => b.name ?? b.id).join(", ")}` : ""} · {cycle.events_new} new or changed events
        {held ? ` · ${held} waiting for approval` : ""}
      </p>
      {cycle.error ? (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-negative">
          <AlertCircle className="mt-px size-3.5 shrink-0" aria-hidden /> {cycle.error}
        </p>
      ) : null}
      {ran.length ? (
        <>
          <ul className="mt-2.5 space-y-1.5">
            {(showAll ? ran : ran.slice(0, RUNS_SHOWN)).map((p, i) => (
              <RunLine key={`${p.event_id}-${i}`} entry={p} />
            ))}
          </ul>
          {ran.length > RUNS_SHOWN ? (
            <Button type="button" variant="ghost" size="sm" className="mt-2" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show fewer" : `Show all ${ran.length} events`}
            </Button>
          ) : null}
        </>
      ) : null}
    </li>
  );
}

function RunLine({ entry }: { entry: ProcessedEntry }) {
  const kind = eventKindAndPeriod(entry.event_id);
  const Icon = entry.status === "ok" ? CheckCircle2 : entry.status === "failed" ? AlertCircle : Clock3;
  return (
    <li className="flex items-start gap-2 text-[13px]">
      <Icon
        className={cn("mt-0.5 size-3.5 shrink-0", entry.status === "ok" ? "text-positive" : entry.status === "failed" ? "text-negative" : "text-info")}
        aria-hidden
      />
      <Link href={`/events/${encodeURIComponent(entry.event_id)}`} className="min-w-0 flex-1 truncate text-foreground underline-offset-4 hover:underline">
        {entry.company ?? entry.event_id}
        {kind ? <span className="font-normal text-muted-foreground"> · {kind}</span> : null}
      </Link>
      <span className="shrink-0 text-xs text-muted-foreground">{STATUS_WORD[entry.status] ?? entry.status}</span>
      <span className="tnum w-16 shrink-0 text-right text-xs text-foreground">{entry.status === "ok" ? usd(entry.cost_usd) : "–"}</span>
    </li>
  );
}
