import { cn } from "@/lib/utils";

/** One figure with its label. Group several in <StatStrip> for a quiet KPI band. */
export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  muted = false,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  /** Value not available: shows the dash in muted ink. */
  muted?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-2 px-5 py-4", className)}>
      <span className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
        {Icon ? <Icon className="size-3.5" /> : null}
        {label}
      </span>
      <span className={cn("tnum text-[1.625rem] font-semibold leading-none tracking-[-0.02em]", muted && "text-faint")}>{value}</span>
      {sub ? <span className="text-xs text-muted-foreground">{sub}</span> : null}
    </div>
  );
}

export function StatStrip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card) md:grid-cols-4 md:divide-x [&>*:nth-child(-n+2)]:max-md:border-b [&>*:nth-child(odd)]:max-md:border-r",
        className,
      )}
    >
      {children}
    </div>
  );
}
