"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  CalendarDays,
  CornerDownLeft,
  HeartPulse,
  History,
  Layers,
  Loader2,
  MessageSquareText,
  Network,
  PhoneCall,
  RadioTower,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
  ClipboardCheck,
  Sparkles,
  Target,
  User,
} from "lucide-react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  ASK_EXAMPLES,
  AskError,
  AskLoading,
  AskNoMatch,
  AskPersonRow,
  AskSummary,
} from "@/components/ask/ask-results";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { formatCr } from "@/lib/format";
import type { AskResponse, CallItem } from "@/lib/types";

type Ctx = {
  open: boolean;
  setOpen: (o: boolean) => void;
  toggle: () => void;
  /** Open the palette and ask a plain-English question straight away. */
  ask: (q: string) => void;
};
const PaletteCtx = createContext<Ctx | null>(null);

export function useCommandPalette() {
  const c = useContext(PaletteCtx);
  if (!c) throw new Error("useCommandPalette must be used inside <Providers>");
  return c;
}

export const NAV = [
  { href: "/", label: "Control tower", icon: MessageSquareText, hint: "Ask anything; every step and cost shown" },
  { href: "/today", label: "Today", icon: PhoneCall, hint: "Who to call and why" },
  {
    href: "/events",
    label: "Events",
    icon: Layers,
    hint: "IPOs, buybacks and offers for sale",
  },
  {
    href: "/calendar",
    label: "Calendar",
    icon: CalendarDays,
    hint: "When money becomes available",
  },
  {
    href: "/network",
    label: "Network",
    icon: Network,
    hint: "Households and links across events",
  },
  {
    href: "/history",
    label: "History",
    icon: History,
    hint: "Every conversation, with what each answer cost",
  },
  {
    href: "/team",
    label: "Team",
    icon: UsersRound,
    hint: "Outcomes per RM and per event type",
    needs: "team",
  },
  {
    href: "/review",
    label: "Review",
    icon: ClipboardCheck,
    hint: "Matches and rows the system was unsure about",
    needs: "review",
  },
  {
    href: "/ops",
    label: "Trust & Ops",
    icon: ShieldCheck,
    hint: "How every number was checked",
    admin: true,
  },
  { href: "/sources", label: "Sources", icon: RadioTower, hint: "Filing sources, their terms, and what ran automatically", admin: true },
  { href: "/ops/accuracy", label: "Accuracy", icon: Target, hint: "Call lists scored against hand-read filings", admin: true },
  { href: "/ops/health", label: "System health", icon: HeartPulse, hint: "Sources, caches, spend and failed runs", admin: true },
  { href: "/admin/pipeline", label: "Pipeline console", icon: SlidersHorizontal, hint: "Run an event by hand, step by step", admin: true },
] as readonly { href: string; label: string; icon: typeof PhoneCall; hint: string; admin?: boolean; needs?: "team" | "review" }[];

/** The pages a role may open (Trust & Ops is for admins). */
export const useNav = () => {
  const { can } = useSession();
  return NAV.filter((n) => (!n.admin || can("ops")) && (!n.needs || can(n.needs)));
};

export function CommandPaletteProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<{ q: string; n: number } | null>(null);
  const toggle = useCallback(() => setOpen((o) => !o), []);
  const ask = useCallback((q: string) => {
    setPending((p) => ({ q, n: (p?.n ?? 0) + 1 }));
    setOpen(true);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    // Deep link for demos and shared links: any page with ?ask=<question> opens the answer.
    const q = new URLSearchParams(window.location.search).get("ask");
    const t = q ? window.setTimeout(() => ask(q), 0) : undefined;
    return () => {
      window.removeEventListener("keydown", onKey);
      if (t) window.clearTimeout(t);
    };
  }, [ask]);

  const value = useMemo(() => ({ open, setOpen, toggle, ask }), [open, toggle, ask]);
  return (
    <PaletteCtx.Provider value={value}>
      {children}
      <CommandPalette open={open} onOpenChange={setOpen} pending={pending} />
    </PaletteCtx.Provider>
  );
}

const looksLikeQuestion = (q: string) => q.trim().split(/\s+/).length >= 3;

/**
 * ⌘K: jump to a page or a person, or ask in plain English ("promoters with cash in hand above 50 crore").
 * A question returns people from the call list with the filters it was read as, shown as chips.
 * People load from the call queue the first time the palette opens.
 */
