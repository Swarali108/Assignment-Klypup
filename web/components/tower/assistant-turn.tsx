"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Ban, Check, ChevronRight, CircleDashed, Clock, Coins, Cpu, Loader2, Play, RotateCw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { expiryMs, formatCost, formatMs, formatSeconds, formatTokens, modelLabel, percent, type ChatEstimate, type ChatStep, type ClarifyOption } from "@/lib/chat";
import { properName } from "@/lib/call-script";
import { Avatar, BrandMark } from "@/components/ds";
import { Prose } from "./prose";
import { ChatCardView } from "./chat-cards";
import { useChat, type AssistantTurn } from "./chat-store";

export function ModelBadge({ model }: { model: string | null }) {
  return (
    <span
      data-tech
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-[11px] font-medium whitespace-nowrap ring-1 ring-inset",
        model ? "bg-info-soft text-info ring-info/15" : "bg-secondary text-muted-foreground ring-border",
      )}
    >
      {model ? <Cpu className="size-3" aria-hidden /> : null}
      {modelLabel(model)}
    </span>
  );
}

function StepIcon({ status }: { status: ChatStep["status"] }) {
  if (status === "running") return <Loader2 className="size-3.5 animate-spin text-brand" aria-label="Running" />;
  if (status === "done") return <Check className="size-3.5 text-positive" aria-label="Done" />;
  if (status === "failed") return <X className="size-3.5 text-negative" aria-label="Failed" />;
  return <CircleDashed className="size-3.5 text-faint" aria-label="Skipped" />;
}

