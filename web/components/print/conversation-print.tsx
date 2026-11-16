"use client";

import { useEffect, useState } from "react";
import { chatApi, formatCost, formatTokens, modelLabel, percent, type StoredConversation } from "@/lib/chat";
import { formatDate } from "@/lib/format";
import { exchanges, totals } from "@/components/history/thread";
import { PrintCard, PrintFrame } from "./print-kit";

/** /history/[id]/print: the conversation as a clean A4 report (answers, cards as tables, cost per answer). */
export function ConversationPrint({ id }: { id: string }) {
  const [c, setC] = useState<StoredConversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    chatApi
      .conversation(id)
      .then(setC)
      .catch((err) => setError((err as Error).message || "This conversation could not be loaded."));
  }, [id]);

  const back = `/history/${encodeURIComponent(id)}`;
  if (error)
    return (
      <PrintFrame title="Conversation not available" backHref="/history" backLabel="All conversations" ready={false}>
        <p className="text-sm">{error}</p>
      </PrintFrame>
    );
  if (!c)
    return (
      <PrintFrame title="Preparing the report…" backHref={back} backLabel="Back to the conversation" ready={false}>
        <p className="text-sm text-[oklch(0.42_0.018_255)]">Loading the conversation.</p>
      </PrintFrame>
    );

  const t = totals(c);
  const xs = exchanges(c.messages);
  const cached = percent(t.cachedIn, t.tokensIn);
  const date = formatDate((c.updated_at ?? c.messages.at(-1)?.created_at ?? "").slice(0, 10));
  return (
    <PrintFrame
      title={c.title}
      backHref={back}
      backLabel="Back to the conversation"
      ready
      subtitle={
        <>
          Conversation report{date ? ` · ${date}` : ""} · {t.questions} {t.questions === 1 ? "question" : "questions"}
          {t.measured ? ` · total cost ${formatCost(t.cost)} · ${formatTokens(t.tokensIn)} tokens in${cached !== null ? `, ${cached}% from cache` : ""}` : ""}
          {t.compressions ? ` · summarised ${t.compressions}×` : ""}
        </>
      }
    >
      <ol className="space-y-7">
        {xs.map((x) => {
          const a = x.answer;
          const meta = a?.meta;
          return (
            <li key={x.key}>
              {meta?.compressed ? <p className="mb-3 text-center text-[11px] text-[oklch(0.5_0.014_255)]">— earlier turns summarised here —</p> : null}
              <h2 className="text-[14.5px] leading-snug font-semibold">
                <span className="tnum mr-2 text-[oklch(0.5_0.014_255)]">{x.n}.</span>
                {x.question?.text?.trim() || (a?.estimate || a?.steps?.length ? "Confirmed the run" : "Picked an option")}
              </h2>
              {a ? (
                <div className="mt-2 pl-6">
                  {a.clarify ? (
                    <p className="text-[13px] leading-relaxed">
                      {a.clarify.question} <span className="text-[oklch(0.42_0.018_255)]">Options: {a.clarify.options.map((o) => o.label).join("; ")}</span>
                    </p>
                  ) : a.text ? (
                    <div className="space-y-2 text-[13px] leading-relaxed">
                      {a.text.split(/\n{2,}/).map((p, i) => (
                        <p key={i}>
                          {p.split("**").map((part, j) => (j % 2 ? <strong key={j}>{part}</strong> : part))}
                        </p>
                      ))}
                    </div>
                  ) : null}
                  {a.estimate ? (
                    <p className="tnum mt-2 text-[12.5px]">
                      Cost preview: {a.estimate.action.title}, {formatCost(a.estimate.cost_usd_low)}–{formatCost(a.estimate.cost_usd_high)}
                    </p>
                  ) : null}
                  {(a.cards ?? []).map((card, i) => (
                    <PrintCard key={`${card.kind}-${i}`} card={card} />
                  ))}
                  {meta ? (
                    <p className="tnum mt-2.5 text-[11px] text-[oklch(0.5_0.014_255)]">
                      {(meta.models ?? []).map((m) => `${modelLabel(m.model)} × ${m.calls}`).join(", ") || "Code only"} · {formatTokens(meta.tokens_in)} in / {formatTokens(meta.tokens_out)} out
                      {percent(meta.cached_in, meta.tokens_in) !== null ? ` · ${percent(meta.cached_in, meta.tokens_in)}% from cache` : ""} · {formatCost(meta.cost_usd)}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </PrintFrame>
  );
}
