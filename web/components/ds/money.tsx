import { cn } from "@/lib/utils";
import { formatCr } from "@/lib/format";
import type { Amount } from "@/lib/types";

const ALIGN = { start: "", end: "items-end text-right", "end-lg": "lg:items-end lg:text-right" } as const;

const SIZE = {
  sm: "text-sm",
  md: "text-[15px]",
  lg: "text-xl tracking-[-0.01em]",
  xl: "text-[2rem] leading-none tracking-[-0.02em]",
} as const;

/**
 * A rupee amount in crore with tabular numerals. Null means "not disclosed" and is never shown as ₹0.
 * Pass either `amount` (API shape) or `value` (+ flags).
 */
export function Money({
  amount,
  value,
  estimate,
  kind,
  reason,
  size = "md",
  showKind = false,
  align = "start",
  className,
}: {
  amount?: Amount;
  value?: number | null;
  estimate?: boolean;
  kind?: "cash" | "shares";
  reason?: string | null;
  size?: keyof typeof SIZE;
  showKind?: boolean;
  align?: "start" | "end" | "end-lg";
  className?: string;
}) {
  const v = amount ? amount.value_cr : value ?? null;
  const est = amount ? amount.estimate : !!estimate;
  const k = amount ? amount.kind : kind;
  const why = amount ? amount.reason : reason;
  const unknownLabel = amount?.display && amount.value_cr === null ? amount.display : "Amount not disclosed";
  const text = formatCr(v);

  if (text === null) {
    return (
      <span className={cn("inline-flex flex-col", ALIGN[align], className)}>
        <span className={cn("font-medium text-muted-foreground", size === "xl" ? "text-xl" : size === "lg" ? "text-base" : "text-sm")}>
          {unknownLabel}
        </span>
        {why ? (
          <span className="max-w-[30ch] text-xs leading-snug text-faint">{why}</span>
        ) : null}
      </span>
    );
  }

  return (
    <span className={cn("inline-flex flex-col", ALIGN[align], className)}>
      <span className={cn("tnum font-semibold text-foreground", SIZE[size])} title={amount?.detail ?? undefined}>
        {est ? (
          <span className="mr-0.5 font-normal text-faint" title="Estimate" aria-label="estimate">
            ≈
          </span>
        ) : null}
        {text}
      </span>
      {showKind && k ? (
        <span className="text-xs text-muted-foreground">
          {k === "cash" ? (est ? "Cash, estimate" : "Cash") : "In shares, not cash"}
        </span>
      ) : null}
    </span>
  );
}
