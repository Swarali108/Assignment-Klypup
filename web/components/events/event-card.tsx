import Link from "next/link";
import { ArrowUpRight, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCrCompact } from "@/lib/format";
import type { EventSummary } from "@/lib/types";
import { EVENT_KIND_LABEL } from "./api";
import { displayStatus, StatusChip } from "./status";

const TIER_DOT = { cash_now: "bg-brand", unlock: "bg-caution", holding: "bg-faint" } as const;
const TIER_WORD = { cash_now: "cash in hand", unlock: "just unlocked", holding: "holding" } as const;

/** One processed event: who to call and how much, or the plain reason there is no one. */
export function EventCard({ event }: { event: EventSummary }) {
  const status = displayStatus(event);
  const kind = event.type_label ?? EVENT_KIND_LABEL[event.type] ?? event.type;
  const md = event.money_date;
  const when = md?.date_iso ? `${md.label} ${md.display}` : null;
  const tiers = (["cash_now", "unlock", "holding"] as const).filter((t) => (event.tier_counts?.[t] ?? 0) > 0);
  const total = event.people_count || 1;
  const docs = event.docs ?? [];
  const pages = docs.reduce((n, d) => n + (d.pages ?? 0), 0);

  return (
    <Link
      href={`/events/${encodeURIComponent(event.id)}`}
      className="group relative flex min-h-[13.5rem] flex-col rounded-xl border bg-surface p-5 shadow-(--shadow-card) transition-[border-color,box-shadow] duration-200 hover:border-input hover:shadow-(--shadow-raised) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug text-foreground text-balance">{event.company}</h3>
          <p className="tnum mt-1 text-[13px] text-muted-foreground">
            {kind}
            {when ? <span> · {when}</span> : null}
          </p>
        </div>
        <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-faint transition-colors group-hover:text-foreground" aria-hidden />
      </div>

      {status === "ready" ? (
        <div className="mt-auto pt-6">
          <dl className="grid grid-cols-2 gap-4">
            <div>
              <dt className="text-xs text-muted-foreground">People to call</dt>
              <dd className="tnum mt-1 text-[1.375rem] font-semibold leading-none tracking-[-0.01em]">{event.people_count}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Cash in hand</dt>
              <dd
                className={cn(
                  "tnum mt-1 text-[1.375rem] font-semibold leading-none tracking-[-0.01em]",
                  event.cash_cr === null && "text-base font-medium text-muted-foreground",
                )}
              >
                {formatCrCompact(event.cash_cr) ?? (event.tier_counts?.cash_now ? "Not disclosed" : "None yet")}
              </dd>
            </div>
          </dl>
          <div className="mt-4 flex h-1.5 overflow-hidden rounded-full bg-secondary" aria-hidden>
            {tiers.map((t) => (
              <span key={t} className={cn("h-full", TIER_DOT[t])} style={{ width: `${((event.tier_counts?.[t] ?? 0) / total) * 100}%` }} />
            ))}
          </div>
          <p className="tnum mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {tiers.map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5">
                <span className={cn("size-1.5 rounded-full", TIER_DOT[t])} aria-hidden />
                {event.tier_counts?.[t]} {TIER_WORD[t]}
              </span>
            ))}
          </p>
        </div>
      ) : (
        <div className="mt-auto pt-6">
          <StatusChip status={status} />
          <p className="mt-2.5 line-clamp-3 text-[13px] leading-snug text-muted-foreground">
            {event.empty_reason ?? event.status_reason ?? "Waiting to be read."}
          </p>
        </div>
      )}

      <div className="tnum mt-4 flex items-center gap-1.5 border-t border-hairline pt-3 text-xs text-faint">
        <FileText className="size-3.5" aria-hidden />
        {docs.length === 1 ? (docs[0].label ?? "1 filing") : `${docs.length} filings`}
        {pages ? <span>· {pages.toLocaleString("en-IN")} pages</span> : null}
        {status === "ready" ? <StatusChip status="ready" className="ml-auto h-5 px-1.5 text-[11px]" label="Ready" /> : null}
      </div>
    </Link>
  );
}
