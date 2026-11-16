"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Ban, Check, CheckCircle2, Clock3, Loader2, RefreshCw, ShieldAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ApiError, resolveApiUrl } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { CHECK_FINISHED, istStamp, sourcesApi, usd, type CheckEvent, type EstimateReply } from "./api";

type Phase =
  | { kind: "loading" }
  | { kind: "error"; reason: string }
  | { kind: "estimate"; reply: EstimateReply }
  | { kind: "starting"; reply: EstimateReply }
  | { kind: "running"; ceiling: number; events: CheckEvent[] }
  | { kind: "finished"; ceiling: number; events: CheckEvent[] };

const errText = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "The data service did not answer.");

/** Words for one source status in the live list. */
const SOURCE_WORD: Record<string, string> = { ok: "checked", blocked: "blocked", failed: "could not be read", disabled: "off" };

/**
 * "Check for new filings now" (admin): estimate first, nothing runs until Confirm. Confirm redeems the
 * single-use token; the check then streams its progress (sources read, events found, each event processed
 * with its cost) and never spends past the confirmed ceiling.
 */
export function CheckNowButton({ onFinished }: { onFinished?: () => void }) {
  const { can } = useSession();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const stream = useRef<EventSource | null>(null);
  const poll = useRef<number | null>(null);

  const stop = useCallback(() => {
    stream.current?.close();
    stream.current = null;
    if (poll.current) window.clearInterval(poll.current);
    poll.current = null;
  }, []);

  useEffect(() => stop, [stop]);

  const loadEstimate = useCallback(() => {
    setPhase({ kind: "loading" });
    sourcesApi
      .estimate()
      .then((reply) => setPhase({ kind: "estimate", reply }))
      .catch((e) => setPhase({ kind: "error", reason: errText(e) }));
  }, []);

  const follow = useCallback(
    (jobId: string, streamUrl: string, ceiling: number) => {
      const seen: CheckEvent[] = [];
      const finish = (events: CheckEvent[]) => {
        stop();
        setPhase({ kind: "finished", ceiling, events });
        router.refresh();
        window.dispatchEvent(new Event(CHECK_FINISHED));
        onFinished?.();
      };
      const fallback = () => {
        stream.current?.close();
        stream.current = null;
        if (poll.current) return;
        poll.current = window.setInterval(() => {
          sourcesApi
            .job(jobId)
            .then((job) => {
              if (job.state === "running") setPhase({ kind: "running", ceiling, events: job.events });
              else finish(job.events);
            })
            .catch(() => undefined);
        }, 1500);
      };
      const es = new EventSource(resolveApiUrl(streamUrl));
      stream.current = es;
      es.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as CheckEvent;
          seen.push(ev);
          if (ev.stage === "finish") finish([...seen]);
          else setPhase({ kind: "running", ceiling, events: [...seen] });
        } catch {
          /* a malformed line is skipped; the next one carries the state */
        }
      };
      es.onerror = () => {
        if (stream.current) fallback();
      };
    },
    [onFinished, router, stop],
  );

  const confirm = (reply: EstimateReply) => {
    setPhase({ kind: "starting", reply });
    sourcesApi
      .confirm(reply.token)
      .then((start) => {
        setPhase({ kind: "running", ceiling: start.ceiling_usd, events: [] });
        follow(start.job_id, start.stream_url, start.ceiling_usd);
      })
      .catch((e) => setPhase({ kind: "error", reason: errText(e) }));
  };

  if (!can("process")) return null;
  const busy = phase.kind === "running" || phase.kind === "starting";

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (busy && !next) {
          setOpen(false); // the check keeps running on the server; its result lands in the log
          return;
        }
        setOpen(next);
        if (next && phase.kind !== "running") loadEstimate();
        if (!next) stop();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <RefreshCw className={cn(phase.kind === "running" && "animate-spin motion-reduce:animate-none")} />
          Check for new filings now
        </Button>
      </DialogTrigger>
      <DialogContent className="gap-0 p-0 sm:max-w-xl">
        <DialogHeader className="border-b px-6 py-5 text-left">
          <DialogTitle className="text-base">
            {phase.kind === "finished" ? "Check finished" : phase.kind === "running" ? "Checking for new filings" : "Check for new filings now"}
          </DialogTitle>
          <DialogDescription>
            {phase.kind === "running" || phase.kind === "finished"
              ? `Spending stops at ${usd(phase.ceiling)}, what was left of today's auto-processing cap when you confirmed.`
              : "Reads every source that is on, then processes new events oldest first while today's spend stays under the cap. Nothing runs until you confirm."}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[min(70dvh,34rem)] overflow-y-auto px-6 py-5">
          {phase.kind === "loading" ? <EstimateSkeleton /> : null}
          {phase.kind === "error" ? (
            <div className="flex gap-3 rounded-lg bg-negative-soft px-4 py-3 text-sm text-negative" role="alert">
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <p>{phase.reason}</p>
            </div>
          ) : null}
          {phase.kind === "estimate" || phase.kind === "starting" ? <EstimateView reply={phase.reply} /> : null}
          {phase.kind === "running" || phase.kind === "finished" ? <Progress events={phase.events} finished={phase.kind === "finished"} /> : null}
        </div>
        <DialogFooter className="mx-0 mb-0 border-t bg-surface-sunken/50 px-6 py-4">
          {phase.kind === "estimate" || phase.kind === "starting" ? (
            <>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => confirm(phase.reply)} disabled={phase.kind === "starting"}>
                {phase.kind === "starting" ? <Loader2 className="animate-spin" /> : <Check />}
                Confirm · spend at most {usd(phase.reply.estimate.ceiling_usd)}
              </Button>
            </>
          ) : phase.kind === "error" ? (
            <>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Close
              </Button>
              <Button variant="outline" onClick={loadEstimate}>
                <RefreshCw /> New estimate
              </Button>
            </>
          ) : phase.kind === "running" ? (
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Hide · the check keeps running
            </Button>
          ) : phase.kind === "finished" ? (
            <Button onClick={() => setOpen(false)}>Done</Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EstimateSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Working out the estimate">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-10 animate-pulse rounded-lg bg-secondary motion-reduce:animate-none" />
      ))}
    </div>
  );
}

