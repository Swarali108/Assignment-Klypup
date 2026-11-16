import { Clock, HelpCircle, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDate, formatRelative } from "@/lib/format";
import type { Timing } from "@/lib/types";

const DOT: Record<string, string> = {
  in_hand: "bg-positive",
  due_past: "bg-caution",
  scheduled: "bg-info",
  upcoming: "bg-info",
  unlocked: "bg-caution",
  partly_unlocked: "bg-caution",
  after_date: "bg-faint",
  past: "bg-faint",
  not_applicable: "bg-faint",
  unknown: "bg-faint",
};
const LOCKED = new Set(["locked", "locked_in"]);
const QUIET = new Set(["past", "after_date", "not_applicable", "unknown"]);

/** When the money is (or was) available. Relative text is computed against the API's as-of date. */
export function TimingPill({
  timing,
  asOf,
  stacked = false,
  className,
}: {
  timing: Timing;
  asOf?: string;
  /** Relative time on its own line under the label (narrow table columns). */
  stacked?: boolean;
  className?: string;
}) {
  // API labels often carry their own "(8 months ago)" or "(today)"; only add a relative when they do not.
  const hasRel = /\bago\b|\(in |\bin \d+ (day|month|year)|\((today|yesterday|tomorrow)\)/i.test(timing.label);
  const rel = asOf && timing.date_iso && !hasRel ? formatRelative(timing.date_iso, asOf) : null;
  const status = timing.status;
  const Icon = LOCKED.has(status) ? Lock : status === "unknown" ? HelpCircle : status === "upcoming" || status === "scheduled" ? Clock : null;
  return (
    <span title={formatDate(timing.date_iso) ?? undefined} className={cn("inline-flex min-w-0 items-start gap-2 text-[13px] leading-snug text-foreground", className)}>
      <span className="mt-[3px] grid size-3.5 shrink-0 place-items-center">
        {Icon ? (
          <Icon className="size-3.5 text-muted-foreground" aria-hidden />
        ) : (
          <span className={cn("size-2 rounded-full", DOT[status] ?? "bg-faint")} aria-hidden />
        )}
      </span>
      <span className={cn("min-w-0", stacked ? "flex flex-col" : "inline")}>
        <span className={cn(QUIET.has(status) && "text-muted-foreground")}>{timing.label}</span>
        {rel ? <span className="tnum text-muted-foreground">{stacked ? rel : ` · ${rel}`}</span> : null}
      </span>
    </span>
  );
}
