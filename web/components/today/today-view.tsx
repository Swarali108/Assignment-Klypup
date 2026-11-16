"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Banknote, CalendarPlus, Download, FileText, FilterX, KeyRound, PhoneCall, Search, SearchX, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, exportCsvUrl } from "@/lib/api";
import { formatCrCompact, formatDate } from "@/lib/format";
import { Can, EmptyState, ErrorState, PageHeader, SectionHeader, SkeletonList, SkeletonStat, StatCard, StatStrip } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CallItem, ConfidenceLevel, RmStatus, Summary, Tier, TodayResponse } from "@/lib/types";
import { HANDLED, notifySaved, saveRowRm } from "./quick-actions";
import { TodayRow } from "./today-row";
import { useLoad } from "./use-load";
import { coverageWords, fitsCoverage, usePrefs } from "@/lib/prefs";
import { bucketOf } from "@/lib/tier";
import { usePersistentState } from "@/lib/persist";

const TIERS: { tier: Tier; title: string; short: string; description: string }[] = [
  { tier: "cash_now", title: "Cash in hand", short: "Cash in hand", description: "Sale proceeds already paid out, or due within a month. Call these first." },
  { tier: "unlock", title: "Shares just unlocked", short: "Just unlocked", description: "Lock-in ended recently; these holdings can now be sold or pledged." },
  { tier: "holding", title: "Holds shares", short: "Holds shares", description: "Still holding after the event. Worth a relationship call." },
];

const MIN_CR = [
  { value: "0", label: "Any amount" },
  { value: "1", label: "₹1 Cr and above" },
  { value: "10", label: "₹10 Cr and above" },
  { value: "50", label: "₹50 Cr and above" },
  { value: "100", label: "₹100 Cr and above" },
];

const CONF_RANK: Record<ConfidenceLevel, number> = { high: 3, medium: 2, low: 1 };

type Filters = { q: string; type: string; tier: Tier | "all"; conf: "any" | "medium" | "high"; min: string; hideDone: boolean };
const DEFAULTS: Filters = { q: "", type: "all", tier: "all", conf: "any", min: "0", hideDone: false };

type Data = { summary: Summary; today: TodayResponse };

