"use client";

import { useSession } from "@/lib/session";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, ChevronDown, ExternalLink, Play, Radar, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { EventSummary } from "@/lib/types";
import type { FeedItem, FeedResponse } from "./types";
import { displayStatus, StatusChip, type DisplayStatus } from "./status";
import { SourceBadge } from "@/components/sources/source-badge";

type GroupKey = keyof FeedResponse["groups"];
const GROUPS: { key: GroupKey; label: string; empty: string }[] = [
  { key: "today", label: "Today", empty: "No new filings yet today. New ones appear here as soon as they are published." },
  { key: "upcoming", label: "Upcoming", empty: "No filings with money dates ahead of us." },
  { key: "recent", label: "Recent", empty: "No filings in the last 30 days." },
];

/** Feed status → the RM's view. When the filing is already an event, the event's own status wins. */
function itemStatus(item: FeedItem, event: EventSummary | undefined): DisplayStatus {
  if (event) return displayStatus(event);
  switch (item.status) {
    case "ready":
      return "ready";
    case "empty":
      return "empty";
    case "scanned":
      return "scanned";
    case "failed":
      return "failed";
    case "waiting":
    case "needs_approval":
      return "not_processed";
    case "watch":
      return "not_processed";
    default:
      return "not_supported";
  }
}

function itemReason(item: FeedItem, event: EventSummary | undefined, status: DisplayStatus): string {
  if (event && status === "ready") return `${event.people_count} to call`;
  if (event && status === "empty") return "Read in full; no individual gets money";
  if (item.status === "watch") return item.reason;
  if (status === "not_supported") return item.kind_label;
  return item.reason;
}

function FeedRow({ item, event }: { item: FeedItem; event?: EventSummary }) {
  const status = itemStatus(item, event);
  const muted = status === "not_supported";
  // Signals v2: a watchlist item ("IPO coming") and an over-cap item carry their own label.
  const chipLabel = item.status === "watch" || item.status === "needs_approval" ? item.status_label : undefined;
  const href = item.event_id ? `/events/${encodeURIComponent(item.event_id)}` : null;
  const { can } = useSession();
  const canProcess = can("process") && !!item.event_id && status === "not_processed";
  const day = item.published_display.split(" ");
  return (
    <li className={cn("relative flex gap-3.5 px-4 py-3.5 transition-colors hover:bg-accent/50 sm:px-5", muted && "opacity-75")}>
      <div className="tnum w-9 shrink-0 pt-0.5 text-center leading-none" aria-label={item.published_display}>
        <div className="text-[15px] font-semibold text-foreground">{day[0]}</div>
        <div className="mt-1 text-[11px] text-muted-foreground uppercase">{day[1]}</div>
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{event?.company ?? item.company}</p>
        <p className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
          <SourceBadge owner={item.source_badge} />
          <span className="truncate">{item.kind_label}</span>
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <StatusChip status={status} label={chipLabel} className="h-5 px-1.5 text-[11px]" />
          <span className="min-w-0 text-xs leading-snug text-muted-foreground">
            {itemReason(item, event, status)}
            {item.money_date_display ? <span className="tnum"> · money date {item.money_date_display}</span> : null}
          </span>
        </div>
      </div>
      <div className="flex shrink-0 items-start pt-0.5">
        {canProcess && href ? (
          <Button asChild size="sm" variant="outline">
            <Link href={`${href}?process=1`}>
              <Play /> Process now
            </Link>
          </Button>
        ) : href ? (
          <Button asChild size="icon-sm" variant="ghost" aria-label={status === "ready" ? `Open call list for ${item.company}` : `See why for ${item.company}`}>
            <Link href={href}>
              <ArrowRight />
            </Link>
          </Button>
        ) : (
          <Button asChild size="icon-sm" variant="ghost" aria-label={`Open the filing for ${item.company} (opens a new tab)`}>
            <a href={item.link} target="_blank" rel="noreferrer">
              <ExternalLink />
            </a>
          </Button>
        )}
      </div>
    </li>
  );
}

