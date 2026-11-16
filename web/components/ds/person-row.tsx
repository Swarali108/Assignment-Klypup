"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { EVENT_TYPE_LABEL } from "@/lib/format";
import type { CallItem, HouseholdMember } from "@/lib/types";
import { formatCr } from "@/lib/format";
import { Avatar } from "./avatar";
import { Money } from "./money";
import { TierBadge } from "./tier-badge";
import { TimingPill } from "./timing-pill";
import { ConfidenceBadge } from "./confidence-badge";
import { InBookBadge } from "./in-book-badge";

export function personHref(item: Pick<CallItem, "event" | "person">) {
  return `/people/${encodeURIComponent(item.event.id)}/${encodeURIComponent(item.person.id)}`;
}

const ENTITY = /\b(trust|fund|llp|limited|ltd|huf|private|company|holdings)\b/i;

/**
 * One call-list row: who, why, how much, when, how sure. Household rows (`item.members`) expand
 * to show members. Use inside a `divide-y` list container (see <CallList>).
 */
export function PersonRow({
  item,
  asOf,
  showEvent = true,
  showTier = true,
  actions,
  rank,
  nested = false,
}: {
  item: CallItem;
  asOf?: string;
  showEvent?: boolean;
  showTier?: boolean;
  /** Right-edge slot (quick actions). Clicks inside do not navigate. */
  actions?: React.ReactNode;
  rank?: number;
  nested?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const members = item.members ?? [];
  const entity = item.person.holder_type !== "person" || ENTITY.test(item.person.name);
  const sub = [item.person.kind_label, item.person.role, showEvent ? `${item.event.company} ${item.event.type_label ?? EVENT_TYPE_LABEL[item.event.type] ?? ""}`.trim() : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className={cn("group/row relative", nested && "bg-surface-sunken/60")}>
      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-4 gap-y-3 px-4 py-4 transition-colors hover:bg-accent/60 sm:px-5 lg:grid-cols-[auto_minmax(0,1fr)_10.5rem_13rem_11.5rem] lg:items-center">
        <div className="flex items-center gap-3">
          {rank !== undefined ? <span className="tnum hidden w-5 text-right text-xs text-faint sm:block">{rank}</span> : null}
          <Avatar name={item.person.name} entity={entity} size={nested ? "sm" : "md"} />
        </div>

        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <Link
              href={personHref(item)}
              className="truncate text-[15px] font-semibold text-foreground after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
            >
              {item.person.name}
            </Link>
            {item.in_book ? <InBookBadge /> : null}
          </div>
          {sub ? <p className="truncate text-[13px] text-muted-foreground">{sub}</p> : null}
          <p className="mt-1.5 line-clamp-2 max-w-[68ch] text-[13px] leading-snug text-foreground/80">{item.why}</p>
          <div className="mt-2.5 flex flex-col items-start gap-2 lg:hidden">
            {showTier ? <TierBadge tier={item.tier} label={item.tier_label} /> : null}
            <TimingPill timing={item.timing} asOf={asOf} />
          </div>
          {members.length > 0 ? (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              className="relative z-10 mt-2.5 inline-flex items-center gap-1.5 rounded-md text-xs font-medium text-brand-ink hover:underline"
            >
              <Users className="size-3.5" />
              {item.household?.label ?? "Household"} · {members.length + 1} people
              {item.household_total_cr ? <span className="tnum font-normal text-muted-foreground">· {formatCr(item.household_total_cr)} together</span> : null}
              <ChevronDown className={cn("size-3.5 transition-transform duration-200", open && "rotate-180")} />
            </button>
          ) : null}
        </div>

        <div className="hidden min-w-0 flex-col items-start gap-1.5 lg:flex">
          {showTier ? <TierBadge tier={item.tier} label={item.tier_label} /> : null}
          <ConfidenceBadge confidence={item.confidence} />
        </div>

        <div className="hidden min-w-0 lg:block">
          <TimingPill timing={item.timing} asOf={asOf} stacked />
        </div>

        <div className="col-start-2 flex items-start justify-between gap-3 lg:col-start-auto lg:justify-self-end">
          <Money amount={item.amount} align="end-lg" size="md" showKind />
          {actions ? <div className="relative z-10 flex items-center gap-1">{actions}</div> : null}
        </div>
      </div>
      {open && members.length > 0 ? (
        <div className="divide-y divide-hairline border-t border-hairline bg-surface-sunken/60">
          {members.map((m) => (
            <MemberRow key={m.id} member={m} showTier={showTier} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** A household member under its lead row (flat shape from /api/today `members`). */
export function MemberRow({ member, showTier = true }: { member: HouseholdMember; showTier?: boolean }) {
  return (
    <div className="relative grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 py-3 pr-4 pl-10 transition-colors hover:bg-accent/60 sm:pr-5 sm:pl-16">
      <Avatar name={member.name} size="sm" />
      <div className="min-w-0">
        <Link
          href={`/people/${member.id}`}
          className="block truncate text-sm font-medium after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {member.name}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {member.role ? <span className="truncate">{member.role}</span> : null}
          {showTier ? <TierBadge tier={member.tier} className="h-5 px-1.5 text-[11px]" /> : null}
        </div>
      </div>
      <Money amount={member.amount} align="end" size="sm" />
    </div>
  );
}

export function CallList({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)", className)}>{children}</div>;
}
