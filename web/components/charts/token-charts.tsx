"use client";

import { Minimize2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatCost, formatTokens, percent } from "@/lib/chat";
import { cn } from "@/lib/utils";

/**
 * Two small charts for token use. One encoding everywhere: reused-from-cache in the brand colour, sent fresh in
 * the recessive slate, split by a 2px surface gap. Values ride the tooltip and the table view; the legend always shows.
 */
export function TokenLegend({ className, compressed = false }: { className?: string; compressed?: boolean }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground", className)}>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-[3px] bg-brand" aria-hidden /> Reused from cache
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-[3px] bg-chart-5 dark:bg-faint" aria-hidden /> Sent fresh
      </span>
      {compressed ? (
        <span className="inline-flex items-center gap-1.5">
          <Minimize2 className="size-3 text-foreground" aria-hidden /> Earlier turns summarised
        </span>
      ) : null}
    </div>
  );
}

export type ContextColumn = { key: string; label: string; total: number; cached: number; compressed: boolean; cost?: number | null; question?: string };

function niceMax(v: number) {
  if (v <= 0) return 1000;
  const step = v <= 2000 ? 500 : v <= 6000 ? 1000 : v <= 15000 ? 2500 : 5000;
  return Math.ceil(v / step) * step;
}

/** Context sent per answer, as columns over the conversation; a marker where older turns were summarised. */
export function ContextColumns({ turns, onSelect, className }: { turns: ContextColumn[]; onSelect?: (key: string) => void; className?: string }) {
  if (!turns.length) return null;
  const max = niceMax(Math.max(...turns.map((t) => t.total)));
  const ticks = [0, max / 2, max];
  const H = 132;
  return (
    <figure className={cn("w-full", className)}>
      <div className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-2">
        <div className="relative tnum text-[11px] text-faint" style={{ height: H }} aria-hidden>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2" style={{ top: H - (t / max) * H }}>
              {formatTokens(t)}
            </span>
          ))}
        </div>
        <div className="relative" style={{ height: H }}>
          {ticks.map((t) => (
            <span key={t} className="absolute inset-x-0 h-px bg-hairline" style={{ top: H - (t / max) * H }} aria-hidden />
          ))}
          <ol className="absolute inset-0 flex items-end gap-1 sm:gap-1.5">
            {turns.map((t, i) => {
              const fresh = Math.max(0, t.total - t.cached);
              const hCached = (t.cached / max) * H;
              const hFresh = (fresh / max) * H;
              const pct = percent(t.cached, t.total);
              return (
                <li key={t.key} className="relative flex h-full min-w-0 flex-1 items-end justify-center">
                  {t.compressed ? (
                    <span className="absolute left-1/2 grid size-4 -translate-x-1/2 place-items-center rounded-full bg-surface text-foreground ring-1 ring-border" style={{ bottom: hCached + hFresh + 6 }} aria-hidden>
                      <Minimize2 className="size-2.5" />
                    </span>
                  ) : null}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => onSelect?.(t.key)}
                        aria-label={`Answer ${i + 1}: ${formatTokens(t.total)} tokens of context, ${pct ?? 0}% reused from cache${t.compressed ? ", earlier turns summarised" : ""}`}
                        className="group/col flex h-full w-full max-w-6 flex-col items-stretch justify-end rounded-t-[4px] focus-visible:outline-offset-1"
                      >
                        {fresh > 0 ? (
                          <span className={cn("block rounded-t-[4px] bg-chart-5 transition-opacity group-hover/col:opacity-80 dark:bg-faint", t.cached > 0 && "mb-[2px]")} style={{ height: Math.max(2, hFresh - (t.cached > 0 ? 2 : 0)) }} />
                        ) : null}
                        {t.cached > 0 ? <span className={cn("block bg-brand transition-opacity group-hover/col:opacity-85", fresh > 0 ? "" : "rounded-t-[4px]")} style={{ height: Math.max(2, hCached) }} /> : null}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="tnum max-w-64">
                      <p className="font-medium">Answer {i + 1}</p>
                      {t.question ? <p className="truncate opacity-80">{t.question}</p> : null}
                      <p className="mt-1">
                        {formatTokens(t.total)} tokens · {pct ?? 0}% from cache
                        {t.cost != null ? ` · ${formatCost(t.cost)}` : ""}
                      </p>
                      {t.compressed ? <p>Earlier turns summarised before this answer</p> : null}
                    </TooltipContent>
                  </Tooltip>
                </li>
              );
            })}
          </ol>
        </div>
        <span />
        <div className="tnum mt-1.5 flex gap-1 text-[11px] text-faint sm:gap-1.5" aria-hidden>
          {turns.map((t, i) => (
            <span key={t.key} className="min-w-0 flex-1 text-center">
              {turns.length <= 16 || i % 2 === 0 ? i + 1 : ""}
            </span>
          ))}
        </div>
      </div>
      <figcaption className="sr-only">
        <table>
          <thead>
            <tr>
              <th>Answer</th>
              <th>Context tokens</th>
              <th>From cache</th>
              <th>Summarised</th>
            </tr>
          </thead>
          <tbody>
            {turns.map((t, i) => (
              <tr key={t.key}>
                <td>{i + 1}</td>
                <td>{t.total}</td>
                <td>{t.cached}</td>
                <td>{t.compressed ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}

export type SplitRow = { key: string; label: React.ReactNode; sub?: React.ReactNode; total: number; cached: number; display: React.ReactNode; aside?: React.ReactNode };

/** Input tokens per row (e.g. per model), split into cached and fresh, scaled to the largest row. */
export function TokenSplitBars({ rows, className }: { rows: SplitRow[]; className?: string }) {
  const max = Math.max(...rows.map((r) => r.total), 0) || 1;
  return (
    <ul className={cn("divide-y divide-hairline", className)}>
      {rows.map((r) => {
        const w = (r.total / max) * 100;
        const cachedShare = r.total ? r.cached / r.total : 0;
        const pct = percent(r.cached, r.total);
        return (
          <li key={r.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-4 py-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_6rem_5.5rem] sm:px-5">
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium">{r.label}</p>
              {r.sub ? <p className="tnum truncate text-xs text-muted-foreground">{r.sub}</p> : null}
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  tabIndex={0}
                  role="img"
                  aria-label={`${formatTokens(r.total)} input tokens, ${pct ?? 0}% reused from cache`}
                  className="col-span-2 row-start-2 flex h-2.5 items-stretch rounded-[4px] sm:col-span-1 sm:row-start-auto"
                >
                  <div className="flex h-full" style={{ width: `${Math.max(2, w)}%` }}>
                    {cachedShare > 0 ? <span className={cn("h-full bg-brand", cachedShare < 1 ? "rounded-l-[4px]" : "rounded-[4px]")} style={{ width: `${cachedShare * 100}%` }} /> : null}
                    {cachedShare < 1 ? (
                      <span className={cn("h-full bg-chart-5 dark:bg-faint", cachedShare > 0 ? "ml-[2px] rounded-r-[4px]" : "rounded-[4px]")} style={{ width: `${(1 - cachedShare) * 100}%` }} />
                    ) : null}
                  </div>
                </div>
              </TooltipTrigger>
              <TooltipContent className="tnum">
                {formatTokens(r.cached)} from cache · {formatTokens(r.total - r.cached)} fresh ({pct ?? 0}% reused)
              </TooltipContent>
            </Tooltip>
            <span className="tnum col-start-2 row-start-1 text-right text-[13px] font-semibold sm:col-start-auto sm:row-start-auto">{r.display}</span>
            {r.aside !== undefined ? <span className="tnum hidden text-right text-xs text-muted-foreground sm:block">{r.aside}</span> : null}
          </li>
        );
      })}
    </ul>
  );
}
