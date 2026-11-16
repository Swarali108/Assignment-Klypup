import { AlertCircle, Ban, CheckCircle2, Clock3, Loader2, ScanLine } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EventStatus } from "@/lib/types";

const STATUS: Record<EventStatus, { label: string; icon: typeof CheckCircle2; cls: string; spin?: boolean }> = {
  ready: { label: "Ready", icon: CheckCircle2, cls: "bg-positive-soft text-positive ring-positive/15" },
  processing: { label: "Processing", icon: Loader2, cls: "bg-info-soft text-info ring-info/15", spin: true },
  failed: { label: "Failed", icon: AlertCircle, cls: "bg-negative-soft text-negative ring-negative/15" },
  scanned: { label: "Scanned filing", icon: ScanLine, cls: "bg-caution-soft text-caution ring-caution/15" },
  not_supported: { label: "Not supported", icon: Ban, cls: "bg-secondary text-muted-foreground ring-border" },
  not_processed: { label: "Not read yet", icon: Clock3, cls: "bg-secondary text-muted-foreground ring-border" },
};

export const SCANNED_COPY = "Scanned filing: text not readable yet";

export function StatusBadge({
  status,
  reason,
  className,
}: {
  status: EventStatus;
  /** Plain reason under the badge. Omit for the default (scanned); pass null to hide it. */
  reason?: string | null;
  className?: string;
}) {
  const s = STATUS[status] ?? STATUS.not_supported;
  const Icon = s.icon;
  const why = reason === undefined ? (status === "scanned" ? SCANNED_COPY : null) : reason;
  return (
    <span className={cn("inline-flex flex-col items-start gap-1", className)}>
      <span
        className={cn(
          "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-md px-2 text-xs font-medium ring-1 ring-inset",
          s.cls,
        )}
      >
        <Icon className={cn("size-3.5", s.spin && "animate-spin")} aria-hidden />
        {s.label}
      </span>
      {why ? <span className="max-w-[36ch] text-xs leading-snug text-muted-foreground">{why}</span> : null}
    </span>
  );
}
