"use client";

import { useEffect, useState } from "react";
import { api, apiFetch } from "@/lib/api";
import { properName, shortCompany } from "@/lib/call-script";
import type { ChatScriptCard } from "@/lib/chat";
import { formatDate } from "@/lib/format";
import { rmText } from "@/components/today/use-load";
import type { PersonCard } from "@/lib/types";
import { evidenceRef, PrintFrame, PrintScript } from "./print-kit";

const MUTED = "text-[oklch(0.42_0.018_255)]";

/** /people/[e]/[p]/print: the call pack — call card, brief, why now, every number with its page, call script. */
export function CallPackPrint({ eventId, personId }: { eventId: string; personId: string }) {
  const [card, setCard] = useState<PersonCard | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The script the chat showed (or the server's template): the print page never writes its own.
  const [script, setScript] = useState<ChatScriptCard | null | "missing">(null);
  useEffect(() => {
    apiFetch<{ script: ChatScriptCard }>(`/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}/callscript`)
      .then((r) => setScript(r.script))
      .catch(() => setScript("missing"));
    api
      .person(eventId, personId)
      .then(setCard)
      .catch((err) => setError((err as Error).message || "This call card could not be loaded."));
    api
      .summary()
      .then((s) => setAsOf(s.as_of))
      .catch(() => {});
  }, [eventId, personId]);

  const back = `/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}`;
  if (error)
    return (
      <PrintFrame title="Call pack not available" backHref="/today" backLabel="Today" ready={false}>
        <p className="text-sm">{error}</p>
      </PrintFrame>
    );
  if (!card || script === null)
    return (
      <PrintFrame title="Preparing the call pack…" backHref={back} backLabel="Back to the call card" ready={false}>
        <p className={`text-sm ${MUTED}`}>Loading the call card.</p>
      </PrintFrame>
    );

  const name = properName(card.person.name);
  const lines = card.brief?.lines?.length ? card.brief.lines : [card.brief_first_line];
  const household = card.household && card.household.members.length > 1 ? card.household : null;
  return (
    <PrintFrame
      title={`Call pack: ${name}`}
      backHref={back}
      backLabel="Back to the call card"
      ready
      subtitle={
        <>
          {card.person.role ?? "Named in the filing"} · {shortCompany(card.event.company)} {card.event.type_label ?? card.event.type}
          {asOf ? ` · data as of ${formatDate(asOf)}` : ""}
        </>
      }
    >
      <dl className="tnum grid grid-cols-3 gap-px overflow-hidden rounded-md border border-[oklch(0.86_0.008_85)] bg-[oklch(0.9_0.006_85)] max-sm:grid-cols-1">
        <div className="bg-white p-3.5">
          <dt className={`text-[11px] ${MUTED}`}>{card.amount.kind === "shares" ? "Value of shares held" : "Money"}</dt>
          <dd className="mt-1 text-[20px] leading-tight font-semibold">
            {card.amount.estimate && card.amount.value_cr !== null ? "≈ " : ""}
            {card.amount.display}
          </dd>
          <dd className={`mt-0.5 text-[11.5px] ${MUTED}`}>{card.tier_label}</dd>
        </div>
        <div className="bg-white p-3.5">
          <dt className={`text-[11px] ${MUTED}`}>When</dt>
          <dd className="mt-1 text-[12.5px] leading-snug">{rmText(card.timing.label)}</dd>
        </div>
        <div className="bg-white p-3.5">
          <dt className={`text-[11px] ${MUTED}`}>How sure</dt>
          <dd className="mt-1 text-[12.5px] font-medium capitalize">{card.confidence.level}</dd>
          <dd className={`mt-0.5 text-[11.5px] leading-snug ${MUTED}`}>{(card.confidence.reasons ?? [card.confidence.reason]).map(rmText).join("; ")}</dd>
        </div>
      </dl>

      <section className="mt-6 grid grid-cols-[minmax(0,1fr)_14rem] gap-6 max-sm:grid-cols-1">
        <div>
          <h2 className="text-[13px] font-semibold">Brief</h2>
          <ol className="mt-1.5 space-y-1.5">
            {lines.map((l, i) => (
              <li key={i} className="tnum text-[13px] leading-relaxed">
                {i + 1}. {rmText(l)}
              </li>
            ))}
          </ol>
        </div>
        <aside className="rounded-md bg-[oklch(0.96_0.02_165)] p-3.5">
          <h2 className="text-[13px] font-semibold text-[oklch(0.34_0.07_165)]">Why now</h2>
          <p className="mt-1 text-[12.5px] leading-relaxed">{rmText(card.why_now || card.why)}</p>
        </aside>
      </section>

      <section className="mt-6">
        <h2 className="text-[13px] font-semibold">The numbers and where they come from</h2>
        <div className="mt-1.5 space-y-3">
          {card.amounts.map((a) => (
            <div key={a.key} className="print-avoid-break border-t border-[oklch(0.93_0.006_85)] pt-2">
              <p className="tnum text-[13px]">
                <span className="font-semibold">{a.label}: {a.short ?? a.display}</span>
                {a.working ? <span className={MUTED}> · {a.working}</span> : null}
              </p>
              <ul className="mt-1 space-y-1">
                {a.inputs.map((input, i) => {
                  const e = input.evidence[0];
                  return (
                    <li key={i} className="tnum text-[11.5px] leading-snug">
                      <span className="font-medium">{input.label}: {input.value}</span>
                      {e ? (
                        <>
                          <span className={MUTED}> · {evidenceRef(e)}</span>
                          <span className={`block italic ${MUTED}`}>“{e.quote.length > 220 ? `${e.quote.slice(0, 220)}…` : e.quote}”</span>
                        </>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {household ? (
        <section className="print-avoid-break mt-6">
          <h2 className="text-[13px] font-semibold">{household.label}</h2>
          <ul className="tnum mt-1.5 space-y-0.5 text-[12.5px]">
            {household.members.map((m) => (
              <li key={m.id}>
                {properName(m.name)}
                {m.role ? <span className={MUTED}> · {m.role}</span> : null} · <span className="font-medium">{m.amount.display}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="mt-7 border-t-2 border-[oklch(0.86_0.008_85)] pt-2">
        {script && script !== "missing" ? (
          <PrintScript card={script} />
        ) : (
          <p className={`text-[12.5px] ${MUTED}`}>The call script could not be loaded. Open the chat and ask for a script for this person.</p>
        )}
      </div>
    </PrintFrame>
  );
}
