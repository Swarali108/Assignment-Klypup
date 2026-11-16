"use client";

import { ModelTools } from "./model-picker";
import { Layers, User, X } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatTokens, percent, type ChatContext, type ChatFocus } from "@/lib/chat";
import { properName, shortCompany } from "@/lib/call-script";
import { cn } from "@/lib/utils";
import { useChat } from "./chat-store";

export function focusLabel(f: ChatFocus) {
  return f.kind === "person" ? properName(f.label) : shortCompany(f.label);
}

/** "Talking about: <person> ✕" — the people or events a follow-up like "him" binds to. */
export function FocusChips({ focus, onDrop, disabled, label = true }: { focus: ChatFocus[]; onDrop?: (f: ChatFocus) => void; disabled?: boolean; label?: boolean }) {
  if (!focus.length) return null;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5" aria-label="Talking about">
      {label ? <span className="text-xs text-muted-foreground max-sm:sr-only">Talking about</span> : null}
      {focus.map((f) => {
        const Icon = f.kind === "person" ? User : Layers;
        const name = focusLabel(f);
        return (
          <span
            key={`${f.kind}:${f.event_id}:${f.person_id ?? ""}`}
            className="inline-flex h-6 max-w-[16rem] items-center gap-1 rounded-full bg-brand-soft pr-0.5 pl-2 text-xs font-medium text-brand-ink ring-1 ring-brand/15 ring-inset"
          >
            <Icon className="size-3 shrink-0" aria-hidden />
            <span className="truncate">{name}</span>
            {onDrop ? (
              <button
                type="button"
                disabled={disabled}
                onClick={() => onDrop(f)}
                aria-label={`Stop talking about ${name}`}
                className="grid size-5 shrink-0 place-items-center rounded-full text-brand-ink/70 transition-colors hover:bg-brand/10 hover:text-brand-ink disabled:opacity-40"
              >
                <X className="size-3" />
              </button>
            ) : (
              <span className="w-1" />
            )}
          </span>
        );
      })}
    </div>
  );
}

/** "Context 2.4k tokens · 71% cached · compressed 1×", with a meter of the cached share and the detail on hover. */
export function ContextMeter({ context, compressions, className }: { context: ChatContext; compressions: number; className?: string }) {
  const cached = percent(context.cached_tokens, context.prompt_tokens);
  const saved = context.history_tokens_before - context.history_tokens_after;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-tech
          className={cn("tnum inline-flex h-6 shrink-0 items-center gap-2 rounded-md px-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground", className)}
          aria-label={`Context ${formatTokens(context.prompt_tokens)} tokens${cached !== null ? `, ${cached}% cached` : ""}${compressions ? `, compressed ${compressions} times` : ""}`}
        >
          <span className="relative h-1.5 w-8 overflow-hidden rounded-full bg-border" aria-hidden>
            <span className="absolute inset-y-0 left-0 rounded-full bg-brand" style={{ width: `${cached ?? 0}%` }} />
          </span>
          <span>
            <span className="max-sm:hidden">Context </span>
            {formatTokens(context.prompt_tokens)}
            <span className="max-sm:hidden"> tokens</span>
            {cached !== null ? ` · ${cached}% cached` : ""}
            {compressions ? <span className="max-sm:hidden"> · compressed {compressions}×</span> : null}
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" align="end" className="tnum w-72 max-w-[calc(100vw-2rem)]">
        <div className="w-full">
        <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-0.5">
          <dt>Sent to the model</dt>
          <dd className="text-right">{formatTokens(context.prompt_tokens)} tokens</dd>
          <dt>Reused from cache</dt>
          <dd className="text-right">
            {formatTokens(context.cached_tokens)}
            {cached !== null ? ` (${cached}%)` : ""}
          </dd>
          <dt>Conversation so far</dt>
          <dd className="text-right">
            {context.compressed ? `${formatTokens(context.history_tokens_before)} → ${formatTokens(context.history_tokens_after)}` : formatTokens(context.history_tokens_after)}
          </dd>
          {context.turns_kept ? (
            <>
              <dt>Recent turns kept word for word</dt>
              <dd className="text-right">{context.turns_kept}</dd>
            </>
          ) : null}
        </dl>
        <p className="mt-1.5 border-t border-background/15 pt-1.5">
          {compressions
            ? `Older turns were summarised ${compressions}× to keep the context small${context.compressed && saved > 0 ? ` (${formatTokens(saved)} tokens saved this turn)` : ""}.`
            : "The fixed instructions come first on every turn, so they are reused from cache."}
        </p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/** The strip inside the composer: focus on the left, context on the right. Renders nothing before the first answer. */
export function ComposerContext() {
  const { focus, dropFocus, context, compressions, busy } = useChat();
  return (
    <div className="mr-14 ml-3 flex min-h-10 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-hairline py-1.5">
      <div className="flex min-w-0 flex-wrap items-center gap-x-2">
        <ModelTools />
        <FocusChips focus={focus} onDrop={dropFocus} disabled={busy} />
      </div>
      {context ? <ContextMeter context={context} compressions={compressions} className="ml-auto" /> : null}
    </div>
  );
}
