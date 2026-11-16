import { AlertCircle, Ban, CheckCircle2, Clock3, Loader2, ScanLine, UserX } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EventSummary } from "@/lib/types";

/** What an event (or a feed item) looks like to the RM. "empty" = read fine, but no individual gets money. */
export type DisplayStatus = "ready" | "empty" | "processing" | "failed" | "scanned" | "not_supported" | "not_processed";

const LOOK: Record<DisplayStatus, { label: string; icon: typeof CheckCircle2; cls: string; spin?: boolean }> = {
  ready: { label: "Call list ready", icon: CheckCircle2, cls: "bg-positive-soft text-positive ring-positive/15" },
  empty: { label: "No one to call", icon: UserX, cls: "bg-secondary text-muted-foreground ring-border" },
  processing: { label: "Processing", icon: Loader2, cls: "bg-info-soft text-info ring-info/15", spin: true },
  failed: { label: "Could not be read", icon: AlertCircle, cls: "bg-negative-soft text-negative ring-negative/15" },
  scanned: { label: "Scanned filing", icon: ScanLine, cls: "bg-caution-soft text-caution ring-caution/15" },
  not_supported: { label: "Not supported yet", icon: Ban, cls: "bg-secondary text-muted-foreground ring-border" },
  not_processed: { label: "Not read yet", icon: Clock3, cls: "bg-info-soft text-info ring-info/15" },
};

export function displayStatus(e: Pick<EventSummary, "status" | "people_count">): DisplayStatus {
  if (e.status === "ready") return e.people_count > 0 ? "ready" : "empty";
  return (e.status in LOOK ? e.status : "not_supported") as DisplayStatus;
}

export function StatusChip({ status, className, label }: { status: DisplayStatus; className?: string; label?: string }) {
  const s = LOOK[status];
  const Icon = s.icon;
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-2 text-xs font-medium ring-1 ring-inset",
        s.cls,
        className,
      )}
    >
      <Icon className={cn("size-3.5", s.spin && "animate-spin")} aria-hidden />
      {label ?? s.label}
    </span>
  );
}
