"use client";

import { useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, ChevronDown, Cpu, Sparkles, TriangleAlert } from "lucide-react";
import { SectionHeader, StatCard, StatStrip } from "@/components/ds";
import { cn } from "@/lib/utils";
import { RunsOnChip } from "./agent-tree";
import { duration, returnsText, runsOnLabel, usd4, usesModel } from "./trace-format";
import type { EventRuns, EventTrace, TraceRecord } from "./types";

type Placed = TraceRecord & { start: number };

/** Start offsets for every record: the recorded one, else laid end to end inside its step. */
function place(trace: EventTrace): { steps: (Placed & { children: Placed[] })[]; total: number } {
  let cursor = 0;
  const steps = trace.steps.map((s) => {
    const sStart = typeof s.start_ms === "number" ? s.start_ms : cursor;
    let inner = sStart;
    const children = trace.agents
      .filter((a) => a.step === s.name)
      .map((a) => {
        const start = typeof a.start_ms === "number" ? a.start_ms : inner;
        inner = start + (a.ms || 0);
        return { ...a, start };
      });
    cursor = sStart + (s.ms || 0);
    return { ...s, start: sStart, children };
  });
  const total = Math.max(trace.total_ms || 0, cursor, 1);
  return { steps, total };
}

function Bar({ start, ms, total, model, muted }: { start: number; ms: number; total: number; model: boolean; muted?: boolean }) {
  const left = Math.min(100, (start / total) * 100);
  const width = Math.max(0.6, Math.min(100 - left, ((ms || 0) / total) * 100));
  return (
    <div className="relative h-2 w-full overflow-hidden rounded-full bg-secondary" aria-hidden>
      <div
        className={cn("absolute inset-y-0 rounded-full", muted ? "bg-faint/40" : model ? "bg-brand" : "bg-info/70")}
        style={{ left: `${left}%`, width: `${width}%` }}
      />
    </div>
  );
}

function AgentRow({ a, total }: { a: Placed; total: number }) {
  const model = usesModel(a.runs_on);
  const skipped = a.status === "skipped";
  const ret = returnsText(a.returns);
  return (
    <li className={cn("grid grid-cols-1 gap-x-6 gap-y-1.5 px-5 py-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_230px]", skipped && "opacity-60")}>
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-[13px] font-medium text-foreground">
          {a.label}
          <RunsOnChip runsOn={skipped ? "skipped" : a.runs_on} />
          {a.status === "failed" ? <span className="text-xs text-negative">failed</span> : null}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          <span className="text-faint">Why: </span>
          {a.why || "—"}
        </p>
      </div>
      <div className="min-w-0 text-xs text-muted-foreground">
        <p className="flex flex-wrap items-center gap-1.5">
          <span className="text-faint">Given</span> <span className="text-foreground">{a.given || "—"}</span>
        </p>
        {ret ? (
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <ArrowRight className="size-3 text-faint" aria-hidden />
            <span className="text-foreground">{ret}</span>
          </p>
        ) : null}
      </div>
      <div className="min-w-0 space-y-1.5">
        <Bar start={a.start} ms={a.ms} total={total} model={model} muted={skipped} />
        <p className="tnum flex justify-between gap-2 text-[11px] text-muted-foreground">
          <span>{duration(a.ms)}</span>
          <span>
            {a.calls ? (
              <>
                {a.calls} {a.calls === 1 ? "call" : "calls"}
                {a.cached_calls ? <span className="text-faint"> · {a.cached_calls} reused</span> : null}
                {a.tokens_in ? <span className="text-faint"> · {(a.tokens_in + a.tokens_out).toLocaleString("en-IN")} tok</span> : null}
                <span className="font-medium text-foreground"> · {usd4(a.cost_usd)}</span>
              </>
            ) : (
              "no model call"
            )}
          </span>
        </p>
      </div>
    </li>
  );
}

