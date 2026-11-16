"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CheckCircle2, CircleDollarSign, Gauge, ShieldCheck, ShieldX, Timer, XCircle } from "lucide-react";
import { BarList } from "@/components/charts/bar-list";
import { VerificationChart } from "@/components/charts/verification-chart";
import { EmptyState, ErrorState, SectionHeader, SkeletonList, SkeletonStat, StatCard, StatStrip } from "@/components/ds";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCount } from "@/lib/format";
import { insightsApi, useLoad, type OpsEvent, type OpsResponse } from "@/lib/insights";
import { TokenPanel } from "./token-panel";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { eventKindAndPeriod } from "@/components/sources/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function short(name: string) {
  const t = name === name.toUpperCase() ? name.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()) : name;
  return t.replace(/\s+(limited|ltd\.?)$/i, "");
}

/** "2026-11-15T10:20:26Z" → "15 Nov, 15:50 IST" (fixed +05:30, no clock or locale involved). */
function istStamp(iso: string | null) {
  if (!iso) return "–";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "–";
  const d = new Date(t + 330 * 60_000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${hh}:${mm} IST`;
}

/** Dollars with enough digits to compare tiny costs: $0.0129, $0.0021, $2.00. */
function formatUSD(n: number | null | undefined) {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  if (n === 0) return "$0.00";
  return n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`;
}

function secs(n: number) {
  if (n < 0.1) return "< 0.1 s";
  if (n < 60) return `${n < 10 ? n.toFixed(1) : Math.round(n)} s`;
  const m = Math.floor(n / 60);
  return `${m} min ${Math.round(n - m * 60)} s`;
}

/** Rows shown before "Show all": the page lists hundreds of events, most of them deals that cost nothing. */
const TOP_ROWS = 25;

const pct = (a: number, b: number) => (b ? `${((a / b) * 100).toFixed(1)}%` : "–");

export function OpsView() {
  const [res, retry] = useLoad(insightsApi.ops);
  if (res.state === "loading") return <OpsSkeleton />;
  if (res.state === "error") return <ErrorState title="Trust & Ops could not load" reason={res.reason} onRetry={retry} />;
  if (res.data.events.length === 0)
    return (
      <EmptyState icon={ShieldCheck} title="Nothing checked yet" tone="brand">
        Once an event is read, every value checked against the filing, the cost of reading it and the time each step took appear here.
      </EmptyState>
    );
  return <Ops data={res.data} />;
}

function Ops({ data }: { data: OpsResponse }) {
  const events = data.events;
  const checked = (e: OpsEvent) => e.verification.kept + e.verification.rejected;
  const kept = events.reduce((s, e) => s + e.verification.kept, 0);
  const rejected = events.reduce((s, e) => s + e.verification.rejected, 0);
  // Every value the model proposed is "checked"; those neither kept nor rejected were set aside (no page, no name).
  const proposed = events.reduce((s, e) => s + (e.verification.proposed ?? 0), 0) || kept + rejected;
  const setAside = Math.max(0, proposed - kept - rejected);
  const priciest = [...events].sort((a, b) => b.fresh_cost_usd - a.fresh_cost_usd)[0];
  const avg = data.totals.avg_fresh_cost_usd;
  const target = data.target_usd;
  const companyOf = useMemo(() => new Map(events.map((e) => [e.event.id, e.event.company])), [events]);

  const [allChecks, setAllChecks] = useState(false);
  const [allCosts, setAllCosts] = useState(false);
  const checkedEvents = useMemo(() => [...events].filter((e) => checked(e) > 0).sort((a, b) => checked(b) - checked(a)), [events]);
  const verifRows = useMemo(() => {
    const shown = allChecks ? checkedEvents : checkedEvents.slice(0, TOP_ROWS);
    const count = new Map<string, number>();
    for (const e of shown) count.set(short(e.event.company), (count.get(short(e.event.company)) ?? 0) + 1);
    return shown.map((e) => {
      const name = short(e.event.company);
      // The chart cuts labels at 21 characters, so a repeated company keeps its week or month in the part that survives.
      const when = (count.get(name) ?? 0) > 1 ? eventKindAndPeriod(e.event.id).split(" · ")[1] : undefined;
      return { id: e.event.id, name: when ? `${name.length > 21 - when.length - 3 ? `${name.slice(0, 21 - when.length - 4).trim()}…` : name} · ${when}` : name, kept: e.verification.kept, rejected: e.verification.rejected };
    });
  }, [checkedEvents, allChecks]);
  const costRows = useMemo(() => {
    const byCost = [...events].sort((a, b) => b.fresh_cost_usd - a.fresh_cost_usd);
    return allCosts ? byCost : byCost.filter((e) => e.fresh_cost_usd > 0).slice(0, TOP_ROWS);
  }, [events, allCosts]);
  const [sel, setSel] = useState<string>(() => verifRows[0]?.id ?? "");
  const selected = events.find((e) => e.event.id === sel) ?? events[0];

  const steps = useMemo(() => {
    const m = new Map<string, { label: string; total: number; n: number }>();
    for (const e of events)
      for (const s of e.steps) {
        const cur = m.get(s.step) ?? { label: s.label, total: 0, n: 0 };
        cur.total += s.seconds;
        cur.n += 1;
        m.set(s.step, cur);
      }
    return [...m.entries()].map(([k, v]) => ({ key: k, label: v.label, avg: v.total / Math.max(1, v.n) }));
  }, [events]);
  const totalCalls = events.reduce((s, e) => s + e.model_calls, 0);
  const reused = events.reduce((s, e) => s + e.model_calls * e.cached_share, 0);

  return (
    <div className="space-y-12">
      <StatStrip>
        <StatCard label="Values checked" icon={ShieldCheck} value={formatCount(proposed)} sub={`Against the filing text, across ${events.length} events`} />
        <StatCard label="Kept after checking" icon={CheckCircle2} value={pct(kept, proposed)} sub={`${formatCount(kept)} kept · ${formatCount(rejected)} rejected${setAside ? ` · ${formatCount(setAside)} set aside` : ""}, never shown`} />
        <StatCard
          label="Average cost per event"
          icon={CircleDollarSign}
          value={formatUSD(avg)}
          sub={`Budget ${formatUSD(target)} · ${avg ? `${Math.round(target / avg)}× under` : "within budget"}`}
        />
        <StatCard
          label="Most expensive event"
          icon={Gauge}
          value={formatUSD(priciest?.fresh_cost_usd)}
          sub={priciest ? `${short(priciest.event.company)} · ${pct(priciest.fresh_cost_usd, target)} of budget` : undefined}
        />
      </StatStrip>

      <section className="space-y-4">
        <SectionHeader
          title="How we know"
          description="Every value read from a filing is checked against the page before it is used: the number must be on the page, in that person's row, under the right heading. Values that fail are rejected and never reach a call list."
        />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:items-start">
          <div className="rounded-xl border bg-surface p-4 shadow-(--shadow-card) sm:p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-medium">Values kept and rejected, per event</p>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <span className="size-2.5 rounded-sm bg-brand" /> Kept
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="size-2.5 rounded-sm bg-negative/70" /> Rejected
                </span>
              </div>
            </div>
            <VerificationChart rows={verifRows} selected={selected?.event.id ?? null} onSelect={setSel} />
            {checkedEvents.length > TOP_ROWS ? (
              <Button type="button" variant="ghost" size="sm" className="mt-2" aria-expanded={allChecks} onClick={() => setAllChecks((v) => !v)}>
                {allChecks ? `Show the ${TOP_ROWS} with most values` : `Show all ${checkedEvents.length} events`}
              </Button>
            ) : null}
            <p className="mt-2 text-xs text-faint">Select an event to see what was rejected and why.</p>
          </div>
          {selected ? <EventChecks e={selected} /> : null}
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeader
          title="Cost per event"
          description={`What it costs to read each event from scratch, against a ${formatUSD(target)} budget. The most expensive event used ${pct(priciest?.fresh_cost_usd ?? 0, target)} of it. Repeat runs reuse earlier reads, so they cost close to nothing.`}
        />
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <div className="hidden grid-cols-[minmax(0,14rem)_minmax(0,1fr)_6.5rem_7rem] gap-x-4 border-b border-hairline bg-surface-sunken/50 px-5 py-2 text-xs font-medium text-muted-foreground sm:grid">
            <span>Event</span>
            <span>Cost to read from scratch</span>
            <span className="text-right">Cost</span>
            <span className="text-right">Of budget</span>
          </div>
          <BarList
            rows={costRows.map((e) => ({
                key: e.event.id,
                label: (
                  <Link href={`/events/${encodeURIComponent(e.event.id)}`} className="hover:underline">
                    {short(e.event.company)}
                  </Link>
                ),
                sub: e.people
                  ? `${eventKindAndPeriod(e.event.id) || e.event.type_label} · ${e.people} ${e.people === 1 ? "person" : "people"} · ${formatUSD(e.fresh_per_person_usd)} each`
                  : `${eventKindAndPeriod(e.event.id) || e.event.type_label} · no one to call`,
                value: e.fresh_cost_usd,
                display: formatUSD(e.fresh_cost_usd),
                aside: pct(e.fresh_cost_usd, target),
              }))}
          />
          {events.length > costRows.length || allCosts ? (
            <div className="border-t border-hairline px-4 py-2 sm:px-5">
              <Button type="button" variant="ghost" size="sm" aria-expanded={allCosts} onClick={() => setAllCosts((v) => !v)}>
                {allCosts ? "Show the most expensive events" : `Show all ${events.length} events`}
              </Button>
            </div>
          ) : null}
        </div>
      </section>

      <TokenPanel />

      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        <section className="space-y-4">
          <SectionHeader title="Where the time goes" description="Average seconds per step for one event." />
          <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
            <BarList tone="info" rows={steps.map((s) => ({ key: s.key, label: s.label, value: s.avg, display: secs(s.avg) }))} />
            <p className="border-t border-hairline px-4 py-3 text-xs text-muted-foreground sm:px-5">
              <span className="tnum font-medium text-foreground">{pct(reused, totalCalls)}</span> of the {formatCount(totalCalls)} page reads in the latest runs were reused from earlier ones.
            </p>
          </div>
        </section>

        <section className="space-y-4">
          <SectionHeader title="Latest runs" count={data.recent_runs.length} description="Most recent first. Times in IST." />
          {data.recent_runs.length ? (
            <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
              <ul className="divide-y divide-hairline lg:max-h-[372px] lg:overflow-y-auto">
                {data.recent_runs.map((r) => {
                  const ok = r.status === "ok";
                  return (
                    <li key={`${r.event_id}-${r.started_at}`} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-3 sm:px-5">
                      {ok ? <CheckCircle2 className="size-4 text-positive" aria-label="Completed" /> : <XCircle className="size-4 text-negative" aria-label="Failed" />}
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium">{short(companyOf.get(r.event_id) ?? "An event no longer listed")}</p>
                        <p className={cn("truncate text-xs", ok ? "text-muted-foreground" : "text-negative")}>
                          {ok ? istStamp(r.started_at) : (r.error ?? "The run stopped before finishing")}
                        </p>
                      </div>
                      <div className="tnum text-right text-xs">
                        <p className="font-medium text-foreground">
                          <Timer className="mr-1 inline size-3 text-faint" />
                          {secs(r.seconds)}
                        </p>
                        <p className="text-muted-foreground">{formatUSD(r.cost_usd)}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed bg-surface px-5 py-8 text-center text-sm text-muted-foreground">No runs recorded yet.</div>
          )}
        </section>
      </div>
    </div>
  );
}

function EventChecks({ e }: { e: OpsEvent }) {
  const [all, setAll] = useState(false);
  const sections = e.verification.sections.filter((s) => s.kept + s.rejected > 0);
  const rej = all ? e.rejections : e.rejections.slice(0, 4);
  return (
    <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <div className="border-b border-hairline px-4 py-3.5 sm:px-5">
        <p className="text-[15px] font-semibold">{short(e.event.company)}</p>
        <p className="tnum text-xs text-muted-foreground">
          {e.event.type_label} · {e.verification.kept} kept · {e.verification.rejected} rejected
        </p>
      </div>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-xs text-muted-foreground">
            <th className="px-4 py-2 text-left font-medium sm:px-5">Section of the filing</th>
            <th className="px-2 py-2 text-right font-medium">Kept</th>
            <th className="px-4 py-2 text-right font-medium sm:px-5">Rejected</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline border-y border-hairline">
          {sections.map((s) => (
            <tr key={s.section}>
              <td className="px-4 py-2 sm:px-5">{s.section}</td>
              <td className="tnum px-2 py-2 text-right">{s.kept}</td>
              <td className={cn("tnum px-4 py-2 text-right sm:px-5", s.rejected ? "font-medium text-negative" : "text-faint")}>{s.rejected}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-4 pt-3.5 pb-1 sm:px-5">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <ShieldX className="size-3.5" /> Rejected values
        </p>
      </div>
      {e.rejections.length ? (
        <ul className="divide-y divide-hairline">
          {rej.map((r, i) => (
            <li key={i} className="px-4 py-2.5 sm:px-5">
              <p className="truncate text-[13px] font-medium" title={r.who}>
                {r.who}
              </p>
              <p className="text-xs text-muted-foreground">
                {r.what}: <span className="tnum text-foreground/80">{r.value}</span>
              </p>
              <p className="text-xs text-negative">{r.reason}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 pb-4 text-xs text-muted-foreground sm:px-5">Nothing was rejected for this event.</p>
      )}
      {e.rejections.length > 4 ? (
        <button
          type="button"
          onClick={() => setAll((a) => !a)}
          className="w-full border-t border-hairline px-4 py-2.5 text-left text-xs font-medium text-brand-ink hover:bg-accent/60 sm:px-5"
        >
          {all ? "Show fewer" : `Show all ${e.rejections.length} rejected values`}
        </button>
      ) : null}
    </div>
  );
}

function OpsSkeleton() {
  return (
    <div className="space-y-12" role="status" aria-label="Loading Trust & Ops">
      <StatStrip>
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
      </StatStrip>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px]">
        <Skeleton className="h-[540px] rounded-xl" />
        <Skeleton className="h-[540px] rounded-xl" />
      </div>
      <SkeletonList rows={4} />
    </div>
  );
}
