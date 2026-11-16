"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertCircle, Ban, CalendarClock, CheckCircle2, Database, Globe2, Loader2, RefreshCw, RotateCw, ShieldCheck, Wallet } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, SectionHeader, SkeletonCard, SkeletonStat, StatCard, StatStrip } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { formatCount, formatUSD } from "@/lib/format";
import { useLoad } from "@/lib/insights";
import { adminApi, formatBytes, istStamp, pct, type Health } from "@/lib/admin";

export function HealthView() {
  const [res, retry] = useLoad(adminApi.health);
  if (res.state === "loading")
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-surface md:grid-cols-4" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <SkeletonStat key={i} />
          ))}
        </div>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  if (res.state === "error") return <ErrorState title="System health could not load" reason={res.reason} onRetry={retry} />;
  return <Health data={res.data} reload={retry} />;
}

function Bar({ share, tone = "brand" }: { share: number | null | undefined; tone?: "brand" | "caution" | "negative" }) {
  const width = Math.max(0, Math.min(1, share ?? 0)) * 100;
  const color = tone === "negative" ? "bg-negative" : tone === "caution" ? "bg-caution" : "bg-brand";
  return (
    <div className="h-2 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-valuenow={Math.round(width)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cn("h-full rounded-full transition-[width]", color)} style={{ width: `${width}%` }} />
    </div>
  );
}

const toneFor = (share: number | null | undefined) => ((share ?? 0) >= 1 ? "negative" : (share ?? 0) >= 0.8 ? "caution" : "brand");

function Card({ title, icon: Icon, children, className }: { title: string; icon: React.ComponentType<{ className?: string }>; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("min-w-0 rounded-xl border bg-surface p-5 shadow-(--shadow-card)", className)}>
      <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon className="size-4 text-faint" aria-hidden /> {title}
      </h3>
      {children}
    </section>
  );
}

