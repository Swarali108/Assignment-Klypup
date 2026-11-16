"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ChevronRight, Coins, MessageSquareOff, MessageSquareText, Minimize2, UserRound } from "lucide-react";
import { EmptyState, ErrorState, SkeletonCard, SkeletonText } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ContextColumns, TokenLegend } from "@/components/charts/token-charts";
import { EstimateCard, ModelBadge, StepTimeline } from "@/components/tower/assistant-turn";
import { ChatCardView } from "@/components/tower/chat-cards";
import { fromStored, useChat, type AssistantTurn } from "@/components/tower/chat-store";
import { FocusChips } from "@/components/tower/context-bar";
import { DownloadMenu } from "@/components/tower/download-menu";
import { Prose } from "@/components/tower/prose";
import { api } from "@/lib/api";
import { chatApi, formatCost, formatSeconds, formatTokens, modelLabel, percent, type StoredConversation, type StoredMessage } from "@/lib/chat";
import { conversationPrintHref, downloadConversationMarkdown } from "@/lib/exports";
import { cn } from "@/lib/utils";
import { exchanges, totals, when } from "./thread";

function Back() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
      <Link href="/history">
        <ArrowLeft /> All conversations
      </Link>
    </Button>
  );
}

/** /history/[id]: every message with what it cost and what the model was given. */
export function ThreadView({ id }: { id: string }) {
  const [state, setState] = useState<{ status: "loading" } | { status: "error"; reason: string; missing: boolean } | { status: "ready"; c: StoredConversation }>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [asOf, setAsOf] = useState<string | undefined>();
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    chatApi
      .conversation(id)
      .then((c) => live && setState({ status: "ready", c }))
      .catch((err) => {
        const reason = (err as Error).message;
        if (live) setState({ status: "error", reason, missing: /404|not found|no such/i.test(reason) });
      });
    api
      .summary()
      .then((s) => live && setAsOf(s.as_of))
      .catch(() => {});
    const t = setTimeout(() => setNow(Date.now()), 0);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [id, attempt]);

  if (state.status === "loading") return <ThreadSkeleton />;
  if (state.status === "error")
    return (
      <div className="space-y-6">
        <Back />
        {state.missing ? (
          <EmptyState icon={MessageSquareOff} title="This conversation is not here" action={<Button asChild variant="outline"><Link href="/history">See all conversations</Link></Button>}>
            It may have been deleted, or it belongs to another account.
          </EmptyState>
        ) : (
          <ErrorState title="This conversation could not load" reason={state.reason} onRetry={() => setAttempt((a) => a + 1)} />
        )}
      </div>
    );
  return <Thread c={state.c} asOf={asOf} now={now} />;
}

