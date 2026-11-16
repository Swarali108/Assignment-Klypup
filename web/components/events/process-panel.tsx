"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, RotateCw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatUSD } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { AgentTree, NowLine, RunCompare } from "./agent-tree";
import { liveCost, type JobView } from "./use-job";

function secs(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  if (n < 0.1) return "under 0.1 s";
  return n < 10 ? `${n.toFixed(1)} s` : `${Math.round(n)} s`;
}

/** Ticks once a second while running, so the elapsed time moves between stream events. */
function useElapsed(running: boolean, at: number): number {
  const [extra, setExtra] = useState(0);
  useEffect(() => {
    if (!running) return;
    const started = Date.now();
    const t = setInterval(() => setExtra((Date.now() - started) / 1000), 1000);
    return () => {
      clearInterval(t);
      setExtra(0);
    };
  }, [running, at]);
  return at + extra;
}

/**
 * Live step progress for one processing run. Running: steps tick through. Complete: the call list
 * below has been refreshed. Failed: the plain reason, and the previous call list is kept.
 */
export function ProcessPanel({
  company,
  eventId,
  view,
  onDismiss,
  onRetry,
}: {
  company: string;
  /** When given, a finished run is compared with the event's first run. */
  eventId?: string;
  view: JobView;
  onDismiss?: () => void;
  onRetry?: () => void;
}) {
  const running = view.state === "running";
  const elapsed = useElapsed(running, view.at);
  const done = view.steps.filter((s) => s.state === "done").length;
  const pct = view.state === "complete" ? 100 : Math.round(((done + (view.steps.some((s) => s.state === "running") ? 0.5 : 0)) / view.steps.length) * 100);
  const current = view.steps.find((s) => s.state === "running");

  return (
    <section
      aria-live="polite"
      aria-label={`Processing ${company}`}
      className={cn(
        "overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)",
        view.state === "failed" && "border-negative/25",
      )}
    >
      <div className="h-1 bg-secondary" aria-hidden>
        <div
          className={cn(
            "h-full transition-[width] duration-500 ease-out motion-reduce:transition-none",
            view.state === "failed" ? "bg-negative" : "bg-brand",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={cn(
              "grid size-9 shrink-0 place-items-center rounded-full",
              running ? "bg-info-soft text-info" : view.state === "complete" ? "bg-positive-soft text-positive" : "bg-negative-soft text-negative",
            )}
          >
            {running ? <Loader2 className="size-4.5 animate-spin" /> : view.state === "complete" ? <CheckCircle2 className="size-4.5" /> : <AlertCircle className="size-4.5" />}
          </span>
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-foreground">
              {running ? `Reading the filings for ${company}` : view.state === "complete" ? "Call list updated" : "Processing stopped"}
            </h2>
            <p className="tnum mt-0.5 text-[13px] text-muted-foreground">
              {running
                ? `${current ? current.label : "Starting"} · step ${Math.min(done + 1, view.steps.length)} of ${view.steps.length} · ${secs(elapsed)}`
                : view.state === "complete"
                  ? <>
                      {`All ${view.steps.length} steps${view.agents.length ? ` and ${view.agents.length} agents` : ""} in ${secs(view.seconds)}`}
                      <span data-tech>{` · ${(view.cost ?? liveCost(view)) ? `cost ${formatUSD(view.cost ?? liveCost(view))}` : "no new cost, saved work reused"}`}</span>
                    </>
                  : view.reason ?? "The run did not finish. The previous call list is kept."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {view.state === "failed" && onRetry ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RotateCw /> Try again
            </Button>
          ) : null}
          {!running && onDismiss ? (
            <Button size="icon-sm" variant="ghost" onClick={onDismiss} aria-label="Close progress">
              <X />
            </Button>
          ) : null}
        </div>
      </div>

      {running ? <NowLine view={view} /> : null}
      <div className="border-t border-hairline">
        <AgentTree view={view} />
      </div>
      {eventId ? <RunCompare eventId={eventId} view={view} /> : null}

      {view.state === "failed" ? (
        <p className="border-t border-hairline bg-negative-soft/40 px-5 py-2.5 text-xs text-muted-foreground">
          Nothing was lost: the call list below is the one from before this run.
        </p>
      ) : running ? (
        <p className="border-t border-hairline bg-surface-sunken/50 px-5 py-2.5 text-xs text-muted-foreground">
          The current call list stays below until the new one is ready.
        </p>
      ) : null}
    </section>
  );
}
