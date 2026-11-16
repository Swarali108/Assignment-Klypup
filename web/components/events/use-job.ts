"use client";

import { useEffect, useReducer } from "react";
import { jobStreamUrl } from "@/lib/api";
import { eventsApi } from "./api";
import type { JobEvent } from "./types";

export const STEPS: { step: string; label: string }[] = [
  { step: "locate", label: "Find the right pages" },
  { step: "extract", label: "Read the tables" },
  { step: "people", label: "Match people and families" },
  { step: "rank", label: "Rank who to call" },
  { step: "brief", label: "Write call briefs" },
  { step: "report", label: "Assemble the call list" },
];

export type StepState = {
  step: string;
  label: string;
  state: "pending" | "running" | "done" | "failed";
  seconds?: number;
  cost?: number;
  calls?: number;
  cached?: number;
  runsOn?: string;
  why?: string;
};

/** One agent or code sub-step inside a step, as the live tree shows it. */
export type AgentState = {
  agent: string;
  parent: string;
  label: string;
  state: "running" | "done" | "skipped" | "failed";
  why: string;
  given: string;
  runsOn: string;
  doing: string;
  returns: Record<string, number | boolean | null>;
  calls: number;
  cached: number;
  cost: number;
  ms: number | null;
  /** Seconds since the job started when this agent began. */
  startedAt: number;
};

export interface JobView {
  state: "running" | "complete" | "failed";
  steps: StepState[];
  /** Agents in the order they started. */
  agents: AgentState[];
  reason: string | null;
  seconds: number | null;
  cost: number | null;
  /** Seconds since the job started, from the last event. */
  at: number;
}

export function initialJob(steps = STEPS): JobView {
  return { state: "running", steps: steps.map((s) => ({ ...s, state: "pending" })), agents: [], reason: null, seconds: null, cost: null, at: 0 };
}

/** Spend so far: finished agents plus finished steps that had no agent events (an older server). */
export function liveCost(view: JobView): number {
  const byAgents = view.agents.reduce((n, a) => n + (a.cost || 0), 0);
  const withAgents = new Set(view.agents.map((a) => a.parent));
  const bySteps = view.steps.filter((s) => !withAgents.has(s.step)).reduce((n, s) => n + (s.cost ?? 0), 0);
  return byAgents + bySteps;
}

/** The agent working right now (the last one started and not finished), with any progress line. */
export function currentAgent(view: JobView): AgentState | null {
  for (let i = view.agents.length - 1; i >= 0; i--) if (view.agents[i].state === "running") return view.agents[i];
  return null;
}

function applyAgent(view: JobView, ev: JobEvent, at: number): JobView {
  const name = ev.agent!;
  const parent = ev.parent ?? "";
  const idx = view.agents.findIndex((a) => a.agent === name && a.parent === parent && (ev.phase !== "start" || a.state === "running"));
  if (ev.phase === "start") {
    if (idx >= 0) return { ...view, at };
    const next: AgentState = {
      agent: name,
      parent,
      label: ev.label ?? name,
      state: ev.runs_on === "skipped" ? "skipped" : "running",
      why: ev.why ?? "",
      given: ev.given ?? "",
      runsOn: ev.runs_on ?? "code",
      doing: ev.doing ?? ev.label ?? name,
      returns: {},
      calls: 0,
      cached: 0,
      cost: 0,
      ms: null,
      startedAt: at,
    };
    return { ...view, at, agents: [...view.agents, next] };
  }
  if (idx < 0) return { ...view, at };
  const agents = view.agents.slice();
  const a = agents[idx];
  if (ev.phase === "progress") agents[idx] = { ...a, doing: ev.doing ?? a.doing };
  else
    agents[idx] = {
      ...a,
      state: ev.status === "failed" ? "failed" : ev.status === "skipped" ? "skipped" : "done",
      runsOn: ev.runs_on ?? a.runsOn,
      returns: ev.returns ?? {},
      calls: ev.calls ?? 0,
      cached: ev.cached ?? ev.cached_calls ?? 0,
      cost: ev.cost_usd ?? 0,
      ms: ev.ms ?? null,
    };
  return { ...view, at, agents };
}

