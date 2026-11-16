"use client";

import { AlertTriangle, SearchX, Sparkles } from "lucide-react";
import { Avatar } from "@/components/ds/avatar";
import { TierBadge } from "@/components/ds/tier-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCr } from "@/lib/format";
import type { AskResponse, CallItem } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Questions shown before the RM types anything. Each one runs as a plain-English question. */
export const ASK_EXAMPLES = [
  "promoters with cash in hand above 50 crore",
  "who just got their shares unlocked",
  "sellers in IPOs with cash above 100 crore",
];

const HOW: Record<string, string> = {
  assistant: "Understood by the assistant",
  rules: "Understood from the key words",
  keyword: "Matched names, companies and roles",
};

/** "Interpreted as" chips and the match count, above the result rows. */
export function AskSummary({ answer }: { answer: AskResponse }) {
  const how = HOW[answer.interpreted_by];
  return (
    <div className="space-y-2.5 border-b border-hairline px-3 pt-2 pb-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-0.5 text-xs text-muted-foreground">Interpreted as</span>
        {answer.chips.length ? (
          answer.chips.map((c) => (
            <span
              key={c}
              className="tnum inline-flex h-6 items-center rounded-md bg-brand-soft px-2 text-xs font-medium text-brand-ink ring-1 ring-brand/15 ring-inset"
            >
              {c}
            </span>
          ))
        ) : (
          <span className="inline-flex h-6 items-center rounded-md bg-secondary px-2 text-xs font-medium text-muted-foreground">
            Everyone on the call list
          </span>
        )}
      </div>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Sparkles className="size-3.5 text-brand" />
        <span className="tnum font-medium text-foreground">
          {answer.count} {answer.count === 1 ? "person matches" : "people match"}
        </span>
        {how ? <span>· {how}</span> : null}
      </p>
    </div>
  );
}

/** Body of one result row (render inside a CommandItem). Amount text comes from the API's own display. */
export function AskPersonRow({ item }: { item: CallItem }) {
  const known = item.amount.value_cr !== null && item.amount.value_cr !== undefined;
  const sub = [item.person.kind_label, item.person.role, item.event.company].filter(Boolean).join(" · ");
  return (
    <div className="flex w-full min-w-0 items-center gap-3 py-0.5">
      <Avatar name={item.person.name} size="sm" entity={item.person.holder_type !== "person"} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{item.person.name}</p>
        <p className="truncate text-xs text-muted-foreground">{sub}</p>
      </div>
      <TierBadge tier={item.tier} label={item.tier_label} className="hidden h-5 px-1.5 text-[11px] sm:inline-flex" />
      <span className={cn("tnum w-24 shrink-0 text-right text-sm", known ? "font-semibold text-foreground" : "text-xs text-muted-foreground")}>
        {known ? (
          <>
            {item.amount.estimate ? <span className="mr-0.5 font-normal text-faint">≈</span> : null}
            {formatCr(item.amount.value_cr)}
          </>
        ) : (
          item.amount.display || "Amount not disclosed"
        )}
      </span>
    </div>
  );
}

export function AskLoading() {
  return (
    <div className="space-y-1 px-3 py-2" role="status" aria-label="Answering">
      <div className="mb-3 flex gap-1.5">
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-6 w-20" />
      </div>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 py-2">
          <Skeleton className="size-7 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-44" />
            <Skeleton className="h-3 w-64 max-w-full" />
          </div>
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  );
}

export function AskNoMatch() {
  return (
    <div className="flex flex-col items-center px-6 py-6 text-center">
      <span className="mb-2.5 grid size-9 place-items-center rounded-full bg-secondary text-muted-foreground">
        <SearchX className="size-4" />
      </span>
      <p className="text-sm font-medium">No one on the call list matches this</p>
      <p className="mt-1 max-w-[44ch] text-xs text-muted-foreground">
        Try a wider amount, a different role (promoter, director, investor) or drop one condition.
      </p>
    </div>
  );
}

export function AskError({ reason, onRetry }: { reason: string; onRetry: () => void }) {
  return (
    <div role="alert" className="mx-3 my-2 flex items-start gap-3 rounded-lg border border-negative/20 bg-negative-soft/60 px-3 py-2.5">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-negative" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">The question could not be answered</p>
        <p className="text-xs text-muted-foreground">{reason}</p>
      </div>
      <button type="button" onClick={onRetry} className="shrink-0 text-xs font-medium text-brand-ink hover:underline">
        Try again
      </button>
    </div>
  );
}
