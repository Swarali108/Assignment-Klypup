"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { briefApi, type Since } from "@/lib/brief";
import { dayLabel, marketStatus } from "@/lib/market";
import { cn } from "@/lib/utils";

/**
 * Above the home greeting: "Monday, 16 November · Markets open · closes 15:30 IST (regular hours)" and, when there is
 * an earlier visit on record, a chip with what is new since then. The clock only starts after mount so the server
 * and the browser never disagree.
 */
export function DateLine() {
  const [now, setNow] = useState<Date | null>(null);
  const [since, setSince] = useState<Since | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setNow(new Date()), 0);
    const tick = setInterval(() => setNow(new Date()), 60_000);
    briefApi
      .since()
      .then(setSince)
      .catch(() => {});
    return () => {
      clearTimeout(t);
      clearInterval(tick);
    };
  }, []);

  if (!now) return <div className="mb-3 h-5" aria-hidden />;
  const market = marketStatus(now);
  const fresh = since && since.new_events + since.new_people > 0;
  const lead = since?.since_known ? "Since your last visit" : "In the last 7 days";
  return (
    <div className="mb-4 flex flex-col items-center gap-2">
      <p className="tnum text-[13px] text-muted-foreground">
        {dayLabel(now)} <span aria-hidden>·</span>{" "}
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("size-1.5 rounded-full", market.open ? "bg-positive" : "bg-faint")} aria-hidden />
          <span className={market.open ? "text-foreground" : undefined}>{market.label}</span>
        </span>{" "}
        <span className="text-faint">(regular hours)</span>
      </p>
      {since ? (
        <Link
          href="/events"
          className="tnum inline-flex items-center gap-1.5 rounded-full border bg-surface px-3 py-1 text-xs text-foreground/85 shadow-(--shadow-card) transition-colors hover:border-brand/35 hover:bg-brand-soft/50"
        >
          {fresh ? (
            <>
              {lead}: <span className="font-medium">{since.new_events} new {since.new_events === 1 ? "event" : "events"}</span> ·{" "}
              <span className="font-medium">{since.new_people} new {since.new_people === 1 ? "person" : "people"}</span>
            </>
          ) : (
            <>{lead}: nothing new</>
          )}
        </Link>
      ) : null}
    </div>
  );
}
