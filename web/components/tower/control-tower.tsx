"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowDown, Banknote, History, Link2, Loader2, Sparkles, UserSearch } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSession } from "@/lib/session";
import { api } from "@/lib/api";
import { CHAT_MOCK } from "@/lib/chat";
import { conversationPrintHref, downloadConversationMarkdown } from "@/lib/exports";
import { Button } from "@/components/ui/button";
import { Briefing } from "./briefing";
import { DateLine } from "@/components/home/date-line";
import { PREFILL_EVENT, PREFILL_KEY } from "@/lib/brief";
import { Composer, type ComposerHandle } from "./composer";
import { AssistantTurnView } from "./assistant-turn";
import { useChat, type AssistantTurn } from "./chat-store";
import { ComposerContext } from "./context-bar";
import { DownloadMenu } from "./download-menu";

/** Above an open conversation: its title (small screens), the full thread with costs, and downloads. */
function ConversationBar() {
  const { activeId, title } = useChat();
  if (!activeId) return <div className="h-12" />;
  return (
    <div className="flex h-12 items-center gap-2 px-4 sm:px-6">
      <p className="min-w-0 flex-1 truncate text-sm font-medium text-foreground lg:invisible">{title ?? "New conversation"}</p>
      <Button asChild variant="ghost" size="sm" className="text-muted-foreground">
        <Link href={`/history/${encodeURIComponent(activeId)}`}>
          <History />
          <span className="max-sm:hidden">Thread details</span>
        </Link>
      </Button>
      <DownloadMenu
        what="conversation"
        variant="ghost"
        className="text-muted-foreground"
        pdfHref={conversationPrintHref(activeId)}
        onMarkdown={() => downloadConversationMarkdown(activeId, title ?? undefined)}
      />
    </div>
  );
}

/** The four suggestions from the chat contract. */
export const SUGGESTIONS = [
  { label: "Who came into money this week?", icon: Sparkles },
  { label: "What money does Manish Sharma have?", icon: UserSearch },
  { label: "Cash in hand above ₹50 Cr", icon: Banknote },
  { label: "Process a new IPO from a link", icon: Link2 },
] as const;

function greeting(hour: number) {
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

function useHour() {
  const [hour, setHour] = useState<number | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setHour(new Date().getHours()), 0);
    return () => clearTimeout(t);
  }, []);
  return hour;
}

function EmptyHome({ onSend }: { onSend: (text: string) => void }) {
  const { user, can } = useSession();
  const hour = useHour();
  const { busy } = useChat();
  const first = user?.name.split(" ")[0];
  const composer = useRef<ComposerHandle>(null);

  // "Ask about this" in the daily brief leaves its question here; the composer is filled, never sent.
  useEffect(() => {
    const take = () => {
      try {
        const text = window.sessionStorage.getItem(PREFILL_KEY);
        if (!text) return;
        window.sessionStorage.removeItem(PREFILL_KEY);
        composer.current?.fill(text);
      } catch {
        /* nothing to fill */
      }
    };
    const t = setTimeout(take, 60);
    window.addEventListener(PREFILL_EVENT, take);
    return () => {
      clearTimeout(t);
      window.removeEventListener(PREFILL_EVENT, take);
    };
  }, []);
  return (
    <div className="mx-auto flex w-full max-w-[46rem] flex-1 flex-col justify-center px-4 pt-10 pb-12 sm:px-6 lg:pt-14">
      <div className="mb-7 text-center sm:mb-8">
        <DateLine />
        <h1 className="text-[1.75rem] leading-tight font-semibold tracking-[-0.025em] text-balance text-foreground sm:text-[2.125rem]">
          {hour === null || !first ? <span className="invisible">Good morning</span> : `${greeting(hour)}, ${first}.`}
        </h1>
        <p className="mx-auto mt-2 max-w-[44ch] text-[15px] leading-relaxed text-pretty text-muted-foreground">
          Ask who came into money, how much, and why it is worth a call. Lookups are free; anything that costs money shows its price first.
        </p>
      </div>
      <Composer
        ref={composer}
        size="lg"
        busy={busy}
        onSend={onSend}
        footer={<ComposerContext />}
        disabled={!can("view")}
        placeholder={first ? `Ask anything, ${first}…` : "Ask anything…"}
      />
      <div className="mt-3.5 flex flex-wrap justify-center gap-2" aria-label="Suggestions">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.label}
            type="button"
            onClick={() => onSend(s.label)}
            className="inline-flex min-h-9 items-center gap-2 rounded-full border bg-surface px-3.5 py-1.5 text-[13px] text-foreground/85 shadow-(--shadow-card) transition-colors hover:border-brand/35 hover:bg-brand-soft/50 hover:text-foreground"
          >
            <s.icon className="size-3.5 text-brand" aria-hidden />
            {s.label}
          </button>
        ))}
      </div>
      <div className="mt-10 sm:mt-12">
        <Briefing />
      </div>
    </div>
  );
}