export function TodayView() {
  const { load, retry, setLoad } = useLoad<Data>(async () => {
    const [summary, today] = await Promise.all([api.summary(), api.today()]);
    return { summary, today };
  });
  // Remembered per browser: the tier tab, type, confidence, minimum amount and "hide logged calls" are still there tomorrow.
  const [f, setF] = usePersistentState<Filters>("aurelia.today.filters", DEFAULTS);
  const { prefs } = usePrefs();
  // The setup guide's coverage (event types, minimum ticket) is the default view; one click shows everyone.
  const hasCoverage = !!prefs && (prefs.event_types.length > 0 || !!prefs.min_ticket_cr);
  const [coverageOff, setCoverageOff] = useState(false);
  const coverageOn = hasCoverage && !coverageOff;
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setF((p) => ({ ...p, [k]: v }));

  const items = useMemo(() => (load.state === "ready" ? load.data.today.items : []), [load]);

  const types = useMemo(() => {
    // One entry per stored type; a type shown under two labels (block and bulk deals) lists both.
    const m = new Map<string, Set<string>>();
    for (const i of items) {
      for (const e of [i.event, ...(i.trades ?? []).map((t) => t.event)]) m.set(e.type, (m.get(e.type) ?? new Set()).add(e.type_label ?? e.type));
    }
    return [...m.entries()].map(([type, labels]) => [type, [...labels].sort().join(" / ")] as [string, string]);
  }, [items]);

  const filtered = useMemo(() => {
    const q = f.q.trim().toLowerCase();
    const min = Number(f.min);
    return items.filter((i) => {
      if (coverageOn && !fitsCoverage(i, prefs)) return false;
      if (f.type !== "all" && i.event.type !== f.type && !(i.trades ?? []).some((t) => t.event.type === f.type)) return false;
      if (f.conf !== "any" && CONF_RANK[i.confidence.level] < CONF_RANK[f.conf]) return false;
      // Unknown amounts never pass a minimum: null is not zero, and it is not "above" anything.
      if (min > 0) {
        const v = Math.max(i.amount.value_cr ?? -1, i.household_total_cr ?? -1, i.trades_total_cr ?? -1);
        if (v < min) return false;
      }
      if (f.hideDone && HANDLED.has(i.rm.status)) return false;
      if (q) {
        const hay = [i.person.name, i.event.company, i.person.role ?? "", i.household?.label ?? "", ...(i.members ?? []).map((m) => m.name)].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [items, f, coverageOn, prefs]);

  const counts = useMemo(() => {
    const c: Record<Tier, number> = { cash_now: 0, unlock: 0, holding: 0 };
    for (const i of filtered) c[bucketOf(i)] = (c[bucketOf(i)] ?? 0) + 1;
    return c;
  }, [filtered]);

  const active = coverageOn || f.q !== "" || f.type !== "all" || f.tier !== "all" || f.conf !== "any" || f.min !== "0" || f.hideDone;

  if (load.state === "loading") return <TodayLoading />;
  if (load.state === "error")
    return (
      <>
        <TodayHeader />
        <ErrorState title="Today's call list could not be loaded" reason={load.reason} onRetry={retry} />
      </>
    );

  const { summary, today } = load.data;
  const asOf = today.as_of;
  const open = items.filter((i) => !HANDLED.has(i.rm.status)).length;
  const handled = items.length - open;
  // Calls fold a household into one row; the summary counts people. Say both so the numbers never look like a clash.
  const cashCalls = items.filter((i) => bucketOf(i) === "cash_now").length;
  const unlockCalls = items.filter((i) => i.tier === "unlock").length;

  const patchItem = (id: string, rm: CallItem["rm"]) =>
    setLoad((prev) =>
      prev.state !== "ready"
        ? prev
        : { ...prev, data: { ...prev.data, today: { ...prev.data.today, items: prev.data.today.items.map((i) => (rowId(i) === id ? { ...i, rm } : i)) } } },
    );

  const onSave = async (item: CallItem, patch: { status: RmStatus; follow_up_date?: string }) => {
    const id = rowId(item);
    const before = item.rm;
    try {
      const next = await saveRowRm(item.event.id, item.person.id, patch);
      patchItem(id, { ...before, ...next });
      notifySaved(item.person.name, next.status, next.follow_up, async () => {
        try {
          const back = await saveRowRm(item.event.id, item.person.id, { status: before.status, follow_up_date: before.follow_up ?? "" });
          patchItem(id, { ...before, ...back });
        } catch {
          /* the toast below covers it */
        }
      });
    } catch (e) {
      const { toast } = await import("sonner");
      toast.error(e instanceof Error ? e.message : "Could not save. Try again.");
    }
  };

  return (
    <>
      <TodayHeader asOf={summary.as_of_display ?? formatDate(asOf) ?? asOf} />

      <StatStrip className="mb-8">
        <StatCard
          label="People to call"
          icon={PhoneCall}
          value={open}
          sub={handled > 0 ? `${handled} logged today · ${items.length} on the list` : `${items.length} on the list, households counted once`}
        />
        <StatCard
          label="Cash in hand"
          icon={Banknote}
          value={formatCrCompact(summary.cash_now_cr) ?? "–"}
          muted={summary.cash_now_cr === null}
          sub={summary.cash_now_people ? `Known proceeds across ${summary.cash_now_people} people${cashCalls !== summary.cash_now_people ? `, grouped into ${cashCalls} calls` : ""}` : "Known proceeds only"}
        />
        <StatCard label="Shares just unlocked" icon={KeyRound} value={unlockCalls} sub={`Lock-in ended in the last few months${summary.unlock_people != null && summary.unlock_people !== unlockCalls ? ` · ${summary.unlock_people} people, grouped into ${unlockCalls} calls` : ""}`} />
        <StatCard
          label="New events this week"
          icon={CalendarPlus}
          value={summary.new_events_this_week}
          sub={`${summary.events_processed}${summary.events_total ? ` of ${summary.events_total}` : ""} events ready to call`}
        />
      </StatStrip>

      {items.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          tone="brand"
          title="No one to call yet"
          action={
            <Button asChild variant="outline">
              <Link href="/events">See events</Link>
            </Button>
          }
        >
          When an event is processed, the people who receive money from it appear here, cash in hand first.
        </EmptyState>
      ) : (
        <>
          <FilterBar f={f} set={set} types={types} counts={counts} total={filtered.length} active={active} reset={() => { setF(DEFAULTS); setCoverageOff(true); }} coverage={coverageOn && prefs ? coverageWords(prefs.event_types, prefs.min_ticket_cr) : null} clearCoverage={() => setCoverageOff(true)} />

          {filtered.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title="No one matches these filters"
              action={
                <Button variant="outline" onClick={() => { setF(DEFAULTS); setCoverageOff(true); }}>
                  <FilterX /> Clear filters
                </Button>
              }
            >
              {f.min !== "0" ? "People whose amount is not disclosed are left out when a minimum amount is set." : "Try a different name, or clear the filters."}
            </EmptyState>
          ) : (
            <div className="space-y-10">
              {TIERS.filter((t) => f.tier === "all" || f.tier === t.tier).map((t) => {
                const rows = filtered.filter((i) => bucketOf(i) === t.tier);
                if (!rows.length) return null;
                return (
                  <section key={t.tier} className="space-y-3" aria-labelledby={`tier-${t.tier}`}>
                    <SectionHeader
                      title={<span id={`tier-${t.tier}`}>{t.title}</span>}
                      description={t.description}
                      count={rows.length}
                    />
                    <ol className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
                      {rows.map((r) => (
                        <TodayRow key={rowId(r)} item={r} position={items.indexOf(r) + 1} asOf={asOf} onSave={onSave} />
                      ))}
                    </ol>
                  </section>
                );
              })}
            </div>
          )}
        </>
      )}
    </>
  );
}

function rowId(i: CallItem) {
  return i.id ?? `${i.event.id}/${i.person.id}`;
}

function TodayHeader({ asOf }: { asOf?: string }) {
  return (
    <PageHeader
      title="Today"
      description={asOf ? `Who to call on ${asOf}, most actionable money first.` : "Who to call today, most actionable money first."}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="lg" className="bg-surface shadow-(--shadow-card)">
            <Link href="/weekly?print=1">
              <FileText /> Download weekly short list (PDF)
            </Link>
          </Button>
        <Can permission="export">
          <Button asChild variant="outline" size="lg" className="bg-surface shadow-(--shadow-card)">
            <a href={exportCsvUrl()} download="aurelia-calls.csv">
              <Download /> Export for CRM
            </a>
          </Button>
        </Can>
        </div>
      }
    />
  );
}

function FilterBar({
  f,
  set,
  types,
  counts,
  total,
  active,
  reset,
  coverage,
  clearCoverage,
}: {
  f: Filters;
  set: <K extends keyof Filters>(k: K, v: Filters[K]) => void;
  types: [string, string][];
  counts: Record<Tier, number>;
  total: number;
  active: boolean;
  reset: () => void;
  coverage: string | null;
  clearCoverage: () => void;
}) {
  const tabs: { value: Tier | "all"; label: string; n: number }[] = [
    { value: "all", label: "All", n: total },
    ...TIERS.map((t) => ({ value: t.tier, label: t.short, n: counts[t.tier] })),
  ];
  return (
    <div className="mb-8 space-y-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="tablist" aria-label="Call tier" className="-mx-1 flex max-w-[calc(100%+0.5rem)] min-w-0 gap-1 overflow-x-auto px-1 pb-0.5">
          {tabs.map((t) => {
            const on = f.tier === t.value;
            return (
              <button
                key={t.value}
                role="tab"
                type="button"
                aria-selected={on}
                onClick={() => set("tier", t.value)}
                className={cn(
                  "inline-flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors",
                  on ? "bg-primary text-primary-foreground shadow-(--shadow-card)" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {t.label}
                <span className={cn("tnum rounded-md px-1.5 text-xs", on ? "bg-primary-foreground/15" : "bg-secondary text-muted-foreground")}>{t.n}</span>
              </button>
            );
          })}
        </div>
        <label className="relative block lg:w-80">
          <span className="sr-only">Search the call list</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={f.q}
            onChange={(e) => set("q", e.target.value)}
            placeholder="Search name, company or household"
            className="h-9 w-full rounded-lg border bg-surface pr-3 pl-9 text-sm shadow-(--shadow-card) placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {coverage ? (
          <span className="inline-flex h-9 items-center gap-2 rounded-lg border border-brand/30 bg-brand-soft px-3 text-sm text-brand-ink">
            Matched to your coverage: {coverage}
            <button type="button" onClick={clearCoverage} className="font-medium underline-offset-2 hover:underline">
              Show everyone
            </button>
          </span>
        ) : null}
        <Select value={f.type} onValueChange={(v) => set("type", v)}>
          <SelectTrigger className="h-9 min-w-40 bg-surface" aria-label="Event type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All event types</SelectItem>
            {types.map(([v, l]) => (
              <SelectItem key={v} value={v}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={f.conf} onValueChange={(v) => set("conf", v as Filters["conf"])}>
          <SelectTrigger className="h-9 min-w-44 bg-surface" aria-label="Confidence">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any confidence</SelectItem>
            <SelectItem value="medium">Medium or high</SelectItem>
            <SelectItem value="high">High confidence only</SelectItem>
          </SelectContent>
        </Select>
        <Select value={f.min} onValueChange={(v) => set("min", v)}>
          <SelectTrigger className="h-9 min-w-40 bg-surface" aria-label="Minimum amount">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MIN_CR.map((m) => (
              <SelectItem key={m.value} value={m.value}>
                {m.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <button
          type="button"
          role="switch"
          aria-checked={f.hideDone}
          onClick={() => set("hideDone", !f.hideDone)}
          className="inline-flex h-9 items-center gap-2 rounded-lg border bg-surface px-3 text-sm text-foreground transition-colors hover:bg-accent"
        >
          <span className={cn("relative h-4 w-7 rounded-full transition-colors", f.hideDone ? "bg-brand" : "bg-border")}>
            <span className={cn("absolute top-0.5 left-0.5 size-3 rounded-full bg-surface shadow-sm transition-transform", f.hideDone && "translate-x-3")} />
          </span>
          Hide logged calls
        </button>
        {active ? (
          <Button variant="ghost" onClick={reset} className="h-9 text-muted-foreground">
            <FilterX /> Clear
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function TodayLoading() {
  return (
    <div role="status" aria-label="Loading today's call list">
      <TodayHeader />
      <StatStrip className="mb-8">
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
      </StatStrip>
      <div className="mb-8 h-[84px]" />
      <div className="space-y-3">
        <div className="h-10" />
        <SkeletonList rows={6} />
      </div>
    </div>
  );
}