function Health({ data, reload }: { data: Health; reload: () => void }) {
  const { spend } = data;
  const blocked = data.sources.sources.filter((s) => s.status === "blocked" || s.status === "failed");
  return (
    <div className="space-y-8">
      <StatStrip>
        <StatCard icon={Wallet} label="Model spend today" value={formatUSD(spend.today.cost_usd)} sub={spend.daily_cap_usd ? `of ${formatUSD(spend.daily_cap_usd)} a day` : "No daily limit set"} />
        <StatCard label="Model calls today" value={formatCount(spend.today.calls)} sub={`${formatCount(spend.today.paid_calls)} paid, ${formatCount(spend.today.cached_calls)} from the cache`} />
        <StatCard icon={Database} label="Answers from the cache" value={pct(spend.today.cache_hit_rate)} muted={spend.today.cache_hit_rate === null} sub={`${pct(spend.all_time.cache_hit_rate)} over all time`} />
        <StatCard
          icon={data.failed_runs.length ? AlertCircle : ShieldCheck}
          label="Failed runs"
          value={String(data.failed_runs.length)}
          sub={blocked.length ? `${blocked.length} source${blocked.length === 1 ? "" : "s"} blocked or failing` : "Every source answers"}
        />
      </StatStrip>

      <section className="space-y-3">
        <SectionHeader
          title="Failed runs"
          description="The latest run of each event, when it did not finish. Retry runs it again from the cache."
          actions={
            <Button variant="outline" size="sm" onClick={reload}>
              <RefreshCw /> Refresh
            </Button>
          }
        />
        <FailedRuns runs={data.failed_runs} onRetried={reload} />
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        <Card title="Spend and limits" icon={Wallet}>
          <div className="space-y-5">
            <Limit
              label="Model spend today"
              used={formatUSD(spend.today.cost_usd)}
              of={spend.daily_cap_usd ? formatUSD(spend.daily_cap_usd) : null}
              share={spend.daily_cap_used}
              missing="No daily limit is set. Set MODEL_DAILY_CAP_USD to see how much of it is used."
            />
            <Limit
              label="Bright Data requests this month"
              used={data.brightdata.available && data.brightdata.requests != null ? formatCount(data.brightdata.requests) : null}
              of={data.brightdata.cap ? formatCount(data.brightdata.cap) : null}
              share={data.brightdata.used_share}
              missing={data.brightdata.available ? (data.brightdata.error ?? "No monthly limit is set. Set BRIGHTDATA_MONTHLY_CAP.") : (data.brightdata.reason ?? "Bright Data is not part of this build.")}
            />
            <div className="border-t border-hairline pt-4 text-[13px] text-muted-foreground">
              Most one event may spend in a run: <span className="tnum font-medium text-foreground">{formatUSD(spend.event_budget_usd)}</span> ({spend.budget_mode} mode). Answers the provider served from its own prompt cache:{" "}
              <span className="tnum font-medium text-foreground">{pct(spend.provider_cache.hit_rate)}</span>.
            </div>
          </div>
        </Card>

        <Card title="Caches" icon={Database}>
          <ul className="space-y-4">
            {data.caches.map((c) => {
              const biggest = Math.max(...data.caches.map((x) => x.bytes), 1);
              return (
                <li key={c.key} className="space-y-1.5">
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="font-medium text-foreground">{c.label}</span>
                    <span className="tnum text-muted-foreground">
                      {formatBytes(c.bytes)} · {formatCount(c.files)} files
                    </span>
                  </div>
                  <Bar share={c.bytes / biggest} />
                </li>
              );
            })}
            <li className="border-t border-hairline pt-3 text-[13px] text-muted-foreground">
              Of all {formatCount(spend.all_time.calls)} model calls so far, {formatCount(spend.all_time.cached_calls)} ({pct(spend.all_time.cache_hit_rate)}) were answered from the model-answer cache.
            </li>
          </ul>
        </Card>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        <Card title="Where filings come from" icon={Globe2}>
          {data.sources.sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">Discovery has not run yet, so no source has been checked.</p>
          ) : (
            <>
              <ul className="divide-y divide-hairline">
                {data.sources.sources.map((s) => (
                  <li key={s.id} className="flex min-w-0 items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                    <SourceIcon status={s.status} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">{s.name}</p>
                      <p className="text-xs break-words text-muted-foreground">
                        {s.status === "ok" ? sourceCount(s as HealthSource) : s.status === "disabled" ? "Switched off" : s.status === "blocked" ? "Blocked by the site" : "Failed"}
                        {s.reason && s.status !== "ok" ? ` · ${s.reason.length > 120 ? `${s.reason.slice(0, 120)}…` : s.reason}` : ""}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted-foreground">Last checked {istStamp(data.sources.refreshed_at)}</p>
            </>
          )}
        </Card>

        <Card title="Scheduler" icon={CalendarClock}>
          <SchedulerBody scheduler={data.scheduler} />
        </Card>
      </div>
      <p className="text-xs text-muted-foreground">
        Checked {istStamp(data.checked_at)} · A source document counts as stale after {data.stale_after_days} days (STALE_AFTER_DAYS).
      </p>
    </div>
  );
}

function SourceIcon({ status }: { status: string }) {
  if (status === "ok") return <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-positive" aria-label="Working" />;
  if (status === "disabled") return <Ban className="mt-0.5 size-4 shrink-0 text-faint" aria-label="Switched off" />;
  return <AlertCircle className="mt-0.5 size-4 shrink-0 text-negative" aria-label="Not working" />;
}

function Limit({ label, used, of, share, missing }: { label: string; used: string | null; of: string | null; share: number | null | undefined; missing: string }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium text-foreground">{label}</span>
        <span className="tnum text-muted-foreground">
          {used ?? "–"}
          {of ? ` of ${of}` : ""}
        </span>
      </div>
      {of && share != null ? <Bar share={share} tone={toneFor(share)} /> : <p className="text-xs leading-snug text-muted-foreground">{missing}</p>}
    </div>
  );
}

type HealthSource = Health["sources"]["sources"][number] & { records?: number | null };

/** Filings listed, or (for deal and insider feeds that list rows rather than filings) the records read. */
function sourceCount(s: HealthSource): string {
  if (s.items) return `${formatCount(s.items)} filings listed`;
  if (s.records) return `${formatCount(s.records)} records read`;
  return "0 filings listed";
}

const SCHEDULER_STATE: Record<string, string> = {
  running: "Running",
  off: "Off on this server",
  "another process": "Running in another API process",
  "not started": "Not started",
  stopped: "Stopped",
};

function SchedulerBody({ scheduler }: { scheduler: Health["scheduler"] }) {
  if (!scheduler.available) return <p className="text-sm text-muted-foreground">{scheduler.reason ?? "The scheduler is not part of this build."}</p>;
  if (scheduler.error) return <p className="text-sm text-negative">{scheduler.error}</p>;
  const state = typeof scheduler.state === "string" ? scheduler.state : null;
  const every = typeof scheduler.every_hours === "number" ? scheduler.every_hours : null;
  const when = (v: unknown) => (typeof v === "string" && v ? istStamp(v) : "–");
  const rows: [string, string][] = [];
  if (typeof scheduler.enabled === "boolean") rows.push(["Automatic checks", scheduler.enabled ? "On" : "Off"]);
  if (state) rows.push(["Status", SCHEDULER_STATE[state] ?? state]);
  if (every !== null) rows.push(["Runs every", `${every} ${every === 1 ? "hour" : "hours"}`]);
  if ("next_run_at" in scheduler) rows.push(["Next run", when(scheduler.next_run_at)]);
  if ("last_run_at" in scheduler) rows.push(["Last run", when(scheduler.last_run_at)]);
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">The scheduler is installed but reports nothing yet.</p>;
  return (
    <dl className="space-y-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-3">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="tnum text-right font-medium text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function FailedRuns({ runs, onRetried }: { runs: Health["failed_runs"]; onRetried: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  if (runs.length === 0)
    return (
      <EmptyState icon={ShieldCheck} title="No failed runs" tone="brand">
        Every event&apos;s latest run finished. A run that stops shows up here with the reason and a Retry button.
      </EmptyState>
    );
  async function retry(eventId: string) {
    setBusy(eventId);
    try {
      const r = await adminApi.run({ event_id: eventId, step: "all", fresh: false });
      if (!r.needs_confirm) toast.success("Started again. Follow it in the pipeline console.");
      onRetried();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not start the run.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <ul className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      {runs.map((r) => (
        <li key={r.event_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5">
          <AlertCircle className="size-4 shrink-0 text-negative" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-foreground">{r.company}</p>
            <p className="text-xs leading-snug text-muted-foreground">
              {istStamp(r.at)} · {r.reason}
            </p>
          </div>
          <Button asChild variant="ghost" size="sm">
            <Link href="/admin/pipeline">Console</Link>
          </Button>
          <Button variant="outline" size="sm" disabled={busy !== null || r.running} onClick={() => void retry(r.event_id)}>
            {busy === r.event_id || r.running ? <Loader2 className="animate-spin" /> : <RotateCw />}
            {r.running ? "Running" : "Retry"}
          </Button>
        </li>
      ))}
    </ul>
  );
}
