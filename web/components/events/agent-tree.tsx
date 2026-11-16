"use client";

import { useEffect, useState } from "react";
import { Check, Cpu, Loader2, Minus, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { eventsApi } from "./api";
import { duration, returnsText, runsOnLabel, usd4, usesModel } from "./trace-format";
import type { EventRuns } from "./types";
import { currentAgent, liveCost, type AgentState, type JobView, type StepState } from "./use-job";

/** The "Now: …" line: which agent is working, what it runs on, and what it is doing. */
export function NowLine({ view }: { view: JobView }) {
  const now = currentAgent(view);
  const step = view.steps.find((s) => s.state === "running");
  const calls = view.agents.reduce((n, a) => n + a.calls, 0) || view.steps.reduce((n, s) => n + (s.calls ?? 0), 0);
  const cached = view.agents.reduce((n, a) => n + a.cached, 0) || view.steps.reduce((n, s) => n + (s.cached ?? 0), 0);
  const cost = liveCost(view);
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-hairline bg-surface-sunken/60 px-5 py-3">
      <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
        <span className="relative flex size-2 shrink-0" aria-hidden>
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-info opacity-60 motion-reduce:animate-none" />
          <span className="relative inline-flex size-2 rounded-full bg-info" />
        </span>
        <span className="font-semibold text-foreground">Now:</span>
        <span className="font-medium text-foreground">{now ? now.label : step ? step.label : "Starting"}</span>
        {now ? <RunsOnChip runsOn={now.runsOn} /> : null}
        <span className="truncate text-muted-foreground">{now ? now.doing : step ? "Working…" : "Preparing the run"}</span>
      </p>
      <p data-tech className="tnum flex shrink-0 items-baseline gap-3 text-[13px] text-muted-foreground" aria-live="off">
        <span>
          <span className="font-semibold text-foreground">{usd4(cost)}</span> spent
        </span>
        <span>
          {calls} model {calls === 1 ? "call" : "calls"}
          {cached ? <span className="text-faint"> · {cached} reused</span> : null}
        </span>
      </p>
    </div>
  );
}

/** Code or the model that answered, as a small chip. */
export function RunsOnChip({ runsOn, className }: { runsOn: string; className?: string }) {
  const model = usesModel(runsOn);
  return (
    <span
      title={runsOn}
      data-tech={model ? "" : undefined}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        model ? "bg-brand-soft text-brand-ink ring-brand/20" : "bg-secondary text-muted-foreground ring-border",
        className,
      )}
    >
      {model ? <Sparkles className="size-3" aria-hidden /> : <Cpu className="size-3" aria-hidden />}
      {runsOnLabel(runsOn)}
    </span>
  );
}

function AgentPill({ a }: { a: AgentState }) {
  const model = usesModel(a.runsOn);
  const title = [a.label, a.why && `Why: ${a.why}`, a.given && `Given: ${a.given}`, returnsText(a.returns) && `Returned: ${returnsText(a.returns)}`,
    `Runs on: ${runsOnLabel(a.runsOn)}`, a.calls ? `${a.calls} model calls (${a.cached} reused) · ${usd4(a.cost)}` : null]
    .filter(Boolean)
    .join("\n");
  return (
    <li
      title={title}
      className={cn(
        "flex min-w-0 items-center gap-1.5 rounded-lg px-2 py-1 text-[12px] ring-1 ring-inset transition-colors duration-300 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-95",
        a.state === "running" && "bg-info-soft text-foreground ring-info/30",
        a.state === "done" && "bg-surface text-foreground ring-border",
        a.state === "skipped" && "bg-surface text-faint ring-hairline",
        a.state === "failed" && "bg-negative-soft text-negative ring-negative/25",
      )}
    >
      <span className="grid size-3.5 shrink-0 place-items-center" aria-hidden>
        {a.state === "running" ? (
          <Loader2 className="size-3.5 animate-spin text-info" />
        ) : a.state === "done" ? (
          <Check className="size-3.5 text-positive" />
        ) : a.state === "failed" ? (
          <X className="size-3.5" />
        ) : (
          <Minus className="size-3.5" />
        )}
      </span>
      <span className="truncate font-medium">{a.label}</span>
      {model ? <Sparkles data-tech className="size-3 shrink-0 text-brand" aria-label="model" /> : null}
      {a.state === "done" && a.ms !== null ? <span className="tnum shrink-0 text-faint">{duration(a.ms)}</span> : null}
      {a.state === "done" && a.calls ? (
        <span data-tech className="tnum shrink-0 text-faint">{a.cost > 0 ? usd4(a.cost) : a.cached === a.calls ? "reused" : usd4(0)}</span>
      ) : null}
    </li>
  );
}

