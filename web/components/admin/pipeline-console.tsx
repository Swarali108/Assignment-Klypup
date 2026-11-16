"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, CircleDashed, Loader2, Minus, Play, Plus, RefreshCw, ScrollText, Terminal, Wallet, XCircle, Zap } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, SectionHeader, SkeletonCard, SkeletonList, StatusBadge } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatUSD } from "@/lib/format";
import { ApiError } from "@/lib/api";
import { useLoad } from "@/lib/insights";
import { adminApi, istStamp, type AdminEvent, type RunDiff, type RunEstimate, type RunRow, type StepChoice } from "@/lib/admin";

const ALL = "all";
const EVERYONE = "__everyone__";

type Job = { jobId: string; eventId: string; step: string; fresh: boolean; streamUrl: string; logUrl: string };
type Pending = { estimate: RunEstimate; token: string; message: string };

function secs(n: number | null | undefined) {
  if (n === null || n === undefined) return "–";
  if (n < 0.1) return "< 0.1 s";
  if (n < 60) return `${n < 10 ? n.toFixed(1) : Math.round(n)} s`;
  return `${Math.floor(n / 60)} min ${Math.round(n % 60)} s`;
}

/** A run id ends in its UTC start, "…-20261115T205345Z"; show it as an IST time like the rest of the page. */
function runStamp(runId: string | null | undefined): string {
  const m = /(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(runId ?? "");
  return m ? istStamp(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`) : (runId?.split("-").pop() ?? "–");
}

export function PipelineConsole() {
  const [res, retry] = useLoad(adminApi.events);
  // A finished run refreshes the event list in the background. `latest` replaces the first load without ever showing the
  // loading state again, so the console (selected event, finished steps, log) is never unmounted when a run ends.
  const [latest, setLatest] = useState<{ events: AdminEvent[]; steps: StepChoice[] } | null>(null);
  const refresh = useCallback(() => {
    adminApi
      .events()
      .then((r) => setLatest({ events: r.events, steps: r.steps }))
      .catch(() => {});
  }, []);
  if (latest && latest.events.length > 0) return <Console events={latest.events} steps={latest.steps} onChanged={refresh} />;
  if (res.state === "loading")
    return (
      <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <SkeletonCard className="h-96" />
        <SkeletonCard className="h-96" />
      </div>
    );
  if (res.state === "error") return <ErrorState title="The console could not load" reason={res.reason} onRetry={retry} />;
  if (res.data.events.length === 0)
    return (
      <EmptyState icon={Terminal} title="No events to run" tone="brand">
        Add an event from the Events screen, then come back to run it here.
      </EmptyState>
    );
  return <Console events={res.data.events} steps={res.data.steps} onChanged={refresh} />;
}

function Console({ events, steps, onChanged }: { events: AdminEvent[]; steps: StepChoice[]; onChanged: () => void }) {
  const [eventId, setEventId] = useState(() => (events.find((e) => e.processed) ?? events[0]).event_id);
  const [step, setStep] = useState(ALL);
  const [personId, setPersonId] = useState(EVERYONE);
  const [fresh, setFresh] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [running, setRunning] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const event = events.find((e) => e.event_id === eventId) ?? events[0];

  const [people, setPeople] = useState<{ id: string; name: string }[] | null>(null);
  useEffect(() => {
    if (step !== "brief") return;
    let live = true;
    adminApi
      .callable(eventId)
      .then((r) => live && setPeople(r.callable.map((c) => ({ id: c.person.id, name: c.person.name }))))
      .catch(() => live && setPeople([]));
    return () => {
      live = false;
    };
  }, [eventId, step]);

  const reset = () => setPending(null);
  const pickEvent = (id: string) => {
    setEventId(id);
    setPersonId(EVERYONE);
    setPeople(null);
    reset();
  };
  const pickStep = (s: string) => {
    setStep(s);
    if (s !== "brief") setPersonId(EVERYONE);
    reset();
  };

  async function start(token?: string) {
    setStarting(true);
    try {
      const r = await adminApi.run({
        event_id: eventId,
        step,
        person_id: step === "brief" && personId !== EVERYONE ? personId : null,
        fresh,
        confirm_token: token,
      });
      if (r.needs_confirm) {
        setPending({ estimate: r.estimate, token: r.confirm_token, message: r.message });
        return;
      }
      setPending(null);
      setJob({ jobId: r.job_id, eventId: r.event_id, step: r.step, fresh: r.fresh, streamUrl: r.stream_url, logUrl: r.log_url });
      setRunning(true);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "The run could not start. Try again.");
      setPending(null);
    } finally {
      setStarting(false);
    }
  }

  const canRun = event.supported && !running && !event.running && !starting;
  const stepLabel = step === ALL ? "every step" : (steps.find((s) => s.step === step)?.label ?? step).toLowerCase();

  return (
    <div className="space-y-10">
      <div className="grid items-start gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <section className="space-y-5 rounded-xl border bg-surface p-5 shadow-(--shadow-card)">
          <div className="space-y-1.5">
            <label className="text-[13px] font-medium text-foreground">Event</label>
            <Select value={eventId} onValueChange={pickEvent}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {events.map((e) => (
                  <SelectItem key={e.event_id} value={e.event_id}>
                    {e.company} · {e.type_label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {event.processed ? `${event.people_count} people on the call list` : "Not processed yet"}
              {event.last_run ? ` · last run ${istStamp(event.last_run.ended_at)}` : ""}
            </p>
          </div>

          <div className="space-y-1.5">
            <span className="text-[13px] font-medium text-foreground">What to run</span>
            <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="What to run">
              {[{ step: ALL, label: "All steps" }, ...steps].map((s) => (
                <button
                  key={s.step}
                  type="button"
                  role="radio"
                  aria-checked={step === s.step}
                  onClick={() => pickStep(s.step)}
                  className={cn(
                    "h-9 rounded-lg border px-2.5 text-left text-[13px] font-medium transition-colors",
                    s.step === ALL && "col-span-2",
                    step === s.step ? "border-brand/50 bg-brand-soft text-brand-ink" : "bg-surface text-muted-foreground hover:border-input hover:text-foreground",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {step === ALL ? "Find pages, read tables, match people, rank, write briefs, assemble the list." : "A step uses what the step before it already wrote."}
            </p>
          </div>

          {step === "brief" ? (
            <div className="space-y-1.5">
              <label className="text-[13px] font-medium text-foreground">Whose brief</label>
              <Select value={personId} onValueChange={(v) => { setPersonId(v); reset(); }}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={EVERYONE}>Everyone on the call list</SelectItem>
                  {(people ?? []).map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{people === null ? "Loading the call list…" : "One person re-runs only their brief; the rest stay as they are."}</p>
            </div>
          ) : null}

          <div className="space-y-1.5">
            <span className="text-[13px] font-medium text-foreground">Model answers</span>
            <div className="grid gap-1.5" role="radiogroup" aria-label="Model answers">
              {[
                { value: false, icon: Zap, title: "From the cache", note: "Repeats earlier answers. Costs nothing when nothing changed." },
                { value: true, icon: Wallet, title: "Fresh", note: "Every model call is paid for again. Shows an estimate and asks you to confirm." },
              ].map((o) => (
                <button
                  key={String(o.value)}
                  type="button"
                  role="radio"
                  aria-checked={fresh === o.value}
                  onClick={() => { setFresh(o.value); reset(); }}
                  className={cn(
                    "flex items-start gap-2.5 rounded-lg border p-3 text-left transition-colors",
                    fresh === o.value ? "border-brand/50 bg-brand-soft" : "bg-surface hover:border-input",
                  )}
                >
                  <o.icon className={cn("mt-0.5 size-4 shrink-0", fresh === o.value ? "text-brand" : "text-faint")} aria-hidden />
                  <span>
                    <span className="block text-[13px] font-medium text-foreground">{o.title}</span>
                    <span className="block text-xs leading-snug text-muted-foreground">{o.note}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          {pending ? (
            <ConfirmPanel
              pending={pending}
              busy={starting}
              onConfirm={() => void start(pending.token)}
              onCancel={reset}
              subject={`${stepLabel} for ${event.company}`}
            />
          ) : (
            <Button className="w-full" size="lg" disabled={!canRun} onClick={() => void start()}>
              {starting ? <Loader2 className="animate-spin" /> : <Play />}
              {fresh ? "Estimate a fresh run" : "Run"} {step === ALL ? "all steps" : stepLabel}
            </Button>
          )}
          {!event.supported ? <p className="text-xs text-caution">This kind of event cannot be processed yet.</p> : null}
          {event.running && !running ? <p className="text-xs text-muted-foreground">This event is already running.</p> : null}
        </section>

        {job ? (
          <LivePanel
            key={job.jobId}
            job={job}
            steps={steps}
            company={event.company}
            onDone={() => {
              setRunning(false);
              setHistoryKey((k) => k + 1);
              onChanged();
            }}
          />
        ) : (
          <EmptyState icon={ScrollText} title="Nothing running" tone="brand" className="h-full min-h-80 justify-center">
            Pick an event and a step, then run it. Progress, what each step cost and the run&apos;s own output appear here as it happens.
          </EmptyState>
        )}
      </div>

      <History key={`${eventId}-${historyKey}`} eventId={eventId} company={event.company} />
    </div>
  );
}

function ConfirmPanel({ pending, busy, onConfirm, onCancel, subject }: { pending: Pending; busy: boolean; onConfirm: () => void; onCancel: () => void; subject: string }) {
  const { estimate } = pending;
  return (
    <div className="space-y-3 rounded-xl border border-caution/30 bg-caution-soft/50 p-4">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden />
        <div>
          <p className="text-sm font-semibold text-foreground">
            About {formatUSD(estimate.low)} to {formatUSD(estimate.high)}
          </p>
          <p className="text-xs leading-snug text-muted-foreground">
            A fresh run of {subject}. Takes about {secs(estimate.seconds_low)} to {secs(estimate.seconds_high)}.
          </p>
        </div>
      </div>
      {estimate.breakdown.length ? (
        <ul className="divide-y divide-hairline rounded-lg bg-surface text-xs ring-1 ring-border">
          {estimate.breakdown
            .filter((b) => b.cost_usd_high > 0)
            .map((b) => (
              <li key={b.step} className="flex items-center justify-between gap-3 px-3 py-1.5">
                <span className="text-foreground">{b.step}</span>
                <span className="tnum text-muted-foreground">
                  {formatUSD(b.cost_usd_low)} – {formatUSD(b.cost_usd_high)}
                </span>
              </li>
            ))}
        </ul>
      ) : null}
      <p className="text-xs leading-snug text-muted-foreground">{estimate.basis}</p>
      <div className="flex gap-2">
        <Button onClick={onConfirm} disabled={busy} className="flex-1">
          {busy ? <Loader2 className="animate-spin" /> : <Play />} Confirm and run
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

type StepView = { state: "pending" | "running" | "done" | "failed"; seconds?: number; cost?: number; calls?: number; cached?: number };
type JobEvt = { step?: string; state?: string; type?: string; phase?: string; doing?: string; seconds?: number; cost_usd?: number; calls?: number; cached?: number; reason?: string | null };

function LivePanel({ job, steps, company, onDone }: { job: Job; steps: StepChoice[]; company: string; onDone: () => void }) {
  const shown = job.step === ALL ? steps : steps.filter((s) => s.step === job.step);
  const [view, setView] = useState<Record<string, StepView>>({});
  const [final, setFinal] = useState<{ state: "complete" | "failed"; reason: string | null; seconds?: number; cost?: number } | null>(null);
  const [doing, setDoing] = useState<string | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  });
  const tail = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stream = new EventSource(job.streamUrl);
    stream.onmessage = (m) => {
      let e: JobEvt;
      try {
        e = JSON.parse(m.data) as JobEvt;
      } catch {
        return;
      }
      if (e.type === "agent") {
        if (e.doing) setDoing(e.doing);
        return;
      }
      if (e.step) {
        const step = e.step;
        setView((v) => ({
          ...v,
          [step]:
            e.state === "start"
              ? { state: "running" }
              : e.state === "done"
                ? { state: "done", seconds: e.seconds, cost: e.cost_usd, calls: e.calls, cached: e.cached }
                : { ...v[step], state: "failed" },
        }));
        return;
      }
      if (e.state === "complete" || e.state === "failed") {
        setFinal({ state: e.state, reason: e.reason ?? null, seconds: e.seconds, cost: e.cost_usd });
        setDoing(null);
        stream.close();
        done.current();
      }
    };
    stream.onerror = () => {
      // The browser retries on its own; a finished job simply ends the stream.
    };
    const log = new EventSource(job.logUrl);
    log.onmessage = (m) => {
      try {
        const d = JSON.parse(m.data) as { line?: string; state?: string };
        if (d.line !== undefined) setLines((l) => (l.length > 600 ? [...l.slice(-500), d.line!] : [...l, d.line!]));
        if (d.state) log.close();
      } catch {}
    };
    return () => {
      stream.close();
      log.close();
    };
  }, [job.streamUrl, job.logUrl]);

  useEffect(() => {
    const el = tail.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  const running = !final;
  return (
    <section className="space-y-4 rounded-xl border bg-surface p-5 shadow-(--shadow-card)">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-foreground">{company}</h2>
          <p className="text-xs text-muted-foreground">
            {job.step === ALL ? "All steps" : (steps.find((s) => s.step === job.step)?.label ?? job.step)} · {job.fresh ? "fresh, nothing from the cache" : "from the cache"}
          </p>
        </div>
        {running ? (
          <span className="inline-flex h-6 items-center gap-1.5 rounded-md bg-info-soft px-2 text-xs font-medium text-info ring-1 ring-inset ring-info/15">
            <Loader2 className="size-3.5 animate-spin" aria-hidden /> Running
          </span>
        ) : final.state === "complete" ? (
          <span className="inline-flex h-6 items-center gap-1.5 rounded-md bg-positive-soft px-2 text-xs font-medium text-positive ring-1 ring-inset ring-positive/15">
            <CheckCircle2 className="size-3.5" aria-hidden /> Finished{final.seconds !== undefined ? ` in ${secs(final.seconds)}` : ""}
            {final.cost !== undefined ? ` · ${formatUSD(final.cost)}` : ""}
          </span>
        ) : (
          <span className="inline-flex h-6 items-center gap-1.5 rounded-md bg-negative-soft px-2 text-xs font-medium text-negative ring-1 ring-inset ring-negative/15">
            <XCircle className="size-3.5" aria-hidden /> Failed
          </span>
        )}
      </div>

      {final?.state === "failed" ? <p className="rounded-lg bg-negative-soft/60 p-3 text-sm text-foreground">{final.reason ?? "Processing failed."}</p> : null}

      <ol className="divide-y divide-hairline rounded-lg border">
        {shown.map((s) => {
          const v = view[s.step] ?? { state: "pending" as const };
          return (
            <li key={s.step} className="flex items-center gap-3 px-3.5 py-2.5">
              {v.state === "done" ? (
                <CheckCircle2 className="size-4 text-positive" aria-hidden />
              ) : v.state === "running" ? (
                <Loader2 className="size-4 animate-spin text-info" aria-hidden />
              ) : v.state === "failed" ? (
                <XCircle className="size-4 text-negative" aria-hidden />
              ) : (
                <CircleDashed className="size-4 text-faint" aria-hidden />
              )}
              <span className={cn("flex-1 text-sm", v.state === "pending" ? "text-muted-foreground" : "font-medium text-foreground")}>{s.label}</span>
              {v.state === "done" ? (
                <span className="tnum text-xs text-muted-foreground">
                  {secs(v.seconds)}
                  {v.calls ? ` · ${v.calls} calls (${v.cached ?? 0} cached)` : ""}
                  {v.cost ? ` · ${formatUSD(v.cost)}` : ""}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {running && doing ? <p className="text-xs text-muted-foreground">Now: {doing}</p> : null}

      <div>
        <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Terminal className="size-3.5" aria-hidden /> Live output
        </h3>
        <div
          ref={tail}
          role="log"
          aria-live="off"
          className="h-56 overflow-auto rounded-lg border bg-surface-sunken p-3 font-mono text-[11.5px] leading-relaxed text-foreground/85 [scrollbar-width:thin]"
        >
          {lines.length === 0 ? <span className="text-faint">{running ? "Waiting for the first line…" : "This run printed nothing."}</span> : lines.map((l, i) => <div key={i} className="whitespace-pre-wrap break-words">{l}</div>)}
        </div>
      </div>
    </section>
  );
}

function History({ eventId, company }: { eventId: string; company: string }) {
  const [res, retry] = useLoad(() => adminApi.history(eventId));
  return (
    <section className="space-y-4">
      <SectionHeader
        title="Run history"
        description={`Every run of ${company}, and what changed between the last two.`}
        actions={
          <Button variant="outline" size="sm" onClick={retry}>
            <RefreshCw /> Refresh
          </Button>
        }
      />
      {res.state === "loading" ? (
        <SkeletonList rows={3} />
      ) : res.state === "error" ? (
        <ErrorState title="History could not load" reason={res.reason} onRetry={retry} />
      ) : (
        <>
          <DiffCard diff={res.data.diff} />
          <RunTable runs={res.data.runs} />
        </>
      )}
    </section>
  );
}

function DiffCard({ diff }: { diff: RunDiff }) {
  if (!diff.available)
    return (
      <EmptyState icon={ArrowRight} title="Nothing to compare yet">
        {diff.runs_with_snapshot.length === 0
          ? "Each run saves a copy of its call list when it finishes. Once this event has two finished runs, what changed between them appears here."
          : "One run has saved its call list. Run this event once more and the differences appear here."}
      </EmptyState>
    );
  const none = diff.added.length + diff.removed.length + diff.changed.length === 0;
  return (
    <div className="space-y-4 rounded-xl border bg-surface p-5 shadow-(--shadow-card)">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">What changed since the run before</h3>
        <span className="tnum text-xs text-muted-foreground">
          {runStamp(diff.older)} → {runStamp(diff.newer)}
        </span>
      </div>
      {none ? (
        <p className="text-sm text-muted-foreground">
          Nothing changed: the same {diff.unchanged} {diff.unchanged === 1 ? "person" : "people"}, with the same amounts, tiers and order.
        </p>
      ) : (
        <div className="grid gap-5 md:grid-cols-3">
          <DiffColumn icon={Plus} tone="text-positive" title="Added" count={diff.added.length} empty="Nobody new">
            {diff.added.map((p) => (
              <li key={p.person_id}>
                <span className="font-medium text-foreground">{p.name}</span>
                {p.amount ? <span className="block text-xs text-muted-foreground">{p.amount}</span> : null}
              </li>
            ))}
          </DiffColumn>
          <DiffColumn icon={Minus} tone="text-negative" title="Removed" count={diff.removed.length} empty="Nobody dropped">
            {diff.removed.map((p) => (
              <li key={p.person_id}>
                <span className="font-medium text-foreground">{p.name}</span>
                {p.amount ? <span className="block text-xs text-muted-foreground">{p.amount}</span> : null}
              </li>
            ))}
          </DiffColumn>
          <DiffColumn icon={RefreshCw} tone="text-info" title="Changed" count={diff.changed.length} empty="No amount, tier or order changed">
            {diff.changed.map((p) => (
              <li key={p.person_id}>
                <span className="font-medium text-foreground">{p.name}</span>
                {p.changes.map((c) => (
                  <span key={c.field} className="block text-xs text-muted-foreground">
                    <span className="capitalize">{c.field}</span>: {String(c.before ?? "–")} → {String(c.after ?? "–")}
                  </span>
                ))}
              </li>
            ))}
          </DiffColumn>
        </div>
      )}
    </div>
  );
}

function DiffColumn({ icon: Icon, tone, title, count, empty, children }: { icon: React.ComponentType<{ className?: string }>; tone: string; title: string; count: number; empty: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Icon className={cn("size-3.5", tone)} aria-hidden /> {title} <span className="tnum">{count}</span>
      </h4>
      {count === 0 ? <p className="text-xs text-faint">{empty}</p> : <ul className="space-y-2 text-sm">{children}</ul>}
    </div>
  );
}

function RunTable({ runs }: { runs: RunRow[] }) {
  if (runs.length === 0)
    return (
      <EmptyState icon={ScrollText} title="No runs yet">
        This event has not been run. Run it above and it is listed here with its cost and time.
      </EmptyState>
    );
  return (
    <div className="overflow-x-auto rounded-xl border bg-surface shadow-(--shadow-card)">
      <table className="w-full min-w-[40rem] text-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-xs text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Started</th>
            <th className="px-4 py-2.5 font-medium">Result</th>
            <th className="px-4 py-2.5 text-right font-medium">Time</th>
            <th className="px-4 py-2.5 text-right font-medium">Model calls</th>
            <th className="px-4 py-2.5 text-right font-medium">Cost</th>
            <th className="px-4 py-2.5 font-medium">Saved list</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {runs.map((r) => (
            <tr key={r.run_id}>
              <td className="tnum px-4 py-2.5 text-foreground">{istStamp(r.started_at)}</td>
              <td className="px-4 py-2.5">
                {r.status === "ok" ? <StatusBadge status="ready" reason={null} /> : r.status === "error" ? <StatusBadge status="failed" reason={r.error} /> : <span className="text-xs text-muted-foreground">Unknown</span>}
              </td>
              <td className="tnum px-4 py-2.5 text-right text-muted-foreground">{secs(r.wall_s)}</td>
              <td className="tnum px-4 py-2.5 text-right text-muted-foreground">
                {r.calls} <span className="text-faint">({r.cached_calls} cached)</span>
              </td>
              <td className="tnum px-4 py-2.5 text-right text-foreground">{formatUSD(r.cost_usd)}</td>
              <td className="px-4 py-2.5 text-xs text-muted-foreground">{r.snapshot ? "Yes" : "Before this was kept"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
