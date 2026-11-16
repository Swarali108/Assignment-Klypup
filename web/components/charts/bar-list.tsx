import { cn } from "@/lib/utils";

export type BarListRow = {
  key: string;
  label: React.ReactNode;
  sub?: React.ReactNode;
  value: number;
  display: React.ReactNode;
  aside?: React.ReactNode;
};

/** Ranked rows with an inline bar scaled to the largest value (not to an outside target). */
export function BarList({ rows, tone = "brand", className }: { rows: BarListRow[]; tone?: "brand" | "info"; className?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 0) || 1;
  return (
    <ul className={cn("divide-y divide-hairline", className)}>
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-4 py-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_6.5rem_auto] sm:px-5">
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium">{r.label}</p>
            {r.sub ? <p className="truncate text-xs text-muted-foreground">{r.sub}</p> : null}
          </div>
          <div className="col-span-2 row-start-2 h-2 overflow-hidden rounded-full bg-surface-sunken sm:col-span-1 sm:row-start-auto">
            <div
              className={cn("h-full rounded-full", tone === "brand" ? "bg-brand" : "bg-info")}
              style={{ width: `${Math.max(2, (r.value / max) * 100)}%` }}
            />
          </div>
          <span className="tnum col-start-2 row-start-1 text-right text-[13px] font-semibold sm:col-start-auto sm:row-start-auto">{r.display}</span>
          {r.aside !== undefined ? (
            <span className="tnum hidden text-right text-xs text-muted-foreground sm:block">{r.aside}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
