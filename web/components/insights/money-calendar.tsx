"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowLeftRight, Banknote, CalendarDays, CalendarRange, ChevronLeft, ChevronRight, HandCoins, KeyRound } from "lucide-react";
import { EmptyState, ErrorState, SkeletonStat, StatCard, StatStrip } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCr, formatCrCompact, formatDate } from "@/lib/format";
import { insightsApi, useLoad, type CalendarItem } from "@/lib/insights";
import { cn } from "@/lib/utils";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type KindMeta = { icon: typeof Banknote; tone: "brand" | "caution" | "info"; short: string };
const KIND: Record<string, KindMeta> = {
  listing: { icon: Banknote, tone: "brand", short: "Listing" },
  unlock: { icon: KeyRound, tone: "caution", short: "Unlock" },
  buyback_payment: { icon: HandCoins, tone: "brand", short: "Buyback paid" },
  buyback_closing: { icon: HandCoins, tone: "info", short: "Buyback closes" },
  ofs_sale: { icon: ArrowLeftRight, tone: "brand", short: "Exchange sale" },
};
const kindMeta = (k: string): KindMeta => KIND[k] ?? { icon: CalendarDays, tone: "info", short: "Money date" };

const TONE = {
  brand: { chip: "bg-brand-soft text-brand-ink", dot: "bg-brand", icon: "bg-brand-soft text-brand-ink" },
  caution: { chip: "bg-caution-soft text-caution", dot: "bg-caution", icon: "bg-caution-soft text-caution" },
  info: { chip: "bg-info-soft text-info", dot: "bg-info", icon: "bg-info-soft text-info" },
} as const;

const monthKey = (iso: string) => iso.slice(0, 7);
const monthTitle = (key: string) => `${MONTHS[+key.slice(5, 7) - 1]} ${key.slice(0, 4)}`;
const monthShort = (key: string) => `${MONTHS[+key.slice(5, 7) - 1].slice(0, 3)} ${key.slice(0, 4)}`;
const isShares = (item: CalendarItem) => item.kind === "unlock";
/** The day's total is an estimate when any known amount in it is one. */
const isEstimate = (item: CalendarItem) =>
  isShares(item) || item.people.some((p) => p.value_cr !== null && (p.estimate || p.value_kind === "shares"));

function shortCompany(name: string) {
  return name.replace(/\b(limited|ltd\.?|private|pvt\.?)\b/gi, "").replace(/\s+/g, " ").trim();
}

/** "₹712.31 Cr" or "≈ ₹268.11 Cr"; null when no amount is known (never ₹0). */
function totalText(item: CalendarItem, compact = false) {
  const t = compact ? formatCrCompact(item.total_cr) : formatCr(item.total_cr);
  if (t === null) return null;
  return isEstimate(item) ? `≈ ${t}` : t;
}

function totalNote(item: CalendarItem) {
  if (item.people_count === 0) return "Listing day · no cash amounts known yet";
  const known = item.people_count - item.unknown_count;
  if (item.total_cr === null) return `${item.people_count} ${item.people_count === 1 ? "person" : "people"}, amounts not disclosed`;
  if (item.unknown_count > 0) return `Known for ${known} of ${item.people_count} people · ${item.unknown_count} not disclosed`;
  return `${item.people_count} ${item.people_count === 1 ? "person" : "people"}${isShares(item) ? " · value at offer price" : ""}`;
}

export function MoneyCalendar() {
  const [res, retry] = useLoad(insightsApi.calendar);
  if (res.state === "loading") return <CalendarSkeleton />;
  if (res.state === "error")
    return <ErrorState title="The calendar could not load" reason={res.reason} onRetry={retry} />;
  const { items, as_of } = res.data;
  if (items.length === 0)
    return (
      <EmptyState icon={CalendarDays} title="No money dates yet" tone="brand">
        Once an event is read, its listing day, lock-in end dates and buyback payment dates appear here with the amount due on each day.
      </EmptyState>
    );
  return <CalendarView items={items} asOf={as_of} />;
}