function EstimateView({ reply }: { reply: EstimateReply }) {
  const e = reply.estimate;
  const waiting = e.events.filter((x) => !x.fits).length;
  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border bg-border text-center">
        {[
          ["Spent today", usd(e.spent_today_usd)],
          ["Daily cap", usd(e.cap_usd)],
          ["This check, at most", usd(e.ceiling_usd)],
        ].map(([k, v]) => (
          <div key={k} className="bg-surface px-3 py-3">
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="tnum mt-0.5 text-lg font-semibold text-foreground">{v}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="est-steps">
        <h3 id="est-steps" className="mb-2 text-sm font-semibold">
          What it does
        </h3>
        <ul className="divide-y divide-hairline rounded-lg border">
          {e.steps.map((s) => (
            <li key={s.step} className="flex items-baseline justify-between gap-4 px-4 py-2.5 text-[13px]">
              <span className="min-w-0 text-foreground">{s.step}</span>
              <span className="tnum shrink-0 text-muted-foreground">
                {s.cost_usd_high === 0 ? "free" : `${usd(s.cost_usd_low)} – ${usd(s.cost_usd_high)}`}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {e.events.length ? (
        <section aria-labelledby="est-events">
          <h3 id="est-events" className="mb-2 text-sm font-semibold">
            Waiting events{waiting ? <span className="font-normal text-muted-foreground"> · {waiting} over the cap</span> : null}
          </h3>
          <ul className="divide-y divide-hairline rounded-lg border">
            {e.events.map((x) => (
              <li key={x.event_id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                {x.fits ? <Clock3 className="size-3.5 shrink-0 text-info" aria-hidden /> : <ShieldAlert className="size-3.5 shrink-0 text-caution" aria-hidden />}
                <span className="min-w-0 flex-1 truncate text-foreground" title={x.company ?? x.event_id}>{x.company ?? x.event_id}</span>
                <span className={cn("shrink-0 text-xs", x.fits ? "text-muted-foreground" : "text-caution")}>{x.fits ? "will run" : "needs approval"}</span>
                <span className="tnum shrink-0 whitespace-nowrap text-right text-muted-foreground">
                  {usd(x.low)} – {usd(x.high)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="text-[13px] text-muted-foreground">No events are waiting right now. New filings the check finds are processed within the ceiling.</p>
      )}

      <p className="text-xs leading-relaxed text-muted-foreground">
        {e.basis} Last checked {istStamp(e.last_checked)}. This estimate is valid for {Math.round(reply.ttl_s / 60)} minutes.
      </p>
    </div>
  );
}

function Progress({ events, finished }: { events: CheckEvent[]; finished: boolean }) {
  const sources = events.filter((e) => e.stage === "source");
  const found = events.find((e) => e.stage === "events");
  const classify = events.find((e) => e.stage === "classify");
  const processed = new Map<string, CheckEvent>();
  for (const e of events) if (e.stage === "process" && e.event_id) processed.set(e.event_id, e);
  const end = events.find((e) => e.stage === "finish");
  return (
    <div className="space-y-5" aria-live="polite">
      <section aria-labelledby="prog-sources">
        <h3 id="prog-sources" className="mb-2 text-sm font-semibold">
          Sources
        </h3>
        {sources.length === 0 ? (
          <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden /> Reading the first source (2 seconds or more between requests to each site)
          </p>
        ) : (
          <ul className="divide-y divide-hairline rounded-lg border">
            {sources.map((s) => (
              <li key={s.source} className="flex items-start gap-3 px-4 py-2.5 text-[13px]">
                <SourceIcon status={s.status} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-foreground">{s.name ?? s.source}</span>
                  {s.reason ? <span className="block text-xs text-muted-foreground">{s.reason}</span> : null}
                </span>
                <span className="tnum shrink-0 text-xs text-muted-foreground">
                  {SOURCE_WORD[s.status ?? ""] ?? s.status} · {s.items ?? 0} items
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {classify || found ? (
        <p className="text-[13px] text-muted-foreground">
          {classify?.skipped ? `${classify.skipped} titles left unsorted: ${classify.reason}. ` : classify?.items ? `${classify.items} titles sorted by the cheap model. ` : ""}
          {found ? `${found.events} events in the window, ${found.new} new or changed.` : ""}
        </p>
      ) : null}

      {processed.size ? (
        <section aria-labelledby="prog-events">
          <h3 id="prog-events" className="mb-2 text-sm font-semibold">
            Processing
          </h3>
          <ul className="divide-y divide-hairline rounded-lg border">
            {[...processed.values()].map((p) => (
              <li key={p.event_id} className="flex items-start gap-3 px-4 py-2.5 text-[13px]">
                <ProcessIcon e={p} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-foreground">{p.company ?? p.event_id}</span>
                  {p.state === "done" && p.status !== "ok" && p.reason ? <span className="block text-xs text-muted-foreground">{p.reason}</span> : null}
                </span>
                <span className="tnum shrink-0 text-xs text-muted-foreground">
                  {p.state === "start" ? `up to ${usd(p.estimate_usd)}` : p.status === "ok" ? usd(p.cost_usd) : p.status === "needs_approval" ? "waits" : p.status}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {finished && end ? (
        <div
          className={cn(
            "flex gap-3 rounded-lg px-4 py-3 text-sm",
            end.status === "done" ? "bg-positive-soft text-positive" : "bg-negative-soft text-negative",
          )}
          role="status"
        >
          {end.status === "done" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden /> : <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />}
          <p>
            {end.status === "done"
              ? `${end.events_new ?? 0} new or changed events; ${end.processed ?? 0} processed for ${usd(end.spent_usd)}${end.needs_approval ? `; ${end.needs_approval} wait for approval` : ""}. Today: ${usd(end.spent_today_usd)} of ${usd(end.cap_usd)}.`
              : `The check stopped: ${end.error ?? "no reason recorded"}. Nothing past this point was spent.`}
          </p>
        </div>
      ) : !finished ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden /> Working. You can hide this window; the check keeps running and its result lands in the log.
        </p>
      ) : null}
    </div>
  );
}

function SourceIcon({ status }: { status?: string }) {
  if (status === "ok") return <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-positive" aria-hidden />;
  if (status === "blocked") return <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-caution" aria-hidden />;
  if (status === "disabled") return <Ban className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />;
  return <X className="mt-0.5 size-3.5 shrink-0 text-negative" aria-hidden />;
}

function ProcessIcon({ e }: { e: CheckEvent }) {
  if (e.state === "start") return <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin text-info motion-reduce:animate-none" aria-hidden />;
  if (e.status === "ok") return <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-positive" aria-hidden />;
  if (e.status === "needs_approval") return <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-caution" aria-hidden />;
  return <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-negative" aria-hidden />;
}