function Thread({ c, asOf, now }: { c: StoredConversation; asOf?: string; now: number | null }) {
  const { open } = useChat();
  const router = useRouter();
  const xs = useMemo(() => exchanges(c.messages), [c.messages]);
  const t = useMemo(() => totals(c), [c]);
  const turns = useMemo(() => {
    const assistants = c.messages.filter((m) => m.role === "assistant");
    const built = fromStored(assistants) as AssistantTurn[];
    return new Map(assistants.map((m, i) => [m, built[i]]));
  }, [c.messages]);
  const columns = xs
    .filter((x) => x.answer?.meta?.context_tokens !== undefined)
    .map((x) => ({
      key: x.key,
      label: String(x.n),
      total: x.answer!.meta!.context?.prompt_tokens ?? x.answer!.meta!.tokens_in ?? x.answer!.meta!.context_tokens!,
      // The provider's own cached count for the turn, as stored.
      cached: x.answer!.meta!.context?.cached_tokens ?? x.answer!.meta!.cached_in ?? 0,
      compressed: !!x.answer!.meta!.compressed,
      cost: x.answer!.meta!.cost_usd ?? null,
      question: x.question?.text,
    }));
  const cachedPct = percent(t.cachedIn, t.tokensIn);
  const started = c.created_at ?? c.messages[0]?.created_at;
  const last = c.updated_at ?? c.messages.at(-1)?.created_at;

  return (
    <div className="space-y-8">
      <Back />
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h1 className="text-[1.75rem] leading-tight font-semibold tracking-[-0.02em] text-balance text-foreground">{c.title}</h1>
          <p className="tnum mt-1.5 text-sm text-muted-foreground">
            {[started && now ? `Started ${when(started, now)}` : null, last && now ? `last active ${when(last, now)}` : null, `${t.questions} ${t.questions === 1 ? "question" : "questions"}`].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <DownloadMenu what="conversation" size="default" pdfHref={conversationPrintHref(c.id)} onMarkdown={() => downloadConversationMarkdown(c.id, c.title)} />
          <Button
            onClick={() => {
              void open(c.id);
              router.push("/");
            }}
          >
            <MessageSquareText /> Continue
          </Button>
        </div>
      </header>

      <section data-tech aria-label="What this conversation cost" className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
        <dl className="tnum grid grid-cols-2 gap-px border-b border-hairline bg-hairline sm:grid-cols-3 lg:grid-cols-6 [&>div]:bg-surface">
          <Ledger label="Total cost" value={t.measured ? formatCost(t.cost) : "—"} sub={t.measured ? `${formatCost(t.measured ? t.cost / t.measured : 0)} per answer` : "Not recorded"} strong />
          <Ledger label="Tokens in / out" value={t.measured ? `${formatTokens(t.tokensIn)} / ${formatTokens(t.tokensOut)}` : "—"} sub="Across every model call" />
          <Ledger label="Reused from cache" value={cachedPct !== null ? `${cachedPct}%` : "—"} sub={t.measured ? `${formatTokens(t.cachedIn)} input tokens` : "Not recorded"} />
          <Ledger label="Summarised" value={t.measured ? `${t.compressions}×` : "—"} sub={t.compressions ? "Older turns, to keep context small" : "Context stayed under the limit"} />
          <Ledger label="Answer time" value={t.measured && t.seconds ? formatSeconds(t.seconds) : "—"} sub="All answers together" />
          <div className="px-5 py-4">
            <dt className="text-xs text-muted-foreground">Models</dt>
            <dd className="mt-2 flex flex-wrap gap-1.5">
              {t.models.length ? t.models.map((m) => <ModelBadge key={m.model} model={m.model} />) : <span className="text-sm text-muted-foreground">{t.measured ? "Code only" : "—"}</span>}
            </dd>
          </div>
        </dl>
        {columns.length ? (
          <div className="px-5 pt-4 pb-4 sm:px-6">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Context sent per answer</h2>
                <p className="text-xs text-muted-foreground">The fixed instructions go first, so from the second answer on they come from cache. Long threads are summarised.</p>
              </div>
              <TokenLegend compressed={columns.some((x) => x.compressed)} />
            </div>
            <ContextColumns turns={columns} onSelect={(key) => document.getElementById(key)?.scrollIntoView({ behavior: "smooth", block: "start" })} />
            <p className="mt-1 text-center text-[11px] text-faint">Answer</p>
          </div>
        ) : (
          <p className="px-5 py-4 text-xs text-muted-foreground">Token use is recorded from the next answer on; earlier answers in this conversation were not measured.</p>
        )}
      </section>

      <ol className="space-y-6">
        {xs.map((x) => (
          <li key={x.key} id={x.key} className="scroll-mt-24">
            {x.answer?.meta?.compressed ? (
              <div className="mb-6 flex items-center gap-3 text-xs text-muted-foreground" role="separator">
                <span className="h-px flex-1 bg-border" />
                <span className="inline-flex items-center gap-1.5 rounded-full border bg-surface px-3 py-1 font-medium text-foreground">
                  <Minimize2 className="size-3.5" aria-hidden /> Compressed here
                </span>
                <span className="max-sm:hidden">earlier turns summarised by the cheap model, no new numbers</span>
                <span className="h-px flex-1 bg-border" />
              </div>
            ) : null}
            <Exchange n={x.n} question={x.question} answer={x.answer} turn={x.answer ? turns.get(x.answer) : undefined} asOf={asOf} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function Ledger({ label, value, sub, strong }: { label: string; value: string; sub?: string; strong?: boolean }) {
  return (
    <div className="px-5 py-4">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("mt-1 text-lg leading-tight font-semibold text-foreground", strong && "text-[1.35rem]")}>{value}</dd>
      {sub ? <dd className="mt-0.5 truncate text-xs text-faint">{sub}</dd> : null}
    </div>
  );
}

function Exchange({ n, question, answer, turn, asOf }: { n: number; question: StoredMessage | null; answer: StoredMessage | null; turn?: AssistantTurn; asOf?: string }) {
  return (
    <article className="grid overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card) lg:grid-cols-[minmax(0,1fr)_17rem] [html[data-boardroom]_&]:lg:grid-cols-1">
      <div className="min-w-0 p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="tnum mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-secondary text-[11px] font-semibold text-muted-foreground">{n}</span>
          <p className="min-w-0 text-[15px] leading-relaxed font-semibold text-pretty text-foreground">
            {question?.text?.trim() || <span className="font-normal text-muted-foreground">{answer?.estimate || answer?.steps?.length ? "Confirmed the run" : "Picked an option"}</span>}
          </p>
        </div>
        {answer && turn ? (
          <div className="mt-4 space-y-3 pl-9">
            <StepTimeline turn={turn} defaultOpen={false} />
            {answer.clarify ? (
              <div className="rounded-lg border bg-surface-sunken/50 p-3.5">
                <p className="text-sm font-medium text-foreground">{answer.clarify.question}</p>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {answer.clarify.options.map((o) => (
                    <li key={o.value} className="rounded-full border bg-surface px-2.5 py-0.5 text-xs text-foreground/85">
                      {o.label}
                    </li>
                  ))}
                </ul>
              </div>
            ) : answer.text ? (
              <Prose text={answer.text} />
            ) : null}
            <Attachments answer={answer} asOf={asOf} />
          </div>
        ) : (
          <p className="mt-3 pl-9 text-sm text-muted-foreground">No answer was stored for this question (it was stopped or failed).</p>
        )}
      </div>
      {answer ? <MetaPanel meta={answer.meta} /> : <div data-tech className="hidden border-l border-hairline bg-surface-sunken/40 lg:block" />}
    </article>
  );
}

/** Cards and cost previews stay folded in the thread so the conversation reads as a log; one click opens them. */
function Attachments({ answer, asOf }: { answer: StoredMessage; asOf?: string }) {
  const [open, setOpen] = useState(false);
  const cards = answer.cards ?? [];
  const names = cards.map((c) => c.title);
  const preview = !!answer.estimate;
  if (!names.length && !preview) return null;
  const total = names.length + (preview ? 1 : 0);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        // A cost preview is a price, so with only that attached the whole button goes in boardroom mode.
        data-tech={names.length ? undefined : ""}
        className="inline-flex max-w-full items-center gap-1.5 rounded-md py-0.5 text-left text-xs font-medium text-brand-ink hover:underline"
      >
        <ChevronRight className={cn("size-3.5 shrink-0 transition-transform duration-200", open && "rotate-90")} aria-hidden />
        <span className="truncate">
          {open ? "Hide" : "Show"}{" "}
          {total === 1 ? (names[0] ?? "Cost preview") : `${total} attachments: `}
          {total > 1 && preview ? <span data-tech>Cost preview{names.length ? " · " : ""}</span> : null}
          {total > 1 ? names.join(" · ") : null}
        </span>
      </button>
      {open ? (
        <div>
          {answer.estimate ? (
            <div data-tech className="mt-3">
              <EstimateCard estimate={answer.estimate} state="cancelled" preview />
            </div>
          ) : null}
          {cards.map((card, i) => (
            <ChatCardView key={`${card.kind}-${i}`} card={card} asOf={asOf} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function MetaPanel({ meta }: { meta: StoredMessage["meta"] }) {
  if (!meta) {
    return (
      <aside data-tech className="border-t border-hairline bg-surface-sunken/40 px-5 py-4 text-xs leading-relaxed text-muted-foreground lg:border-t-0 lg:border-l">
        <p className="flex items-center gap-1.5 font-medium text-foreground">
          <Coins className="size-3.5 text-faint" aria-hidden /> Not measured
        </p>
        <p className="mt-1">This answer was given before token use was recorded.</p>
      </aside>
    );
  }
  const cached = percent(meta.cached_in, meta.tokens_in);
  return (
    <aside data-tech className="tnum border-t border-hairline bg-surface-sunken/40 px-5 py-4 text-[13px] lg:border-t-0 lg:border-l" aria-label="What this answer cost">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-muted-foreground">Cost</span>
        <span className="text-lg font-semibold text-foreground">{formatCost(meta.cost_usd)}</span>
      </div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs max-lg:grid-cols-[auto_1fr_auto_1fr]">
        <dt className="text-muted-foreground">Tokens in</dt>
        <dd className="text-right text-foreground">{formatTokens(meta.tokens_in)}</dd>
        <dt className="text-muted-foreground">Tokens out</dt>
        <dd className="text-right text-foreground">{formatTokens(meta.tokens_out)}</dd>
        <dt className="text-muted-foreground">From cache</dt>
        <dd className="text-right text-foreground">{cached !== null ? `${cached}%` : "—"}</dd>
        <dt className="text-muted-foreground">Context</dt>
        <dd className="text-right text-foreground">{formatTokens(meta.context_tokens)}</dd>
        {meta.seconds ? (
          <>
            <dt className="text-muted-foreground">Time</dt>
            <dd className="text-right text-foreground">{formatSeconds(meta.seconds)}</dd>
          </>
        ) : null}
      </dl>
      {cached !== null ? (
        <div className="mt-2 flex h-1.5 overflow-hidden rounded-full" aria-hidden>
          <span className="h-full bg-brand" style={{ width: `${cached}%` }} />
          {cached < 100 ? <span className={cn("h-full flex-1 bg-chart-5 dark:bg-faint", cached > 0 && "ml-[2px]")} /> : null}
        </div>
      ) : null}
      <div className="mt-4 border-t border-hairline pt-3">
        <p className="mb-1.5 text-xs text-muted-foreground">Models</p>
        {meta.models?.length ? (
          <ul className="space-y-1">
            {meta.models.map((m) => (
              <li key={m.model} className="flex items-center justify-between gap-2 text-xs">
                <span className="min-w-0 truncate text-foreground" title={m.model}>
                  {modelLabel(m.model)} <span className="text-muted-foreground">× {m.calls}</span>
                </span>
                <span className="text-muted-foreground">{formatCost(m.cost_usd)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-foreground">Code only, no model called</p>
        )}
      </div>
      {meta.focus?.length ? (
        <div className="mt-4 border-t border-hairline pt-3">
          <p className="mb-1.5 flex items-center gap-1 text-xs text-muted-foreground">
            <UserRound className="size-3" aria-hidden /> Focus after this answer
          </p>
          <FocusChips focus={meta.focus} label={false} />
        </div>
      ) : null}
    </aside>
  );
}

function ThreadSkeleton() {
  return (
    <div className="space-y-8" role="status" aria-label="Loading the conversation">
      <Skeleton className="h-8 w-40" />
      <div className="space-y-2">
        <Skeleton className="h-8 w-96 max-w-full" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="h-64 rounded-xl" />
      <SkeletonCard />
      <SkeletonText lines={4} />
    </div>
  );
}