function CalendarView({ items, asOf }: { items: CalendarItem[]; asOf: string }) {
  const months = useMemo(() => [...new Set(items.map((i) => monthKey(i.date_iso)))].sort(), [items]);
  const [month, setMonth] = useState(() => monthKey(asOf));
  const [day, setDay] = useState<string | null>(null);

  const byDay = useMemo(() => {
    const m = new Map<string, CalendarItem[]>();
    for (const i of items) m.set(i.date_iso, [...(m.get(i.date_iso) ?? []), i]);
    return m;
  }, [items]);

  const stats = useMemo(() => {
    const upcoming = items.filter((i) => i.date_iso > asOf);
    const cash = items.filter((i) => !isShares(i));
    const unlocks = items.filter(isShares);
    const sum = (xs: CalendarItem[]) => {
      const known = xs.filter((x) => x.total_cr !== null);
      return known.length ? known.reduce((s, x) => s + (x.total_cr ?? 0), 0) : null;
    };
    return {
      events: new Set(items.map((i) => i.event.id)).size,
      next: upcoming[0] ?? null,
      cash: sum(cash),
      cashPeople: cash.reduce((s, x) => s + x.people_count, 0),
      cashUnknown: cash.reduce((s, x) => s + x.unknown_count, 0),
      unlock: sum(unlocks),
      unlockUnknown: unlocks.reduce((s, x) => s + x.unknown_count, 0),
    };
  }, [items, asOf]);

  const panelItems = day ? byDay.get(day) ?? [] : items.filter((i) => monthKey(i.date_iso) === month);
  const pick = (iso: string) => {
    setMonth(monthKey(iso));
    setDay(iso);
  };
  const goMonth = (key: string) => {
    setMonth(key);
    setDay(null);
  };

  return (
    <div className="space-y-10">
      <StatStrip>
        <StatCard label="Money dates" icon={CalendarRange} value={items.length} sub={`Across ${stats.events} events`} />
        <StatCard
          label="Next money date"
          icon={CalendarDays}
          value={stats.next ? formatDate(stats.next.date_iso) : "None ahead"}
          muted={!stats.next}
          sub={stats.next ? `${shortCompany(stats.next.event.company)} · ${stats.next.label}` : "Every dated payment is in the past"}
        />
        <StatCard
          label="Cash on these dates"
          icon={Banknote}
          value={formatCrCompact(stats.cash) ?? "Not disclosed"}
          muted={stats.cash === null}
          sub={`${stats.cashPeople} people${stats.cashUnknown ? ` · ${stats.cashUnknown} amounts not disclosed` : ""}`}
        />
        <StatCard
          label="Shares unlocking"
          icon={KeyRound}
          value={stats.unlock === null ? "Not disclosed" : `≈ ${formatCrCompact(stats.unlock)}`}
          muted={stats.unlock === null}
          sub={`Value at offer price${stats.unlockUnknown ? ` · ${stats.unlockUnknown} not valued` : ""}`}
        />
      </StatStrip>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-start">
        <MonthGrid month={month} asOf={asOf} byDay={byDay} selected={day} onPick={pick} onMonth={goMonth} months={months} />
        <aside className="min-w-0 space-y-3 lg:sticky lg:top-6" aria-live="polite">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-base font-semibold">{day ? formatDate(day) : monthTitle(month)}</h2>
            {day ? (
              <button type="button" onClick={() => setDay(null)} className="text-xs font-medium text-brand-ink hover:underline">
                Whole month
              </button>
            ) : (
              <span className="tnum text-sm text-muted-foreground">
                {panelItems.length} {panelItems.length === 1 ? "date" : "dates"}
              </span>
            )}
          </div>
          {panelItems.length ? (
            panelItems.map((i) => <DateCard key={`${i.date_iso}-${i.kind}-${i.event.id}`} item={i} />)
          ) : (
            <NoDatesThisMonth month={month} months={months} onMonth={goMonth} />
          )}
        </aside>
      </div>

      <section className="space-y-3">
        <div className="space-y-1">
          <h2 className="text-base font-semibold">Every money date</h2>
          <p className="text-sm text-muted-foreground">All listings, lock-in ends and payments across events, oldest first.</p>
        </div>
        <Timeline items={items} asOf={asOf} selected={day} onPick={pick} />
      </section>
    </div>
  );
}

