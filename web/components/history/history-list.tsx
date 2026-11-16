"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowDownWideNarrow, CircleDollarSign, Clock3, MessagesSquare, MessageSquareText, Search, SearchX, X } from "lucide-react";
import { EmptyState, ErrorState, SkeletonList, StatCard, StatStrip } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { useChat } from "@/components/tower/chat-store";
import { chatApi, formatCost, type Conversation } from "@/lib/chat";
import { cn } from "@/lib/utils";
import { when } from "./thread";

type Sort = "recent" | "cost";

function useNow() {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setNow(Date.now()), 0);
    const i = setInterval(() => setNow(Date.now()), 60_000);
    return () => {
      clearTimeout(t);
      clearInterval(i);
    };
  }, []);
  return now;
}

/** /history: every conversation, searchable (titles and message text), sorted by recent or by cost. */
export function HistoryList() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState<Sort>("recent");
  const [state, setState] = useState<{ status: "loading" } | { status: "error"; reason: string } | { status: "ready"; items: Conversation[]; q: string }>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const now = useNow();
  const { open } = useChat();
  const router = useRouter();

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 220);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    let live = true;
    chatApi
      .conversations(debounced)
      .then((items) => live && setState({ status: "ready", items, q: debounced }))
      .catch((err) => live && setState({ status: "error", reason: (err as Error).message }));
    return () => {
      live = false;
    };
  }, [debounced, attempt]);

  const all = useMemo(() => (state.status === "ready" ? state.items : []), [state]);
  // A server without search returns every conversation (and no message counts): narrow by title here.
  const serverSearches = all.some((c) => c.messages !== undefined);
  const shown = useMemo(() => {
    const needle = state.status === "ready" ? state.q.toLowerCase() : "";
    const list = needle && !serverSearches ? all.filter((c) => c.title.toLowerCase().includes(needle)) : all;
    return [...list].sort((a, b) => (sort === "cost" ? (b.cost_usd ?? -1) - (a.cost_usd ?? -1) : b.updated_at.localeCompare(a.updated_at)));
  }, [all, sort, serverSearches, state]);

  const hasCost = all.some((c) => c.cost_usd !== undefined);
  const spent = all.reduce((s, c) => s + (c.cost_usd ?? 0), 0);
  const messages = all.reduce((s, c) => s + (c.messages ?? 0), 0);

  const continueChat = (id: string) => {
    void open(id);
    router.push("/");
  };

  return (
    <div className="space-y-8">
      {state.status === "ready" && !state.q && all.length ? (
        <StatStrip>
          <StatCard label="Conversations" icon={MessagesSquare} value={String(all.length)} sub="Yours only, newest first" />
          <StatCard label="Messages" icon={MessageSquareText} value={hasCost ? String(messages) : "—"} sub={hasCost ? "Questions and answers" : "Counted from the next answer on"} />
          <StatCard label="Spent on answers" icon={CircleDollarSign} value={hasCost ? formatCost(spent) : "—"} sub={hasCost ? "Every model call, every conversation" : "Recorded from the next answer on"} />
          <StatCard
            label="Average per conversation"
            icon={Clock3}
            value={hasCost && all.length ? formatCost(spent / all.length) : "—"}
            sub={hasCost ? "Lookups run on code and cost nothing" : "Recorded from the next answer on"}
          />
        </StatStrip>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex-1">
          <span className="sr-only">Search conversations</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" aria-hidden />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search questions, answers and names"
            className="h-10 w-full rounded-lg border bg-surface pr-9 pl-9 text-sm text-foreground shadow-(--shadow-card) outline-none placeholder:text-faint focus-visible:border-brand/40 focus-visible:shadow-[0_0_0_3px_var(--brand-soft)] [&::-webkit-search-cancel-button]:hidden"
          />
          {q ? (
            <button type="button" onClick={() => setQ("")} aria-label="Clear search" className="absolute top-1/2 right-2 grid size-6 -translate-y-1/2 place-items-center rounded-md text-faint hover:bg-secondary hover:text-foreground">
              <X className="size-3.5" />
            </button>
          ) : null}
        </label>
        <div role="radiogroup" aria-label="Sort conversations" className="inline-flex h-10 shrink-0 items-center gap-0.5 self-start rounded-lg border bg-surface-sunken p-1 sm:self-auto">
          <ArrowDownWideNarrow className="mx-1.5 size-4 text-faint" aria-hidden />
          {(["recent", "cost"] as const).map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={sort === s}
              onClick={() => setSort(s)}
              disabled={s === "cost" && !hasCost}
              className={cn(
                "h-8 rounded-md px-3 text-[13px] font-medium transition-colors disabled:opacity-40",
                sort === s ? "bg-surface text-foreground shadow-(--shadow-card) ring-1 ring-border" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {s === "recent" ? "Most recent" : "Highest cost"}
            </button>
          ))}
        </div>
      </div>

      {state.status === "loading" ? (
        <SkeletonList rows={5} />
      ) : state.status === "error" ? (
        <ErrorState title="Conversations could not load" reason={state.reason} onRetry={() => setAttempt((a) => a + 1)} />
      ) : shown.length === 0 ? (
        state.q ? (
          <EmptyState icon={SearchX} title={`Nothing matches “${state.q}”`} action={<Button variant="outline" onClick={() => setQ("")}>Clear the search</Button>}>
            Search looks through conversation titles{serverSearches ? ", every question and every answer" : ""}. Try a person&rsquo;s or a company&rsquo;s name.
          </EmptyState>
        ) : (
          <EmptyState icon={MessagesSquare} title="No conversations yet" tone="brand" action={<Button asChild><Link href="/">Ask a question</Link></Button>}>
            Every question you ask in the control tower is kept here, with what each answer cost and which models wrote it.
          </EmptyState>
        )
      ) : (
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <div className="hidden grid-cols-[minmax(0,1fr)_7rem_6rem_7.5rem_2rem] gap-x-4 border-b border-hairline bg-surface-sunken/50 px-5 py-2 text-xs font-medium text-muted-foreground sm:grid">
            <span>Conversation</span>
            <span className="text-right">Messages</span>
            <span className="text-right">Cost</span>
            <span className="text-right">Last active</span>
            <span />
          </div>
          <ul className="divide-y divide-hairline">
            {shown.map((c) => (
              <li key={c.id} className="group/row relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 px-4 py-3.5 transition-colors hover:bg-accent/50 sm:grid-cols-[minmax(0,1fr)_7rem_6rem_7.5rem_2rem] sm:px-5">
                <div className="min-w-0">
                  <Link
                    href={`/history/${encodeURIComponent(c.id)}`}
                    className="block truncate text-[14px] font-medium text-foreground after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
                  >
                    {c.title}
                  </Link>
                  <p className="tnum truncate text-xs text-muted-foreground sm:hidden">
                    {[c.messages !== undefined ? `${c.messages} messages` : null, now ? when(c.updated_at, now) : null].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <span className="tnum hidden text-right text-[13px] text-muted-foreground sm:block">{c.messages ?? "—"}</span>
                <span className="tnum text-right text-[13px] font-semibold text-foreground">{c.cost_usd !== undefined ? formatCost(c.cost_usd) : <span className="font-normal text-faint">—</span>}</span>
                <span className="tnum hidden text-right text-xs text-muted-foreground sm:block">{now ? when(c.updated_at, now) : ""}</span>
                <div className="relative z-10 hidden justify-end sm:flex">
                  <button
                    type="button"
                    onClick={() => continueChat(c.id)}
                    aria-label={`Continue “${c.title}” in the control tower`}
                    title="Continue in the control tower"
                    className="grid size-7 place-items-center rounded-md text-faint opacity-0 transition-opacity group-hover/row:opacity-100 hover:bg-surface hover:text-foreground focus-visible:opacity-100"
                  >
                    <MessageSquareText className="size-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