/** Home: ChatGPT-familiar control tower. Empty state with greeting + briefing; then the conversation. */
export function ControlTower() {
  const { turns, send, stop, busy, loading } = useChat();
  const [asOf, setAsOf] = useState<string | undefined>();
  const scroller = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const lastUser = [...turns].reverse().find((t) => t.kind === "user");

  useEffect(() => {
    api
      .summary()
      .then((s) => setAsOf(s.as_of))
      .catch(() => {});
  }, []);

  // Follow the answer as it streams, unless the RM scrolled up to read.
  useEffect(() => {
    const el = scroller.current;
    if (el && pinned) el.scrollTo({ top: el.scrollHeight });
  }, [turns, pinned]);

  const onSend = (text: string) => send({ message: text });

  if (!turns.length && !loading) {
    return (
      <div className="flex flex-1 flex-col overflow-y-auto">
        <EmptyHome onSend={onSend} />
        {CHAT_MOCK ? <p className="pb-4 text-center text-[11px] text-faint">Preview mode: answers are replayed from the call list.</p> : null}
      </div>
    );
  }

  return (
    <div className="relative flex h-[calc(100dvh-3.5rem)] flex-col">
      <ConversationBar />
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
        }}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        <div className="mx-auto w-full max-w-[52rem] space-y-8 px-4 pt-2 pb-10 sm:px-6">
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden /> Opening the conversation…
            </p>
          ) : null}
          {turns.map((t) =>
            t.kind === "user" ? (
              <div key={t.id} className="flex justify-end">
                <p className="max-w-[min(36rem,85%)] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-foreground">{t.text}</p>
              </div>
            ) : (
              <AssistantTurnView
                key={t.id}
                turn={t as AssistantTurn}
                asOf={asOf}
                onRetry={lastUser ? () => send({ message: lastUser.text }) : undefined}
              />
            ),
          )}
        </div>
      </div>
      {!pinned ? (
        <button
          type="button"
          onClick={() => {
            setPinned(true);
            scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
          }}
          aria-label="Scroll to the latest answer"
          className="absolute bottom-28 left-1/2 grid size-9 -translate-x-1/2 place-items-center rounded-full border bg-surface text-muted-foreground shadow-(--shadow-raised) hover:text-foreground"
        >
          <ArrowDown className="size-4" />
        </button>
      ) : null}
      <div className={cn("border-t border-transparent bg-background px-4 pt-2 pb-4 sm:px-6")}>
        <div className="mx-auto w-full max-w-[52rem]">
          <Composer busy={busy} onSend={onSend} onStop={stop} placeholder="Ask a follow-up…" footer={<ComposerContext />} />
          <p className="mt-2 text-center text-[11px] text-faint">Every number is checked against the filings. Paid work always asks first.</p>
        </div>
      </div>
    </div>
  );
}
