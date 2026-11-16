"use client";

import { useMemo } from "react";
import { usePersistentState } from "@/lib/persist";
import { Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/ds";
import type { EventSummary } from "@/lib/types";
import { EventCard } from "./event-card";
import { displayStatus } from "./status";

type Filter = "all" | "calls" | "empty" | "attention";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "calls", label: "With calls" },
  { key: "empty", label: "No one to call" },
  { key: "attention", label: "Needs attention" },
];

function bucket(e: EventSummary): Exclude<Filter, "all"> {
  const s = displayStatus(e);
  if (s === "ready" || s === "processing") return "calls";
  if (s === "empty") return "empty";
  return "attention";
}

/** Order: events with calls (largest known cash first), then no-one-to-call, then ones needing attention. */
function order(events: EventSummary[]): EventSummary[] {
  const rank = { calls: 0, empty: 1, attention: 2 } as const;
  return [...events].sort(
    (a, b) =>
      rank[bucket(a)] - rank[bucket(b)] ||
      (b.cash_cr ?? -1) - (a.cash_cr ?? -1) ||
      b.people_count - a.people_count ||
      a.company.localeCompare(b.company),
  );
}

export function EventsGrid({ events }: { events: EventSummary[] }) {
  const [filter, setFilter] = usePersistentState<Filter>("aurelia.events.tab", "all");
  const sorted = useMemo(() => order(events), [events]);
  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: events.length, calls: 0, empty: 0, attention: 0 };
    for (const e of events) c[bucket(e)]++;
    return c;
  }, [events]);
  const shown = filter === "all" ? sorted : sorted.filter((e) => bucket(e) === filter);

  return (
    <div>
      <div role="group" aria-label="Filter events" className="mb-4 flex gap-1 overflow-x-auto rounded-lg border bg-surface p-1 shadow-(--shadow-card) sm:w-fit">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={cn(
              "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground",
              filter === f.key && "bg-secondary text-foreground",
            )}
          >
            {f.label}
            <span className="tnum text-xs font-normal text-faint">{counts[f.key]}</span>
          </button>
        ))}
      </div>
      {shown.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-2 2xl:grid-cols-3">
          {shown.map((e) => (
            <EventCard key={e.id} event={e} />
          ))}
        </div>
      ) : (
        <EmptyState icon={Layers} title="Nothing in this view">
          {filter === "attention" ? "Every event was read without problems." : "No events match this filter yet."}
        </EmptyState>
      )}
    </div>
  );
}