/** Fold one stream event into the view. Keyed by step / agent name, so a replayed stream is harmless. */
export function applyEvent(view: JobView, ev: JobEvent): JobView {
  const at = Math.max(view.at, ev.at ?? 0);
  if (ev.type === "agent" && ev.agent) return applyAgent(view, ev, at);
  if (!ev.step) {
    if (ev.state === "complete" || ev.state === "failed") {
      return {
        ...view,
        at,
        state: ev.state,
        reason: ev.reason ?? null,
        seconds: ev.seconds ?? ev.at ?? null,
        cost: ev.cost_usd ?? view.steps.reduce((n, s) => n + (s.cost ?? 0), 0),
        steps: ev.state === "failed" ? view.steps.map((s) => (s.state === "running" ? { ...s, state: "failed" } : s)) : view.steps,
        agents: ev.state === "failed" ? view.agents.map((a) => (a.state === "running" ? { ...a, state: "failed" } : a)) : view.agents,
      };
    }
    return view;
  }
  const exists = view.steps.some((s) => s.step === ev.step);
  const steps = exists ? view.steps : [...view.steps, { step: ev.step, label: ev.label ?? ev.step, state: "pending" as const }];
  return {
    ...view,
    at,
    steps: steps.map((s) => {
      if (s.step !== ev.step) return s;
      if (ev.state === "start") return s.state === "pending" ? { ...s, label: ev.label ?? s.label, state: "running" } : s;
      if (ev.state === "done")
        return { ...s, label: ev.label ?? s.label, state: "done", seconds: ev.seconds, cost: ev.cost_usd, calls: ev.calls, cached: ev.cached, runsOn: ev.runs_on, why: ev.why };
      if (ev.state === "failed") return { ...s, state: "failed" };
      return s;
    }),
  };
}

type Action = { type: "reset" } | { type: "event"; ev: JobEvent } | { type: "lost" };

function reducer(view: JobView, a: Action): JobView {
  if (a.type === "reset") return initialJob();
  if (a.type === "lost")
    return view.state === "running"
      ? { ...view, state: "failed", reason: "Lost contact with the processing service. Refresh the page to see the latest call list." }
      : view;
  return applyEvent(view, a.ev);
}

/**
 * Follow a processing job over Server-Sent Events. The server closes the stream after the final
 * event; we close too so EventSource does not reconnect and replay. If the stream drops before
 * the end we fall back to polling the job once a second.
 */
export function useJob(jobId: string | null): JobView | null {
  const [view, dispatch] = useReducer(reducer, undefined, () => initialJob());

  useEffect(() => {
    if (!jobId) return;
    dispatch({ type: "reset" });
    let finished = false;
    let poll: ReturnType<typeof setInterval> | null = null;
    const es = new EventSource(jobStreamUrl(jobId));

    const handle = (ev: JobEvent) => {
      dispatch({ type: "event", ev });
      if (!ev.step && (ev.state === "complete" || ev.state === "failed")) {
        finished = true;
        es.close();
        if (poll) clearInterval(poll);
      }
    };

    es.onmessage = (m) => {
      try {
        handle(JSON.parse(m.data) as JobEvent);
      } catch {}
    };
    es.onerror = () => {
      es.close();
      if (finished || poll) return;
      let misses = 0;
      poll = setInterval(async () => {
        try {
          const snap = await eventsApi.job(jobId);
          snap.events.forEach(handle);
          misses = 0;
        } catch {
          if (++misses >= 5) {
            if (poll) clearInterval(poll);
            dispatch({ type: "lost" });
          }
        }
      }, 1000);
    };

    return () => {
      finished = true;
      es.close();
      if (poll) clearInterval(poll);
    };
  }, [jobId]);

  return jobId ? view : null;
}