function StepGroup({ s, total, index }: { s: Placed & { children: Placed[] }; total: number; index: number }) {
  const [open, setOpen] = useState(true);
  const modelCalls = s.calls;
  return (
    <li className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="grid w-full grid-cols-1 items-center gap-x-6 gap-y-2 px-5 py-3.5 text-left transition-colors hover:bg-accent/40 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_230px]"
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className="tnum grid size-6 shrink-0 place-items-center rounded-full bg-positive-soft text-[11px] font-semibold text-positive ring-1 ring-inset ring-positive/20">
            {index + 1}
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-foreground">{s.label}</span>
            <span className="block truncate text-xs text-muted-foreground">{s.why || `${s.children.length} ${s.children.length === 1 ? "agent" : "agents"}`}</span>
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <RunsOnChip runsOn={s.runs_on} />
          <span className="tnum">
            {s.children.length} {s.children.length === 1 ? "agent" : "agents"}
            {modelCalls ? ` · ${modelCalls} model ${modelCalls === 1 ? "call" : "calls"}` : ""}
            {s.cached_calls ? `, ${s.cached_calls} reused` : ""}
          </span>
        </span>
        <span className="space-y-1.5">
          <Bar start={s.start} ms={s.ms} total={total} model={usesModel(s.runs_on)} />
          <span className="tnum flex justify-between text-[11px] text-muted-foreground">
            <span>{duration(s.ms)}</span>
            <span className="flex items-center gap-1">
              <span className="font-medium text-foreground">{usd4(s.cost_usd)}</span>
              <ChevronDown className={cn("size-3.5 transition-transform duration-200", open && "rotate-180")} aria-hidden />
            </span>
          </span>
        </span>
      </button>
      {open && s.children.length ? (
        <ul className="divide-y divide-hairline border-t border-hairline bg-surface-sunken/30">
          {s.children.map((a) => (
            <AgentRow key={`${a.name}-${a.order}`} a={a} total={total} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * "How this list was built": every agent and code check of the last run — why it ran, what it was given,
 * what it returned, what it ran on, and its calls, tokens, cost and time — with the totals checked against
 * the cost log, and the first run compared with the latest.
 */
export function TraceView({ trace, runs }: { trace: EventTrace; runs: EventRuns | null }) {
  const placed = useMemo(() => place(trace), [trace]);
  const t = trace.totals;
  const share = t.calls ? Math.round((t.cached_calls / t.calls) * 100) : 0;
  const used = trace.agents.filter((a) => usesModel(a.runs_on)).flatMap((a) => a.runs_on.replace("code + ", "").split(", "));
  // "model" (the logs did not name it) and "skipped" are not model names.
  const models = Array.from(new Set(used.filter((m) => m !== "model" && m !== "skipped")));
  const codeAgents = trace.agents.filter((a) => !usesModel(a.runs_on) && a.status !== "skipped").length;
  const first = runs?.first;
  const latest = runs?.latest;

  return (
    <section id="how-built" data-tech className="scroll-mt-24 space-y-5" aria-labelledby="how-built-title">
      <SectionHeader
        title={<span id="how-built-title">How this list was built</span>}
        description="Every agent and code check of the last run: what decided it, what it was given, what it returned, and what it ran on. A model only copies text from a few pages; code finds the pages, checks every quote and does the arithmetic."
        actions={
          trace.balanced ? (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-positive-soft px-2 py-1 text-xs font-medium text-positive ring-1 ring-inset ring-positive/20">
              <CheckCircle2 className="size-3.5" aria-hidden /> Totals match the cost log
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-caution-soft px-2 py-1 text-xs font-medium text-caution ring-1 ring-inset ring-caution/25">
              <TriangleAlert className="size-3.5" aria-hidden /> Totals differ from the cost log
            </span>
          )
        }
      />

      <StatStrip>
        <StatCard label="Cost of this run" value={usd4(t.cost_usd)} sub={first && latest && first.run_id !== latest.run_id ? `First run ${usd4(first.cost_usd)}` : "First time this event was read"} />
        <StatCard label="Time" value={duration(trace.total_ms)} sub={first && latest && first.run_id !== latest.run_id ? `First run ${duration(first.seconds * 1000)}` : `${placed.steps.length} steps`} />
        <StatCard
          label="Model calls"
          value={t.calls}
          sub={t.calls ? `${t.cached_calls} reused (${share}%) · ${(t.tokens_in + t.tokens_out).toLocaleString("en-IN")} tokens` : "None needed"}
        />
        <StatCard
          label="Agents"
          value={trace.agents.filter((a) => a.status !== "skipped").length}
          sub={
            <span className="inline-flex flex-wrap items-center gap-x-2">
              <span className="inline-flex items-center gap-1">
                <Sparkles className="size-3 text-brand" aria-hidden /> {trace.agents.filter((a) => usesModel(a.runs_on)).length} read with a model
              </span>
              <span className="inline-flex items-center gap-1">
                <Cpu className="size-3" aria-hidden /> {codeAgents} code
              </span>
            </span>
          }
        />
      </StatStrip>

      <ol className="space-y-3">
        {placed.steps.map((s, i) => (
          <StepGroup key={s.name} s={s} total={placed.total} index={i} />
        ))}
      </ol>

      <p className="text-xs text-muted-foreground">
        Runs on: {models.length ? models.map(runsOnLabel).join(", ") : used.includes("model") ? "a model" : "code only"} for reading; code for everything else.{" "}
        {trace.source === "live" ? "Recorded while the run happened." : "Rebuilt from the run's logs (agent times are model time only)."}{" "}
        <span className="tnum">
          Cost log for this run: {trace.cost_log.calls} calls, {usd4(trace.cost_log.cost_usd)}.
        </span>
        {runs && runs.count > 1 ? <span className="tnum"> This event has been processed {runs.count} times.</span> : null}
      </p>
    </section>
  );
}
