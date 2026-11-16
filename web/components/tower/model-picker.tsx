"use client";

import { useEffect, useState } from "react";
import { Check, ChevronDown, Cpu, GitCompare, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { v3, type ChatModel, type CompareResult } from "@/lib/v3";
import { CHAT_MOCK } from "@/lib/chat";
import { useSession } from "@/lib/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useChat } from "./chat-store";

type Catalogue = { models: ChatModel[]; default_fast: string; default_strong: string; priced_from: string };

function useCatalogue(): Catalogue | null {
  const { can } = useSession();
  const [data, setData] = useState<Catalogue | null>(null);
  useEffect(() => {
    if (CHAT_MOCK || !can("ask")) return;
    let live = true;
    v3.models()
      .then((d) => live && setData(d))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [can]);
  return data;
}

const price = (m: ChatModel) => `$${m.input_per_m} in · $${m.output_per_m} out per 1M tokens`;
const cost = (usd: number) => (usd === 0 ? "$0" : `$${usd.toFixed(usd < 0.01 ? 5 : 4)}`);

/** Model choice for this conversation, and the side-by-side comparison. Hidden for roles that cannot ask the model. */
export function ModelTools() {
  const catalogue = useCatalogue();
  const { model, setModel, busy } = useChat();
  const [compare, setCompare] = useState(false);
  if (!catalogue) return null;
  const current = catalogue.models.find((m) => m.id === model);
  return (
    <div data-tech className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" disabled={busy} className="h-7 gap-1.5 px-2 text-xs text-muted-foreground" aria-label="Choose the model for this conversation">
            <Cpu className="size-3.5" aria-hidden />
            {current ? current.label : "Default model"}
            <ChevronDown className="size-3" aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-80">
          <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Model for this conversation</DropdownMenuLabel>
          <DropdownMenuItem onSelect={() => setModel(null)}>
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-medium">Default</span>
              <span className="block text-xs text-muted-foreground">Cheap model reads the question, a stronger one writes long answers</span>
            </span>
            {!current ? <Check className="text-brand" /> : null}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {catalogue.models.map((m) => (
            <DropdownMenuItem key={m.id} onSelect={() => setModel(m.id)}>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium">
                  {m.label} <span className="font-normal text-muted-foreground">· {m.note}</span>
                </span>
                <span className="tnum block text-xs text-muted-foreground">{price(m)}</span>
              </span>
              {current?.id === m.id ? <Check className="text-brand" /> : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <p className="px-2 py-1.5 text-[11px] leading-snug text-faint">Prices from {catalogue.priced_from}. Numbers in answers are still checked against the filings, whichever model writes.</p>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button variant="ghost" size="sm" onClick={() => setCompare(true)} className="h-7 gap-1.5 px-2 text-xs text-muted-foreground">
        <GitCompare className="size-3.5" aria-hidden />
        Compare
      </Button>
      {compare ? <CompareDialog catalogue={catalogue} onClose={() => setCompare(false)} /> : null}
    </div>
  );
}

function CompareDialog({ catalogue, onClose }: { catalogue: Catalogue; onClose: () => void }) {
  const { turns } = useChat();
  const lastQuestion = [...turns].reverse().find((t) => t.kind === "user");
  const [question, setQuestion] = useState(lastQuestion && "text" in lastQuestion ? lastQuestion.text : "");
  const [a, setA] = useState(catalogue.models[0]?.id ?? "");
  const [b, setB] = useState(catalogue.models[2]?.id ?? catalogue.models[1]?.id ?? "");
  const [state, setState] = useState<{ s: "idle" } | { s: "running" } | { s: "error"; reason: string } | { s: "done"; results: CompareResult[] }>({ s: "idle" });
  const label = (id: string) => catalogue.models.find((m) => m.id === id)?.label ?? id;

  const run = async () => {
    setState({ s: "running" });
    try {
      const r = await v3.compare(question.trim(), [a, b]);
      setState({ s: "done", results: r.results });
    } catch (e) {
      setState({ s: "error", reason: e instanceof Error ? e.message : "The comparison could not run." });
    }
  };
  const select = "h-9 w-full rounded-lg border bg-surface px-2.5 text-[13px] text-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] gap-5 overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Compare two models</DialogTitle>
          <DialogDescription>The same question on two models, with what each one cost and how long it took. Nothing is saved to your history, and anything that would spend money is not run.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <label className="block text-xs text-muted-foreground" htmlFor="cmp-q">
            Question
          </label>
          <textarea
            id="cmp-q"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            placeholder="For example: who came into money this week?"
            className="block w-full resize-none rounded-lg border bg-surface px-3 py-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            {[
              ["Model A", a, setA, b],
              ["Model B", b, setB, a],
            ].map(([name, value, set, other]) => (
              <label key={name as string} className="block text-xs text-muted-foreground">
                {name as string}
                <select className={cn(select, "mt-1.5")} value={value as string} onChange={(e) => (set as (v: string) => void)(e.target.value)}>
                  {catalogue.models.map((m) => (
                    <option key={m.id} value={m.id} disabled={m.id === other}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <Button onClick={run} disabled={state.s === "running" || !question.trim() || a === b}>
              {state.s === "running" ? <Loader2 className="animate-spin" /> : <GitCompare />}
              Run both
            </Button>
          </div>
        </div>
        {state.s === "running" ? (
          <div className="grid gap-4 md:grid-cols-2" role="status" aria-label="Running the question on both models">
            {[a, b].map((id) => (
              <div key={id} className="space-y-3 rounded-xl border p-4">
                <p className="text-sm font-semibold">{label(id)}</p>
                <div className="h-3 w-5/6 animate-pulse rounded bg-secondary" />
                <div className="h-3 w-4/6 animate-pulse rounded bg-secondary" />
                <div className="h-3 w-3/6 animate-pulse rounded bg-secondary" />
              </div>
            ))}
          </div>
        ) : null}
        {state.s === "error" ? <p role="alert" className="rounded-lg border border-negative/20 bg-negative-soft/60 px-4 py-3 text-sm text-negative">{state.reason}</p> : null}
        {state.s === "done" ? (
          <div className="grid gap-4 md:grid-cols-2">
            {state.results.map((r) => {
              const cached = (r as CompareResult & { cached?: boolean }).cached === true;
              return (
              <section key={r.model} className="flex flex-col rounded-xl border bg-surface">
                <header className="flex items-baseline justify-between gap-3 border-b px-4 py-3">
                  <h3 className="text-sm font-semibold">{label(r.model)}</h3>
                  <p className="tnum text-xs text-muted-foreground">
                    {cached ? (
                      <span className="font-medium text-foreground">Saved copy</span>
                    ) : (
                      <>
                        <span className="font-medium text-foreground">{cost(r.cost_usd)}</span> · {r.seconds.toFixed(1)} s
                      </>
                    )}
                  </p>
                </header>
                <div className="flex-1 space-y-3 px-4 py-3.5 text-[14px] leading-relaxed">
                  {r.blocked ? <p className="rounded-lg bg-caution-soft px-3 py-2 text-[13px] text-foreground">{r.blocked}</p> : null}
                  {r.text ? <p className="whitespace-pre-wrap">{r.text}</p> : !r.blocked ? <p className="text-muted-foreground">No text came back.</p> : null}
                  {r.cards.length ? (
                    <p className="text-xs text-muted-foreground">
                      Also shown: {r.cards.map((c) => c.title || c.kind).join(" · ")}
                    </p>
                  ) : null}
                </div>
                <footer className="tnum border-t px-4 py-2.5 text-xs text-muted-foreground">
                  {cached
                    ? "Saved copy of an earlier answer from this model. Cost and speed were not measured this time."
                    : `${r.tokens ? `${r.tokens.input} tokens in${r.tokens.cached_input ? ` (${r.tokens.cached_input} reused)` : ""} · ${r.tokens.output} out` : "No tokens used"}${r.models_used.length ? ` · ${r.models_used.map((m) => `${label(m.model)} ×${m.calls}`).join(", ")}` : " · answered from the data, no model"}`}
                </footer>
              </section>
              );
            })}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