export function CommandPalette({
  open,
  onOpenChange,
  pending,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  /** A question to ask as soon as the palette opens (from `useCommandPalette().ask` or `?ask=`). */
  pending?: { q: string; n: number } | null;
}) {
  const router = useRouter();
  const nav = useNav();
  const { can } = useSession();
  const canAsk = can("ask");
  const [query, setQuery] = useState("");
  const [people, setPeople] = useState<CallItem[] | null>(null);
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  // Highlighted row while an answer is shown, so Enter opens the first person straight away.
  const [sel, setSel] = useState("");
  const asked = useRef<string>("");
  const lastPending = useRef(0);

  useEffect(() => {
    if (!open || people !== null) return;
    api
      .today(200)
      .then((r) => setPeople(r.items ?? []))
      .catch(() => setPeople([]));
  }, [open, people]);

  const go = (href: string) => {
    onOpenChange(false);
    router.push(href);
  };

  const ask = useCallback(async (q: string) => {
    const question = q.trim();
    if (!question) return;
    asked.current = question;
    setQuery(question);
    setAsking(true);
    setAskError(null);
    setAnswer(null);
    try {
      const res = await api.ask(question);
      if (asked.current === question) {
        setAnswer(res);
        const first = res.people[0];
        setSel(first ? `ans-${first.event.id}-${first.person.id}` : "");
      }
    } catch (e) {
      if (asked.current === question)
        setAskError(e instanceof Error ? e.message : "The data service did not answer.");
    } finally {
      if (asked.current === question) setAsking(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !pending || pending.n === lastPending.current) return;
    lastPending.current = pending.n;
    const t = window.setTimeout(() => void ask(pending.q), 0);
    return () => window.clearTimeout(t);
  }, [open, pending, ask]);

  const reset = () => {
    asked.current = "";
    setAnswer(null);
    setAskError(null);
    setAsking(false);
  };

  // While a question is being answered or shown, the list shows only the answer, in call order.
  const answering = asking || !!answer || !!askError;
  const isQuestion = canAsk && looksLikeQuestion(query);

  return (
    <CommandDialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) {
          reset();
          setQuery("");
        }
      }}
      title="Search or ask"
      description="Find a person, company or page, or ask a question in plain English"
      className="sm:max-w-2xl"
    >
      <Command
        className="rounded-none! bg-popover"
        shouldFilter={!answering}
        {...(answering ? { value: sel, onValueChange: setSel } : {})}
      >
        <CommandInput
          value={query}
          onValueChange={(v) => {
            setQuery(v);
            if (answering) reset();
          }}
          placeholder={canAsk ? "Search, or ask: promoters with cash in hand above 50 crore" : "Search people, companies and pages"}
        />
        <CommandList className="max-h-[min(64vh,32rem)]">
          {answering ? (
            <>
              {asking ? <AskLoading /> : null}
              {askError ? <AskError reason={askError} onRetry={() => void ask(query)} /> : null}
              {answer ? <AskSummary answer={answer} /> : null}
              {answer && answer.people.length === 0 ? <AskNoMatch /> : null}
              {answer && answer.people.length > 0 ? (
                <CommandGroup heading={answer.people.length > 25 ? `First 25 of ${answer.people.length}, in call order` : "In call order"}>
                  {answer.people.slice(0, 25).map((p) => (
                    <CommandItem
                      key={`ans-${p.event.id}-${p.person.id}`}
                      value={`ans-${p.event.id}-${p.person.id}`}
                      onSelect={() => go(`/people/${encodeURIComponent(p.event.id)}/${encodeURIComponent(p.person.id)}`)}
                      className="py-2"
                    >
                      <AskPersonRow item={p} />
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null}
            </>
          ) : (
            <>
              <CommandEmpty>No matching people or pages.</CommandEmpty>
              {isQuestion ? (
                <CommandGroup heading="Ask">
                  <CommandItem
                    value={`ask ${query}`}
                    onSelect={() => void ask(query)}
                    className="gap-3"
                  >
                    <Sparkles className="text-brand" />
                    <span className="truncate">
                      Ask: <span className="font-medium">{query}</span>
                    </span>
                    <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground max-sm:hidden">
                      <CornerDownLeft className="size-3" /> to ask
                    </span>
                  </CommandItem>
                </CommandGroup>
              ) : null}
              {canAsk && query.trim() === "" ? (
                <CommandGroup heading="Try asking">
                  {ASK_EXAMPLES.map((q) => (
                    <CommandItem key={q} value={`example ${q}`} onSelect={() => void ask(q)}>
                      <MessageSquareText className="text-brand" />
                      <span className="truncate">{q}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ) : null}
              <CommandGroup heading="Go to">
                {nav.map((n) => (
                  <CommandItem
                    key={n.href}
                    value={`page ${n.label} ${n.hint}`}
                    onSelect={() => go(n.href)}
                  >
                    <n.icon />
                    <span className="whitespace-nowrap">{n.label}</span>
                    <span className="ml-2 truncate text-muted-foreground max-sm:hidden">
                      {n.hint}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
              {people && people.length > 0 ? (
                <>
                  <CommandSeparator />
                  <CommandGroup heading="People">
                    {people.slice(0, 60).map((p) => (
                      <CommandItem
                        key={`${p.event.id}-${p.person.id}`}
                        value={`${p.person.name} ${p.event.company} ${p.person.role ?? ""}`}
                        onSelect={() => go(`/people/${encodeURIComponent(p.event.id)}/${encodeURIComponent(p.person.id)}`)}
                      >
                        <User />
                        <span className="truncate">{p.person.name}</span>
                        <span className="truncate text-muted-foreground">
                          {p.event.company}
                        </span>
                        <span className="tnum ml-auto text-muted-foreground">
                          {formatCr(p.amount.value_cr) ?? "Not disclosed"}
                        </span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </>
              ) : null}
            </>
          )}
        </CommandList>
        {answering ? (
          <div className="flex items-center justify-between gap-3 border-t border-hairline px-3 py-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              {asking ? <Loader2 className="size-3.5 animate-spin text-brand" /> : <Sparkles className="size-3.5 text-brand" />}
              {asking ? "Reading your question…" : "Every person and amount comes from the checked call list."}
            </span>
            <span className="max-sm:hidden">Edit the question to search again</span>
          </div>
        ) : null}
      </Command>
    </CommandDialog>
  );
}
