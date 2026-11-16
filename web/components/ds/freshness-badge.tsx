import { Clock3, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";

/**
 * When a source document was fetched, and a "Stale" flag once it is older than the configured number of days
 * (the API decides: STALE_AFTER_DAYS). Nothing is shown when the fetch date is not known.
 */
export function FreshnessBadge({
  fetchedAt,
  ageDays,
  stale,
  className,
  compact = false,
}: {
  fetchedAt?: string | null;
  ageDays?: number | null;
  stale?: boolean;
  className?: string;
  compact?: boolean;
}) {
  if (!fetchedAt) return null;
  const date = formatDate(fetchedAt);
  return (
    <span
      data-tech
      title={stale ? `Fetched ${ageDays ?? "?"} days ago: the filing may have changed since` : "Date this filing was last fetched"}
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-[11px] font-medium ring-1 ring-inset",
        stale ? "bg-caution-soft text-caution ring-caution/20" : "bg-secondary text-muted-foreground ring-border",
        className,
      )}
    >
      {stale ? <History className="size-3" aria-hidden /> : <Clock3 className="size-3" aria-hidden />}
      {compact ? date : <>Fetched {date}</>}
      {stale ? <span className="font-semibold">· Stale</span> : null}
    </span>
  );
}