/** New filings watched on public sources, grouped Today / Upcoming / Recent. */
export function FeedPanel({ feed, events, initialGroup }: { feed: FeedResponse; events: EventSummary[]; initialGroup?: string }) {
  const byId = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);
  const firstNonEmpty = GROUPS.find((g) => feed.groups[g.key]?.length)?.key ?? "today";
  const [group, setGroup] = useState<GroupKey>(GROUPS.some((g) => g.key === initialGroup) ? (initialGroup as GroupKey) : firstNonEmpty);
  const [showAll, setShowAll] = useState(false);
  const [showWatch, setShowWatch] = useState(false);
  const items = feed.groups[group] ?? [];
  const supported = items.filter((i) => (i.event_id || i.status !== "unsupported") && i.status !== "watch");
  const watch = items.filter((i) => i.status === "watch");
  const unsupported = items.filter((i) => !i.event_id && i.status === "unsupported");
  const checked = new Date(feed.refreshed_at);
  const checkedLabel = Number.isNaN(checked.getTime())
    ? null
    : checked.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });

  return (
    <section aria-labelledby="feed-title" className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <header className="border-b border-hairline px-4 pt-4 sm:px-5">
        <div className="flex items-center justify-between gap-3">
          <h2 id="feed-title" className="flex items-center gap-2 text-base font-semibold">
            <Radar className="size-4 text-brand" aria-hidden />
            New filings
          </h2>
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="relative flex size-2" aria-hidden>
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-positive/50 motion-reduce:animate-none" />
              <span className="relative inline-flex size-2 rounded-full bg-positive" />
            </span>
            Watching {feed.sources_ok.length} sources
          </span>
        </div>
        <div role="tablist" aria-label="Filings by date" className="-mb-px mt-3 flex gap-5">
          {GROUPS.map((g) => {
            const n = feed.groups[g.key]?.length ?? 0;
            const active = g.key === group;
            return (
              <button
                key={g.key}
                role="tab"
                type="button"
                aria-selected={active}
                onClick={() => {
                  setGroup(g.key);
                  setShowAll(false);
                }}
                className={cn(
                  "inline-flex h-9 items-center gap-1.5 border-b-2 border-transparent text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground",
                  active && "border-brand text-foreground",
                )}
              >
                {g.label}
                <span className={cn("tnum rounded px-1 text-[11px]", active ? "bg-brand-soft text-brand-ink" : "bg-secondary text-muted-foreground")}>{n}</span>
              </button>
            );
          })}
        </div>
      </header>

      {items.length === 0 ? (
        <div className="px-6 py-10 text-center">
          <p className="text-sm font-medium text-foreground">Nothing here yet</p>
          <p className="mx-auto mt-1 max-w-[34ch] text-[13px] leading-relaxed text-muted-foreground">{GROUPS.find((g) => g.key === group)?.empty}</p>
        </div>
      ) : (
        <ul role="tabpanel" className="divide-y divide-hairline xl:max-h-[calc(100dvh-16rem)] xl:overflow-y-auto">
          {supported.map((i) => (
            <FeedRow key={i.id} item={i} event={i.event_id ? byId.get(i.event_id) : undefined} />
          ))}
          {watch.length ? (
            <li>
              <button
                type="button"
                aria-expanded={showWatch}
                onClick={() => setShowWatch((s) => !s)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground sm:px-5"
              >
                <span>
                  <span className="tnum">{watch.length}</span> to watch: IPOs coming (draft offers filed) and acquisition notices
                </span>
                <ChevronDown className={cn("size-3.5 shrink-0 transition-transform duration-200", showWatch && "rotate-180")} />
              </button>
              {showWatch ? (
                <ul className="divide-y divide-hairline border-t border-hairline bg-surface-sunken/50">
                  {watch.map((i) => (
                    <FeedRow key={i.id} item={i} />
                  ))}
                </ul>
              ) : null}
            </li>
          ) : null}
          {unsupported.length ? (
            <li>
              <button
                type="button"
                aria-expanded={showAll}
                onClick={() => setShowAll((s) => !s)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground sm:px-5"
              >
                <span>
                  <span className="tnum">{unsupported.length}</span> filings we spotted but don&apos;t read yet (takeover offers and similar)
                </span>
                <ChevronDown className={cn("size-3.5 shrink-0 transition-transform duration-200", showAll && "rotate-180")} />
              </button>
              {showAll ? (
                <ul className="divide-y divide-hairline border-t border-hairline bg-surface-sunken/50">
                  {unsupported.map((i) => (
                    <FeedRow key={i.id} item={i} />
                  ))}
                </ul>
              ) : null}
            </li>
          ) : null}
        </ul>
      )}

      <footer className="flex items-center gap-2 border-t border-hairline bg-surface-sunken/50 px-4 py-2.5 text-xs text-muted-foreground sm:px-5">
        {feed.sources_with_problems.length ? (
          <span className="inline-flex items-center gap-1.5 text-caution">
            <TriangleAlert className="size-3.5" /> {feed.sources_with_problems.length} source could not be checked
          </span>
        ) : (
          <span>All sources checked</span>
        )}
        {checkedLabel ? <span className="tnum ml-auto">Last checked {checkedLabel}</span> : null}
      </footer>
    </section>
  );
}