function StepNode({ s, i }: { s: StepState; i: number }) {
  return (
    <span
      className={cn(
        "relative z-10 grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold ring-1 ring-inset transition-colors duration-200",
        s.state === "done" && "bg-positive-soft text-positive ring-positive/20",
        s.state === "running" && "bg-info-soft text-info ring-info/25",
        s.state === "failed" && "bg-negative-soft text-negative ring-negative/25",
        s.state === "pending" && "bg-surface text-faint ring-border",
      )}
      aria-hidden
    >
      {s.state === "done" ? <Check className="size-3.5" /> : s.state === "running" ? <Loader2 className="size-3.5 animate-spin" /> : s.state === "failed" ? <X className="size-3.5" /> : <span className="tnum">{i + 1}</span>}
    </span>
  );
}

/**
 * The live agent tree: each pipeline step is a node on a rail, and the agents and code checks inside it
 * appear and light up as they run (a sparkle marks a model call; everything else is code).
 */
export function AgentTree({ view }: { view: JobView }) {
  return (
    <ol className="relative space-y-1 px-5 py-4" aria-label="How the call list is being built">
      <span className="absolute top-7 bottom-7 left-[31px] w-px bg-hairline" aria-hidden />
      {view.steps.map((s, i) => {
        const agents = view.agents.filter((a) => a.parent === s.step);
        const shown = agents.filter((a) => a.state !== "skipped");
        const skipped = agents.length - shown.length;
        return (
          <li key={s.step} className="flex gap-3 py-1.5">
            <StepNode s={s} i={i} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <p className={cn("text-[13px] font-semibold leading-6", s.state === "pending" ? "text-muted-foreground" : "text-foreground")}>{s.label}</p>
                {s.state === "done" ? (
                  <p className="tnum text-xs text-muted-foreground">
                    {s.seconds !== undefined ? duration(s.seconds * 1000) : ""}
                    <span data-tech>
                      {s.calls ? ` · ${s.calls} model ${s.calls === 1 ? "call" : "calls"}${s.cached ? `, ${s.cached} reused` : ""}` : " · code only"}
                      {s.cost ? ` · ${usd4(s.cost)}` : ""}
                    </span>
                  </p>
                ) : s.state === "running" ? (
                  <p className="text-xs text-info">Working…</p>
                ) : s.state === "failed" ? (
                  <p className="text-xs text-negative">Stopped here</p>
                ) : null}
              </div>
              {shown.length ? (
                <ul className="mt-1.5 flex flex-wrap gap-1.5">
                  {shown.map((a) => (
                    <AgentPill key={`${a.agent}-${a.startedAt}`} a={a} />
                  ))}
                  {skipped ? <li className="self-center px-1 text-[12px] text-faint">{skipped} skipped: no matching pages</li> : null}
                </ul>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** After a run: "This run $0.0000 vs first run $0.0289 — 31 of 31 model calls reused". */
export function RunCompare({ eventId, view }: { eventId: string; view: JobView }) {
  const [runs, setRuns] = useState<EventRuns | null>(null);
  useEffect(() => {
    if (view.state !== "complete") return;
    let live = true;
    eventsApi
      .runs(eventId)
      .then((r) => live && setRuns(r))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [eventId, view.state]);
  if (view.state !== "complete" || !runs?.latest) return null;
  const { first, latest } = runs;
  const reused = latest.cached_calls;
  const same = !first || first.run_id === latest.run_id;
  return (
    <div data-tech className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-hairline bg-positive-soft/40 px-5 py-3 text-[13px]">
      <p className="tnum text-foreground">
        <span className="font-semibold">This run {usd4(latest.cost_usd)}</span>
        {same ? (
          <span className="text-muted-foreground"> · first time this event was read · {latest.calls} model calls</span>
        ) : (
          <>
            <span className="text-muted-foreground"> vs first run </span>
            <span className="font-semibold">{usd4(first!.cost_usd)}</span>
            <span className="text-muted-foreground">
              {" "}
              — {reused} of {latest.calls} model calls reused · {duration(latest.seconds * 1000)} vs {duration(first!.seconds * 1000)}
            </span>
          </>
        )}
      </p>
      <a href="#how-built" className="shrink-0 font-medium text-brand underline-offset-4 hover:underline">
        How this list was built
      </a>
    </div>
  );
}