/** Claude-style collapsible "thinking" steps: label, model, time and cost for each. */
export function StepTimeline({ turn, defaultOpen = true }: { turn: AssistantTurn; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const touched = useRef(false);
  const wasStreaming = useRef(turn.streaming);
  useEffect(() => {
    if (wasStreaming.current && !turn.streaming && !touched.current && !turn.error) setOpen(false);
    wasStreaming.current = turn.streaming;
  }, [turn.streaming, turn.error]);

  if (!turn.steps.length) {
    return turn.streaming ? (
      <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin text-brand" aria-hidden /> Starting…
      </p>
    ) : null;
  }
  const running = turn.steps.find((s) => s.status === "running");
  const totalMs = turn.steps.reduce((s, x) => s + (x.ms || 0), 0);
  // While streaming: preview the current step only when collapsed (otherwise it is already
  // shown in the open list, which looked like a duplicate). When open, stay neutral.
  const summary = turn.streaming
    ? open
      ? "Working…"
      : `${running?.label ?? "Working"}…`
    : `${turn.steps.length} ${turn.steps.length === 1 ? "step" : "steps"} · ${formatMs(turn.done ? turn.done.seconds * 1000 : totalMs)}`;

  return (
    <div className="text-[13px]">
      <button
        type="button"
        onClick={() => {
          touched.current = true;
          setOpen((o) => !o);
        }}
        aria-expanded={open}
        className="group/steps inline-flex items-center gap-1.5 rounded-md py-0.5 pr-1 text-muted-foreground transition-colors hover:text-foreground"
      >
        {turn.streaming ? <Loader2 className="size-3.5 animate-spin text-brand" aria-hidden /> : <Check className="size-3.5 text-faint" aria-hidden />}
        <span className={cn(turn.streaming && "text-foreground")}>{summary}</span>
        <ChevronRight className={cn("size-3.5 transition-transform duration-200", open && "rotate-90")} aria-hidden />
      </button>
      <div className={cn("grid transition-[grid-template-rows] duration-300 ease-(--ease-out-expo) motion-reduce:transition-none", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <div className="overflow-hidden">
          <ol className="relative mt-2 ml-[7px] border-l border-border pb-1" aria-live="polite">
            {turn.steps.map((s) => (
              <li key={s.id} className="step-in relative grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 py-1.5 pl-5 max-sm:grid-cols-1">
                <span className="absolute top-2 -left-[8px] grid size-[15px] place-items-center rounded-full bg-background">
                  <StepIcon status={s.status} />
                </span>
                <div className="min-w-0">
                  <p className={cn("leading-snug", s.status === "running" ? "font-medium text-foreground" : s.status === "failed" ? "text-negative" : "text-foreground/85")}>{s.label}</p>
                  {s.detail ? <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{s.detail}</p> : null}
                </div>
                <div data-tech className="tnum flex items-center gap-2.5 self-start text-xs text-muted-foreground sm:justify-end">
                  <ModelBadge model={s.model} />
                  <span className="w-12 text-right max-sm:w-auto">{s.status === "running" ? "…" : formatMs(s.ms)}</span>
                  <span className="w-14 text-right max-sm:w-auto">{s.status === "running" ? "" : formatCost(s.cost_usd)}</span>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}

/** "FIRSTNAME SURNAME · Company Limited" → name + context, for a candidate that names a person. */
function splitOption(o: ClarifyOption): { name: string; sub: string | null; person: boolean } {
  const person = /^(person|lookup):/.test(o.value) || /\//.test(o.value);
  const [name, ...rest] = o.label.split(" · ");
  return { name: person ? properName(name) : name, sub: rest.join(" · ") || null, person };
}

/** The server's candidates (people, events or slots), never the home suggestions. */
function Clarify({ turn }: { turn: AssistantTurn }) {
  const { send, busy, patchTurn } = useChat();
  const c = turn.clarify!;
  const opts = c.options.map((o) => ({ o, ...splitOption(o) }));
  const candidates = opts.some((x) => x.person);
  const pick = (o: ClarifyOption) => {
    patchTurn(turn.id, { answered: o.value });
    // A person card posts just the name; the long "name · role, company · amount" label stays on the card.
    const x = splitOption(o);
    send({ message: x.person ? x.name : o.label, choice: o.value });
  };
  return (
    <div className="mt-4 rounded-xl border bg-surface p-4 shadow-(--shadow-card) sm:p-5">
      <p className="text-[15px] leading-relaxed font-medium text-pretty text-foreground">{c.question}</p>
      {candidates ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {opts.map(({ o, name, sub, person }) => {
            const picked = turn.answered === o.value;
            return (
              <button
                key={o.value}
                type="button"
                disabled={!!turn.answered || busy}
                onClick={() => pick(o)}
                aria-pressed={picked}
                className={cn(
                  "flex min-h-14 items-center gap-3 rounded-xl border px-3.5 py-2.5 text-left transition-[border-color,background-color,opacity] duration-150",
                  picked ? "border-brand/40 bg-brand-soft" : "bg-background hover:border-brand/40 hover:bg-brand-soft/50",
                  turn.answered && !picked && "opacity-50",
                  "disabled:cursor-default",
                )}
              >
                {person ? <Avatar name={name} /> : null}
                <span className="min-w-0 flex-1">
                  <span className={cn("block truncate text-[13px] font-semibold", picked ? "text-brand-ink" : "text-foreground")}>{name}</span>
                  {sub ? <span className="block truncate text-xs text-muted-foreground">{sub}</span> : null}
                </span>
                {picked ? <Check className="size-4 shrink-0 text-brand" aria-hidden /> : <ChevronRight className="size-4 shrink-0 text-faint" aria-hidden />}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {c.options.map((o) => {
            const picked = turn.answered === o.value;
            return (
              <button
                key={o.value}
                type="button"
                disabled={!!turn.answered || busy}
                onClick={() => pick(o)}
                aria-pressed={picked}
                className={cn(
                  "inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-left text-[13px] font-medium transition-colors",
                  picked ? "border-brand/40 bg-brand-soft text-brand-ink" : "bg-background text-foreground hover:border-brand/40 hover:bg-brand-soft/60",
                  turn.answered && !picked && "opacity-50",
                  "disabled:cursor-default",
                )}
              >
                {picked ? <Check className="size-3.5" aria-hidden /> : null}
                {o.label}
              </button>
            );
          })}
        </div>
      )}
      {c.allow_free_text && !turn.answered ? <p className="mt-3 text-xs text-muted-foreground">Or type your answer in the box below.</p> : null}
    </div>
  );
}

function range(lo: number, hi: number, fmt: (n: number) => string) {
  return lo === hi ? fmt(lo) : `${fmt(lo)}–${fmt(hi)}`;
}

/** The cost preview. Nothing runs until the RM confirms; Confirm posts the confirm token. */
export function EstimateCard({ estimate, state, onConfirm, onCancel, preview = false }: { estimate: ChatEstimate; state: AssistantTurn["estimateState"]; onConfirm?: () => void; onCancel?: () => void; preview?: boolean }) {
  const { busy } = useChat();
  // The server decides who may confirm (role limits live in config/chat.py); the button only mirrors that flag.
  const blocked = estimate.can_confirm === false;
  const [lapsed, setLapsed] = useState(false);
  useEffect(() => {
    const at = expiryMs(estimate.expires_at);
    if (at == null) return;
    const left = at - Date.now();
    const t = setTimeout(() => setLapsed(true), Math.max(0, Math.min(left, 2 ** 31 - 1)));
    return () => clearTimeout(t);
  }, [estimate.expires_at]);
  const expired = !preview && lapsed && state === "open";
  const inr = estimate.cost_inr_low != null && estimate.cost_inr_high != null ? ` (₹${estimate.cost_inr_low.toFixed(2)}–₹${estimate.cost_inr_high.toFixed(2)})` : "";
  return (
    <div className={cn("overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)", !preview && "mt-4")} data-tour={preview ? undefined : "confirm"}>
      <div className="flex items-start gap-3 px-5 pt-4 pb-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-caution-soft text-caution">
          <Coins className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{blocked ? "Price preview" : "Costs money · needs your go-ahead"}</p>
          <h4 className="text-[15px] leading-snug font-semibold text-foreground">{estimate.action.title}</h4>
        </div>
      </div>
      <div className="overflow-x-auto border-y border-hairline">
        <table className="tnum w-full text-[13px] sm:min-w-[30rem]">
          <thead className="bg-surface-sunken/60 text-xs text-muted-foreground">
            <tr>
              <th className="px-5 py-2 text-left font-medium">Step</th>
              <th className="px-3 py-2 text-left font-medium max-sm:hidden">Runs on</th>
              <th className="px-3 py-2 text-right font-medium">Calls</th>
              <th className="px-5 py-2 text-right font-medium">Cost</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {estimate.breakdown.map((b) => (
              <tr key={b.step}>
                <td className="px-5 py-2 text-foreground max-sm:px-3">
                  {b.step}
                  <span className="mt-1 block sm:hidden">
                    <ModelBadge model={b.model} />
                  </span>
                </td>
                <td className="px-3 py-2 max-sm:hidden">
                  <ModelBadge model={b.model} />
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">{b.brightdata_requests !== undefined ? `${b.brightdata_requests} req.` : b.calls || "—"}</td>
                <td className="px-5 py-2 text-right text-foreground max-sm:px-3">{b.brightdata_requests !== undefined ? <span title="Counted in Bright Data requests, not dollars">$0 + requests</span> : formatCost(b.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-border">
              <td className="px-5 py-2.5 font-semibold text-foreground max-sm:hidden" colSpan={3}>
                Total
              </td>
              <td className="px-3 py-2.5 font-semibold text-foreground sm:hidden" colSpan={2}>
                Total
              </td>
              <td className="px-5 py-2.5 text-right font-semibold whitespace-nowrap text-foreground max-sm:px-3 max-sm:whitespace-normal">
                {range(estimate.cost_usd_low, estimate.cost_usd_high, formatCost)}
                {inr}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 text-xs leading-relaxed text-muted-foreground">
          <p className="inline-flex items-center gap-1.5 text-foreground">
            <Clock className="size-3.5 text-faint" aria-hidden />
            About{" "}
            {estimate.seconds_high < 90
              ? `${range(estimate.seconds_low, estimate.seconds_high, (n) => String(Math.round(n)))} s`
              : range(estimate.seconds_low, estimate.seconds_high, formatSeconds)}
          </p>
          <p className="mt-0.5 max-w-[46ch]">{estimate.basis}</p>
        </div>
        {preview ? null : state === "confirmed" ? (
          <p className="inline-flex items-center gap-1.5 text-[13px] font-medium text-positive">
            <Check className="size-4" aria-hidden /> Confirmed. Running below.
          </p>
        ) : state === "cancelled" ? (
          <p className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground">
            <Ban className="size-4" aria-hidden /> Not run. Nothing was spent.
          </p>
        ) : expired ? (
          <p className="text-[13px] text-muted-foreground">This estimate expired. Ask again for a fresh one.</p>
        ) : blocked ? (
          <p className="max-w-[40ch] text-xs text-muted-foreground sm:text-right">{estimate.blocked_reason || "Your role cannot confirm this paid action. Ask an admin."}</p>
        ) : (
          <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
            <div className="flex gap-2">
              <Button variant="ghost" onClick={onCancel} disabled={busy} className="h-9">
                Cancel
              </Button>
              <Button onClick={onConfirm} disabled={busy} className="h-9 bg-brand text-brand-foreground hover:bg-brand/90">
                <Play className="size-3.5" /> Confirm & run
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function Footer({ turn }: { turn: AssistantTurn }) {
  const d = turn.done!;
  const n = d.models.length;
  const t = d.tokens;
  const cached = t ? percent(t.cached_input, t.input) : null;
  const label = [
    n === 0 ? "No model" : `${n} ${n === 1 ? "model" : "models"}`,
    formatCost(d.total_cost_usd),
    d.seconds ? formatSeconds(d.seconds) : null,
    t && t.input ? `${formatTokens(t.input + t.output)} tokens` : null,
    cached ? `${cached}% cached` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" data-tech className="tnum mt-4 inline-flex items-center gap-1.5 rounded-md text-left text-xs text-faint transition-colors hover:text-muted-foreground">
          <Coins className="size-3.5" aria-hidden />
          {label}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="start" className="tnum">
        {n === 0 ? (
          "Answered by code only: no model was called."
        ) : (
          <div className="space-y-1.5">
            <ul className="space-y-0.5">
              {d.models.map((m) => (
                <li key={m.model}>
                  {modelLabel(m.model)} · {m.calls} {m.calls === 1 ? "call" : "calls"} · {formatCost(m.cost_usd)}
                </li>
              ))}
            </ul>
            {t ? (
              <p className="border-t border-background/15 pt-1.5">
                {formatTokens(t.input)} in · {formatTokens(t.output)} out · {formatTokens(t.cached_input)} reused from cache
                {d.saved_usd_by_cache ? ` · saved ${formatCost(d.saved_usd_by_cache)}` : ""}
              </p>
            ) : null}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

export function AssistantTurnView({ turn, asOf, onRetry }: { turn: AssistantTurn; asOf?: string; onRetry?: () => void }) {
  const { send, patchTurn, busy } = useChat();
  return (
    <div className="flex gap-3 sm:gap-4">
      <BrandMark className="mt-0.5 size-7 shrink-0 max-sm:size-6" />
      <div className="min-w-0 flex-1">
        <StepTimeline turn={turn} />
        {turn.text && !turn.clarify ? (
          <div className="mt-3">
            <Prose text={turn.text} streaming={turn.streaming} />
          </div>
        ) : null}
        {turn.clarify ? <Clarify turn={turn} /> : null}
        {turn.estimate ? (
          <EstimateCard
            estimate={turn.estimate}
            state={turn.estimateState}
            onConfirm={() => {
              // "Confirmed" shows only once the server has started the run; an expired or refused confirm leaves the card open.
              send({ message: "", confirmToken: turn.estimate!.confirm_token, display: null, onStarted: () => patchTurn(turn.id, { estimateState: "confirmed" }) });
            }}
            onCancel={() => patchTurn(turn.id, { estimateState: "cancelled" })}
          />
        ) : null}
        {turn.cards.map((c, i) => (
          <ChatCardView key={`${c.kind}-${i}`} card={c} asOf={asOf} />
        ))}
        {turn.error ? (
          <div role="alert" className="mt-4 flex items-start gap-3 rounded-xl border border-negative/20 bg-negative-soft/60 px-4 py-3">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-negative" aria-hidden />
            <div className="min-w-0 flex-1 text-sm leading-relaxed text-foreground">{turn.error}</div>
            {onRetry ? (
              <Button variant="outline" size="sm" onClick={onRetry} disabled={busy} className="shrink-0">
                <RotateCw /> Try again
              </Button>
            ) : null}
          </div>
        ) : null}
        {turn.note ? <p className="mt-3 text-xs text-muted-foreground">{turn.note}</p> : null}
        {turn.done && !turn.streaming ? <Footer turn={turn} /> : null}
      </div>
    </div>
  );
}
