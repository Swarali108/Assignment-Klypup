"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown, Repeat, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCr } from "@/lib/format";
import { Avatar, Can, ConfidenceBadge, Money, personHref, TimingPill } from "@/components/ds";
import { RM_STATUS_LABEL } from "@/components/ds/rm-status-control";
import { MemberRow } from "@/components/ds/person-row";
import { InBookBadge } from "@/components/ds/in-book-badge";
import { AssignControl } from "@/components/team/assign-control";
import type { CallItem, RmStatus, TradeRef } from "@/lib/types";
import { HANDLED, QuickActions, type RowRm } from "./quick-actions";
import { rmConfidence, rmText, rmTiming } from "./use-load";

const ENTITY = /\b(trust|fund|llp|limited|ltd|huf|private|company|holdings|partners|mauritius)\b/i;

/** One slot in the Today queue: who, why, how sure, when, how much, and the quick call log. */
export function TodayRow({
  item,
  position,
  asOf,
  onSave,
}: {
  item: CallItem;
  position: number;
  asOf: string;
  onSave: (item: CallItem, patch: { status: RmStatus; follow_up_date?: string }) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [openTrades, setOpenTrades] = useState(false);
  const members = item.members ?? [];
  const trades = item.trades ?? [];
  const rm = item.rm as RowRm;
  const handled = HANDLED.has(rm.status);
  const entity = item.person.holder_type !== "person" || ENTITY.test(item.person.name);
  const sub = [item.person.kind_label, item.person.role, `${item.event.company} · ${item.sources && item.sources.length > 1 ? item.sources.join(" + ") : (item.event.type_label ?? item.event.type)}`].filter(Boolean).join(" · ");

  return (
    <li className={cn("group/row relative list-none", handled && "bg-surface-sunken/50")}>
      <div
        className={cn(
          "grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-4 gap-y-3 px-4 py-4 transition-colors hover:bg-accent/50 sm:px-5",
          "lg:grid-cols-[auto_minmax(0,1fr)_14rem_9rem_auto] lg:items-center",
        )}
      >
        <div className="flex items-center gap-3">
          <span className="tnum hidden w-6 text-right text-xs text-faint sm:block">{position}</span>
          <Avatar name={item.person.name} entity={entity} className={cn(handled && "opacity-60")} />
        </div>

        <div className={cn("min-w-0", handled && "opacity-60")}>
          <div className="flex min-w-0 items-center gap-2">
            <Link
              href={personHref(item)}
              className="truncate text-[15px] font-semibold text-foreground after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
            >
              {item.person.name}
            </Link>
            {item.in_book ? <InBookBadge /> : null}
          </div>
          <p className="truncate text-[13px] text-muted-foreground">{sub}</p>
          <AssignControl eventId={item.event.id} personId={item.person.id} compact className="mt-1.5" />
          <p className="mt-1.5 line-clamp-2 max-w-[68ch] text-[13px] leading-snug text-foreground/80">{rmText(item.why)}</p>
          <div className="mt-2.5 flex flex-col items-start gap-2 lg:hidden">
            <TimingPill timing={rmTiming(item.timing)} asOf={asOf} />
            <ConfidenceBadge confidence={rmConfidence(item.confidence)} />
          </div>
          {members.length > 0 ? (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              className="relative z-10 mt-2.5 rounded-md text-left text-xs leading-relaxed font-medium text-brand-ink hover:underline"
            >
              <Users className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden />
              {item.household?.label ?? "Household"} · {members.length + 1} people
              {item.household_total_cr ? <span className="tnum font-normal text-muted-foreground"> · {formatCr(item.household_total_cr)} together</span> : null}
              <ChevronDown className={cn("ml-1 inline size-3.5 align-[-2px] transition-transform duration-200 motion-reduce:transition-none", open && "rotate-180")} aria-hidden />
            </button>
          ) : null}
          {trades.length > 1 ? (
            <button
              type="button"
              onClick={() => setOpenTrades((o) => !o)}
              aria-expanded={openTrades}
              className="relative z-10 mt-2.5 block rounded-md text-left text-xs leading-relaxed font-medium text-brand-ink hover:underline"
            >
              <Repeat className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden />
              Sold {trades.length} times at {item.event.company}
              {item.trades_total_display ? (
                <span className="tnum font-normal text-muted-foreground">
                  {" "}· {item.trades_total_display} together{item.trades_unpriced ? ` (${item.trades_unpriced} without an amount)` : ""}
                </span>
              ) : null}
              <ChevronDown className={cn("ml-1 inline size-3.5 align-[-2px] transition-transform duration-200 motion-reduce:transition-none", openTrades && "rotate-180")} aria-hidden />
            </button>
          ) : null}
        </div>

        <div className={cn("hidden min-w-0 space-y-2 lg:block", handled && "opacity-60")}>
          <span className="line-clamp-2" title={item.timing.label}>
            <TimingPill timing={rmTiming(item.timing)} asOf={asOf} />
          </span>
          <ConfidenceBadge confidence={rmConfidence(item.confidence)} />
        </div>

        <div className={cn("col-start-2 lg:col-start-auto lg:justify-self-end", handled && "opacity-60")}>
          <Money amount={item.amount} align="end-lg" size="md" showKind />
        </div>

        <div className="relative z-10 col-start-2 lg:col-start-auto lg:flex lg:justify-end lg:max-[1359px]:w-[7.5rem] min-[1360px]:w-[17.5rem]">
          <Can
            permission="edit_rm"
            fallback={
              handled ? (
                <span className="inline-flex h-8 items-center whitespace-nowrap rounded-lg bg-positive-soft px-2.5 text-[13px] font-medium text-positive">
                  {RM_STATUS_LABEL[rm.status]}
                </span>
              ) : null
            }
          >
            <QuickActions name={item.person.name} rm={rm} asOf={asOf} onSave={(p) => onSave(item, p)} className="w-full lg:w-auto" />
          </Can>
        </div>
      </div>
      {open && members.length > 0 ? (
        <div className="divide-y divide-hairline border-t border-hairline bg-surface-sunken/60">
          {members.map((m) => (
            <MemberRow key={m.id} member={m} />
          ))}
        </div>
      ) : null}
      {openTrades && trades.length > 1 ? (
        <div className="divide-y divide-hairline border-t border-hairline bg-surface-sunken/60">
          {trades.map((t) => (
            <TradeRow key={t.id} trade={t} lead={t.id === item.id} />
          ))}
        </div>
      ) : null}
    </li>
  );
}

/** One of a holder's sales on a folded Today slot: the day its money came, where it was reported, how much,
 * and the call status logged against it (the slot itself carries the newest sale's status). */
function TradeRow({ trade, lead }: { trade: TradeRef; lead: boolean }) {
  const [eventId, personId] = trade.id.split("/");
  return (
    <div className="relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 py-3 pr-4 pl-10 transition-colors hover:bg-accent/60 sm:pr-5 sm:pl-16">
      <div className="min-w-0">
        <Link
          href={`/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}`}
          className="block truncate text-sm font-medium after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {trade.date_display || "Date not confirmed"}
        </Link>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {trade.sources.join(" + ")}
          {lead ? " · the sale shown above" : trade.rm_status !== "to_call" ? ` · ${RM_STATUS_LABEL[trade.rm_status]}` : ""}
        </p>
      </div>
      <Money amount={trade.amount} align="end" size="sm" />
    </div>
  );
}
