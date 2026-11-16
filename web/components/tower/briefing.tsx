"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Download, Newspaper, RotateCw } from "lucide-react";
import { useBrief } from "@/components/brief/brief-provider";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { coverageWords, fitsCoverage, usePrefs } from "@/lib/prefs";
import { Avatar, InBookBadge, Money, personHref } from "@/components/ds";
import type { CallItem, EventSummary } from "@/lib/types";

type Data = { asOf: string; calls: CallItem[]; filtered: boolean; fresh: EventSummary[]; closed: EventSummary[]; found: number | null };

/** A quiet strip under the prompt: the top 3 calls (matched to the RM's coverage) and this week's new events. */
export function Briefing() {
  const { prefs } = usePrefs();
  const { openBrief } = useBrief();
  const [data, setData] = useState<Data | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    Promise.all([api.today(), api.events(), api.summary().catch(() => null)])
      .then(([today, events, summary]) => {
        if (!live) return;
        const matched = today.items.filter((i) => fitsCoverage(i, prefs));
        const filtered = !!prefs && (prefs.event_types.length > 0 || !!prefs.min_ticket_cr);
        const weekAgo = new Date(new Date(today.as_of).getTime() - 7 * 864e5).toISOString().slice(0, 10);
        const thisWeek = events.events.filter(
          (e) => e.status === "ready" && e.money_date?.date_iso && e.money_date.date_iso >= weekAgo && e.money_date.date_iso <= today.as_of,
        );
        // "Paid out" only for an event with a dated payment and named people to call; a buyback that merely closed is said so.
        const fresh = thisWeek.filter((e) => e.money_date?.kind !== "buyback_closing" && e.people_count > 0).slice(0, 3);
        const closed = thisWeek.filter((e) => e.money_date?.kind === "buyback_closing").slice(0, 3);
        setData({ asOf: today.as_of, closed, calls: (matched.length ? matched : today.items).slice(0, 3), filtered: filtered && matched.length > 0, fresh, found: summary?.new_events_this_week ?? null });
        setFailed(false);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [prefs, attempt]);

  if (failed) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed px-4 py-3 text-[13px] text-muted-foreground">
        Today’s briefing could not be loaded.
        <button type="button" onClick={() => setAttempt((a) => a + 1)} className="inline-flex items-center gap-1 font-medium text-brand-ink hover:underline">
          <RotateCw className="size-3.5" aria-hidden /> Retry
        </button>
      </div>
    );
  }

  return (
    <section aria-labelledby="briefing-title" className="rounded-2xl border bg-surface-sunken/60 p-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-3.5 pt-2 pb-2.5">
        <h2 id="briefing-title" className="text-[13px] font-semibold text-foreground">
          Today’s briefing
          {data ? <span className="tnum ml-2 font-normal text-muted-foreground">{formatDate(data.asOf)}</span> : null}
        </h2>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <button type="button" onClick={openBrief} className="inline-flex items-center gap-1 font-medium text-brand-ink hover:underline">
            <Newspaper className="size-3.5" aria-hidden /> Today’s brief
          </button>
          <Link href="/weekly?print=1" className="inline-flex items-center gap-1 font-medium text-brand-ink hover:underline">
            <Download className="size-3.5" aria-hidden /> Weekly short list (PDF)
          </Link>
          {data?.filtered && prefs ? (
            <span className="text-muted-foreground">Matched to your coverage: {coverageWords(prefs.event_types, prefs.min_ticket_cr)}</span>
          ) : (
            <Link href="/today" className="inline-flex items-center gap-1 font-medium text-brand-ink hover:underline">
              Full call list <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          )}
        </div>
      </div>
      <ol className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
        {data
          ? data.calls.map((item, i) => (
              <li key={item.id ?? i} className="relative grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-accent/50">
                <Avatar name={item.person.name} size="sm" />
                <div className="min-w-0">
                  <div className="flex min-w-0 items-center gap-2">
                    <Link
                      href={personHref(item)}
                      className="truncate text-[13px] font-semibold text-foreground after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring"
                    >
                      {item.person.name}
                    </Link>
                    {item.in_book ? <InBookBadge /> : null}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {item.event.company} · {item.tier_label}
                  </p>
                </div>
                <span data-tour={i === 0 ? "evidence-amount" : undefined}>
                  <Money amount={item.amount} size="sm" align="end" />
                </span>
              </li>
            ))
          : [0, 1, 2].map((i) => (
              <li key={i} className="flex items-center gap-3 px-4 py-3" aria-hidden>
                <span className="size-8 animate-pulse rounded-full bg-secondary" />
                <span className="h-3 flex-1 animate-pulse rounded bg-secondary" />
                <span className="h-3 w-16 animate-pulse rounded bg-secondary" />
              </li>
            ))}
      </ol>
      {data ? (
        <p className="px-3.5 pt-2.5 pb-1.5 text-xs text-muted-foreground">
          {data.found !== null ? (
            <Link href="/events" className="font-medium text-foreground hover:underline">
              {data.found} new {data.found === 1 ? "event" : "events"} found this week
            </Link>
          ) : null}
          {data.found !== null ? " · " : null}
          {data.fresh.length ? (
            <>
              Money paid out this week: <EventLinks events={data.fresh} />
            </>
          ) : (
            "No new payouts dated this week."
          )}
          {data.closed.length ? (
            <>
              {" · "}Buyback closed this week: <EventLinks events={data.closed} />
            </>
          ) : null}
        </p>
      ) : null}
    </section>
  );
}

function EventLinks({ events }: { events: EventSummary[] }) {
  return (
    <>
      {events.map((e, i) => (
        <span key={e.id}>
          {i > 0 ? ", " : ""}
          <Link href={`/events/${encodeURIComponent(e.id)}`} className="hover:text-foreground hover:underline">
            {e.company}
          </Link>
        </span>
      ))}
    </>
  );
}