function MonthGrid({
  month,
  asOf,
  byDay,
  selected,
  onPick,
  onMonth,
  months,
}: {
  month: string;
  asOf: string;
  byDay: Map<string, CalendarItem[]>;
  selected: string | null;
  onPick: (iso: string) => void;
  onMonth: (key: string) => void;
  months: string[];
}) {
  const y = +month.slice(0, 4);
  const m = +month.slice(5, 7) - 1;
  const first = new Date(Date.UTC(y, m, 1));
  const lead = (first.getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const cells: (string | null)[] = [...Array(lead).fill(null)];
  for (let d = 1; d <= days; d++) cells.push(`${month}-${String(d).padStart(2, "0")}`);
  while (cells.length % 7) cells.push(null);
  const prev = [...months].reverse().find((k) => k < month);
  const next = months.find((k) => k > month);

  return (
    <div className="min-w-0 overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-4 py-3 sm:px-5">
        <h2 className="text-base font-semibold tracking-[-0.01em]">{monthTitle(month)}</h2>
        <div className="flex items-center gap-1.5">
          <Button variant="ghost" size="sm" onClick={() => onMonth(monthKey(asOf))} disabled={month === monthKey(asOf)}>
            This month
          </Button>
          <Button variant="outline" size="icon-sm" aria-label="Previous month with money dates" disabled={!prev} onClick={() => prev && onMonth(prev)}>
            <ChevronLeft />
          </Button>
          <Button variant="outline" size="icon-sm" aria-label="Next month with money dates" disabled={!next} onClick={() => next && onMonth(next)}>
            <ChevronRight />
          </Button>
        </div>
      </div>

      <div className="flex gap-1.5 overflow-x-auto border-b border-hairline px-4 py-2.5 sm:px-5 [scrollbar-width:none]">
        {months.map((k) => {
          const n = [...byDay.entries()].filter(([iso]) => monthKey(iso) === k).reduce((s, [, v]) => s + v.length, 0);
          return (
            <button
              key={k}
              type="button"
              onClick={() => onMonth(k)}
              aria-pressed={k === month}
              className={cn(
                "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
                k === month ? "bg-foreground text-background" : "bg-surface-sunken text-muted-foreground hover:text-foreground",
              )}
            >
              {monthShort(k)}
              <span className={cn("tnum", k === month ? "opacity-70" : "text-faint")}>{n}</span>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-7 border-b border-hairline bg-surface-sunken/50 text-[11px] font-medium text-muted-foreground">
        {WEEKDAYS.map((w) => (
          <div key={w} className="px-2 py-2 text-center sm:text-left">
            <span className="sm:hidden">{w[0]}</span>
            <span className="max-sm:hidden">{w}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {cells.map((iso, idx) => {
          const list = iso ? byDay.get(iso) ?? [] : [];
          const isToday = iso === asOf;
          const past = iso !== null && iso < asOf;
          const isSel = iso !== null && iso === selected;
          const col = idx % 7;
          const base = cn(
            "relative min-h-14 border-hairline p-1.5 text-left sm:min-h-24 sm:p-2",
            col < 6 && "border-r",
            idx < cells.length - 7 && "border-b",
          );
          if (!iso) return <div key={`x${idx}`} className={cn(base, "bg-surface-sunken/40")} />;
          const dayNum = (
            <span
              className={cn(
                "tnum inline-grid size-6 place-items-center rounded-full text-xs",
                isToday ? "bg-brand font-semibold text-brand-foreground" : past ? "text-faint" : "text-foreground",
              )}
            >
              {+iso.slice(8)}
            </span>
          );
          if (!list.length)
            return (
              <div key={iso} className={base}>
                {dayNum}
              </div>
            );
          return (
            <button
              key={iso}
              type="button"
              onClick={() => onPick(iso)}
              aria-pressed={isSel}
              aria-label={`${formatDate(iso)}: ${list.map((i) => `${i.label}, ${i.event.company}`).join("; ")}`}
              className={cn(
                base,
                "flex flex-col items-start justify-start transition-colors hover:bg-accent/60 focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                isSel && "bg-brand-soft/60 hover:bg-brand-soft/80",
              )}
            >
              {dayNum}
              <span className="mt-1 flex flex-wrap gap-1 sm:hidden">
                {list.map((i) => (
                  <span key={i.kind + i.event.id} className={cn("size-1.5 rounded-full", TONE[kindMeta(i.kind).tone].dot)} />
                ))}
              </span>
              <span className="mt-1 hidden w-full flex-col gap-1 sm:flex">
                {list.slice(0, 2).map((i) => {
                  const k = kindMeta(i.kind);
                  return (
                    <span key={i.kind + i.event.id} className={cn("block rounded-md px-1.5 py-1 text-[11px] leading-tight", TONE[k.tone].chip, past && "opacity-75")}>
                      <span className="block truncate font-medium">{shortCompany(i.event.company)}</span>
                      <span className="tnum block truncate opacity-90">{totalText(i, true) ?? k.short}</span>
                    </span>
                  );
                })}
                {list.length > 2 ? <span className="text-[11px] text-muted-foreground">+{list.length - 2} more</span> : null}
              </span>
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-hairline px-4 py-2.5 text-xs text-muted-foreground sm:px-5">
        <Legend tone="brand" label="Cash paid (listing, buyback, exchange sale)" />
        <Legend tone="caution" label="Lock-in ends (shares, not cash)" />
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-grid size-4 place-items-center rounded-full bg-brand text-[9px] font-semibold text-brand-foreground">{+asOf.slice(8)}</span>
          Today
        </span>
      </div>
    </div>
  );
}

function Legend({ tone, label }: { tone: keyof typeof TONE; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-2 rounded-full", TONE[tone].dot)} />
      {label}
    </span>
  );
}

function NoDatesThisMonth({ month, months, onMonth }: { month: string; months: string[]; onMonth: (k: string) => void }) {
  const next = months.find((k) => k > month);
  const prev = [...months].reverse().find((k) => k < month);
  const target = next ?? prev;
  return (
    <div className="rounded-xl border border-dashed bg-surface px-5 py-8 text-center">
      <p className="text-sm font-medium">No money dates in {monthTitle(month)}</p>
      <p className="mt-1 text-[13px] text-muted-foreground">Nothing is listed, unlocked or paid out this month.</p>
      {target ? (
        <Button variant="outline" size="sm" className="mt-4" onClick={() => onMonth(target)}>
          {next ? "Next" : "Previous"} dates: {monthTitle(target)}
        </Button>
      ) : null}
    </div>
  );
}

function DateCard({ item }: { item: CalendarItem }) {
  const [all, setAll] = useState(false);
  const k = kindMeta(item.kind);
  const Icon = k.icon;
  const total = totalText(item);
  const people = all ? item.people : item.people.slice(0, 4);
  return (
    <article className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <div className="flex items-start gap-3 px-4 pt-4 pb-3">
        <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg", TONE[k.tone].icon)}>
          <Icon className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{item.label}</p>
          <Link href={`/events/${encodeURIComponent(item.event.id)}`} className="block truncate text-[13px] text-muted-foreground hover:text-foreground hover:underline">
            {item.event.company} · {item.event.type_label}
          </Link>
          <p className="mt-1 text-xs text-muted-foreground">
            <span className="tnum">{item.display}</span> · {item.relative} ·{" "}
            {item.confirmed ? "Confirmed date" : "From the offer timetable"}
          </p>
        </div>
      </div>
      <div className="flex items-end justify-between gap-3 border-y border-hairline bg-surface-sunken/50 px-4 py-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{isShares(item) ? "Shares unlocking" : "Cash to sellers"}</p>
          <p className={cn("tnum text-xl font-semibold tracking-[-0.01em]", total === null && "text-base font-medium text-muted-foreground")}>
            {total ?? (item.people_count === 0 ? "No amount yet" : "Amount not disclosed")}
          </p>
        </div>
        <p className="max-w-[20ch] text-right text-xs leading-snug text-muted-foreground">{totalNote(item)}</p>
      </div>
      <ul className="divide-y divide-hairline">
        {people.map((p) => (
          <li key={p.id} className="relative flex items-center justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-accent/60">
            <Link
              href={`/people/${encodeURIComponent(item.event.id)}/${encodeURIComponent(p.person_id)}`}
              className="min-w-0 truncate text-[13px] font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-inset"
            >
              {p.name}
            </Link>
            <span className={cn("tnum shrink-0 text-[13px]", p.value_cr === null ? "text-muted-foreground" : "font-medium")}>
              {p.value_cr === null ? "Not disclosed" : `${p.value_kind === "shares" || p.estimate ? "≈ " : ""}${formatCr(p.value_cr)}`}
            </span>
          </li>
        ))}
      </ul>
      {item.people.length > 4 ? (
        <button
          type="button"
          onClick={() => setAll((a) => !a)}
          className="w-full border-t border-hairline px-4 py-2.5 text-left text-xs font-medium text-brand-ink hover:bg-accent/60"
        >
          {all ? "Show fewer" : `Show all ${item.people.length} people`}
        </button>
      ) : null}
    </article>
  );
}

function Timeline({ items, asOf, selected, onPick }: { items: CalendarItem[]; asOf: string; selected: string | null; onPick: (iso: string) => void }) {
  const groups = useMemo(() => {
    const g = new Map<string, CalendarItem[]>();
    for (const i of items) g.set(monthKey(i.date_iso), [...(g.get(monthKey(i.date_iso)) ?? []), i]);
    return [...g.entries()];
  }, [items]);
  const firstAhead = items.find((i) => i.date_iso > asOf);
  return (
    <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      {groups.map(([key, list]) => (
        <div key={key}>
          {list[0] === firstAhead ? <TodayMarker asOf={asOf} /> : null}
          <div className="border-b border-hairline bg-surface-sunken/50 px-4 py-2 text-xs font-medium text-muted-foreground sm:px-5">{monthTitle(key)}</div>
          <ul className="divide-y divide-hairline border-b border-hairline last:border-b-0">
            {list.map((i) => {
              const k = kindMeta(i.kind);
              const Icon = k.icon;
              const total = totalText(i);
              const marker = i === firstAhead && list[0] !== i;
              return (
                <li key={`${i.date_iso}-${i.kind}-${i.event.id}`}>
                  {marker ? <TodayMarker asOf={asOf} /> : null}
                  <button
                    type="button"
                    onClick={() => {
                      onPick(i.date_iso);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                    className={cn(
                      "grid w-full grid-cols-[3.25rem_minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-3 text-left transition-colors hover:bg-accent/60 sm:grid-cols-[3.75rem_minmax(0,1fr)_12rem_10rem] sm:px-5",
                      selected === i.date_iso && "bg-brand-soft/40",
                      i.past && "text-muted-foreground",
                    )}
                  >
                    <span className="tnum text-[13px] leading-tight">
                      <span className={cn("block text-lg font-semibold", i.past ? "text-muted-foreground" : "text-foreground")}>{+i.date_iso.slice(8)}</span>
                      <span className="text-xs">{MONTHS[+i.date_iso.slice(5, 7) - 1].slice(0, 3)}</span>
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                        <Icon className={cn("size-3.5 shrink-0", k.tone === "caution" ? "text-caution" : "text-brand")} />
                        <span className="truncate">{i.event.company}</span>
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {i.label} · <span title={i.display}>{i.relative}</span>
                        {i.confirmed ? "" : " · from the offer timetable"}
                      </span>
                    </span>
                    <span className="hidden text-xs text-muted-foreground sm:block">
                      {i.people_count === 0 ? "Listing day" : `${i.people_count} ${i.people_count === 1 ? "person" : "people"}`}
                      {i.unknown_count ? ` · ${i.unknown_count} not disclosed` : ""}
                    </span>
                    <span className={cn("tnum text-right text-sm", total ? "font-semibold text-foreground" : "text-muted-foreground")}>
                      {total ?? (i.people_count === 0 ? "No amount yet" : "Not disclosed")}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function TodayMarker({ asOf }: { asOf: string }) {
  return (
    <div className="flex items-center gap-2 border-b border-brand/15 bg-brand-soft/60 px-4 py-1.5 text-[11px] font-medium text-brand-ink sm:px-5">
      <span className="size-1.5 rounded-full bg-brand" /> Today, {formatDate(asOf)}
    </div>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-10" role="status" aria-label="Loading the calendar">
      <StatStrip>
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
      </StatStrip>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="rounded-xl border bg-surface p-5">
          <Skeleton className="mb-5 h-5 w-40" />
          <div className="grid grid-cols-7 gap-2">
            {Array.from({ length: 35 }).map((_, i) => (
              <Skeleton key={i} className="h-14 sm:h-20" />
            ))}
          </div>
        </div>
        <div className="space-y-3">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-56 rounded-xl" />
        </div>
      </div>
    </div>
  );
}
