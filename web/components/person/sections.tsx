"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, CalendarDays, ChevronDown, FileSearch, Lock, LockOpen, Tag, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { evidencePageUrl } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { EvidenceChip, EvidenceViewer, FreshnessBadge, Money, pageLabel, SectionHeader } from "@/components/ds";
import { isBareAmount, rmText } from "@/components/today/use-load";
import type { AmountDetail, AmountInput, Evidence } from "@/lib/types";
import { allEvidence, evKey, uniqueEvidence, uniquePages, type Card, type EventFacts, type TimingDetail } from "./types";

function Chips({ list, className }: { list: Evidence[]; className?: string }) {
  const u = uniquePages(uniqueEvidence(list));
  if (!u.length) return null;
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {u.map((e) => (
        <EvidenceChip key={evKey(e)} evidence={e} />
      ))}
    </div>
  );
}

function InputsTable({ inputs }: { inputs: AmountInput[] }) {
  if (!inputs?.length) return null;
  return (
    <dl className="divide-y divide-hairline rounded-lg border border-hairline">
      {inputs.map((i) => (
        <div key={i.label} className="grid gap-2 px-3.5 py-3 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
          <dt className="text-[13px] text-muted-foreground">{i.label}</dt>
          <dd className="tnum min-w-0 text-sm font-medium break-words text-foreground">{i.value}</dd>
          <dd>
            <Chips list={i.evidence ?? []} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** One card per amount (cash from the sale, gain, value of shares held), each input traceable. */
export function AmountsSection({ amounts }: { amounts: AmountDetail[] }) {
  if (!amounts?.length) return null;
  return (
    <section className="space-y-4" aria-labelledby="amounts-h">
      <SectionHeader title={<span id="amounts-h">How the amounts add up</span>} description="Each figure is worked out from values printed in the filings. Open any source to see the page." />
      <div className="space-y-4">
        {amounts.map((a) => (
          <article key={a.key} className="rounded-xl border bg-surface p-5 shadow-(--shadow-card) sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-foreground">{a.label}</h3>
                {a.value_cr !== null && !isBareAmount(a.display) ? <p className="mt-1 max-w-[60ch] text-[13px] leading-snug text-muted-foreground">{rmText(a.display)}</p> : null}
              </div>
              <Money
                amount={{
                  value_cr: a.value_cr,
                  display: a.value_cr === null ? a.display || "Amount not disclosed" : (a.short ?? ""),
                  reason: a.value_cr === null ? rmText(a.reason) || null : null,
                  kind: a.key === "retained" ? "shares" : "cash",
                  estimate: a.value_cr !== null && /estimate|if all|up to/i.test(a.display),
                }}
                size="lg"
                align="end"
                className="sm:shrink-0 max-sm:items-start max-sm:text-left"
              />
            </div>
            {a.working ? (
              <div className="tnum mt-4 rounded-lg bg-surface-sunken px-3.5 py-2.5 text-sm text-foreground">
                <span className="mr-2 text-xs text-muted-foreground">Working</span>
                {a.working}
              </div>
            ) : null}
            {a.inputs?.length ? <div className="mt-4"><InputsTable inputs={a.inputs} /></div> : null}
            {a.caveats?.length ? (
              <ul className="mt-3 space-y-1">
                {a.caveats.map((c) => (
                  <li key={c} className="text-xs leading-snug text-muted-foreground">
                    {rmText(c)}
                  </li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

const PERIOD_ICON: Record<string, typeof Lock> = { locked_until: Lock, unlocked_since: LockOpen };

export function TimingSection({ timing }: { timing: TimingDetail[] }) {
  if (!timing?.length) return null;
  return (
    <section className="space-y-4" aria-labelledby="timing-h">
      <SectionHeader title={<span id="timing-h">When the money is free</span>} description="Dates come from the filing, with the rule that sets them." />
      <div className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
        {timing.map((t) => (
          <article key={t.key} className="p-5 sm:p-6">
            <h3 className="text-sm font-semibold text-foreground">{t.label}</h3>
            {t.periods?.length ? (
              <ul className="mt-3 space-y-2">
                {t.periods.map((p) => {
                  const Icon = PERIOD_ICON[p.status] ?? CalendarDays;
                  const open = p.status === "unlocked_since";
                  return (
                    <li key={p.label} className="flex gap-3 rounded-lg bg-surface-sunken px-3.5 py-3">
                      <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-md", open ? "bg-caution-soft text-caution" : "bg-secondary text-muted-foreground")}>
                        <Icon className="size-3.5" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{p.label}</p>
                        <p className="tnum mt-0.5 text-[13px] leading-snug text-muted-foreground first-letter:uppercase">{rmText(p.display.replace(`${p.label}: `, ""))}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-1 text-[15px] leading-relaxed text-foreground">{rmText(t.display)}</p>
            )}
            {t.note ? <p className="mt-2 text-[13px] text-muted-foreground">{rmText(t.note)}</p> : null}
            {t.inputs?.length ? <div className="mt-4"><InputsTable inputs={t.inputs} /></div> : null}
            {t.rule_evidence?.length ? (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">The rule, as printed:</span>
                <Chips list={t.rule_evidence} />
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

/** Collapsed by default: page thumbnails of every source used on this card, plus why it ranks where it does. */
export function EvidenceTrail({ card, defaultOpen = false }: { card: Card; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const all = allEvidence(card);
  return (
    <section className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-accent/50 sm:px-6"
      >
        <span className="flex items-center gap-3">
          <span className="grid size-8 place-items-center rounded-lg bg-secondary text-muted-foreground">
            <FileSearch className="size-4" aria-hidden />
          </span>
          <span>
            <span className="block text-sm font-semibold text-foreground">Full evidence trail</span>
            <span className="tnum block text-[13px] text-muted-foreground">
              {all.length} source {all.length === 1 ? "passage" : "passages"} from the filings, and why this person ranks here
            </span>
          </span>
        </span>
        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform duration-200 motion-reduce:transition-none", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div className="space-y-6 border-t border-hairline px-5 py-5 sm:px-6">
          {card.rank_reasons?.length ? (
            <div>
              <h3 className="mb-2 text-xs font-medium text-muted-foreground">Why this rank</h3>
              <ul className="space-y-1.5">
                {card.rank_reasons.map((r) => (
                  <li key={r} className="flex gap-2 text-sm leading-snug text-foreground">
                    <span className="mt-[8px] size-1 shrink-0 rounded-full bg-brand" aria-hidden />
                    {rmText(r)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {card.names_as_printed?.length ? (
            <p className="text-[13px] text-muted-foreground">
              Name as printed: <span className="text-foreground">{card.names_as_printed.join(" · ")}</span>
            </p>
          ) : null}
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {all.map(({ evidence, context }) => (
              <li key={evKey(evidence)}>
                <EvidenceViewer
                  evidence={evidence}
                  trigger={
                    <button type="button" className="group/thumb flex w-full flex-col overflow-hidden rounded-lg border bg-surface text-left transition-shadow hover:shadow-(--shadow-raised) focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
                      <span className="relative block h-40 overflow-hidden bg-surface-sunken">
                        {evidence.cached === false ? (
                          <span className="grid h-full place-items-center text-xs text-muted-foreground">Original filing online</span>
                        ) : (
                          // eslint-disable-next-line @next/next/no-img-element -- API page render
                          <img src={evidencePageUrl(evidence)} alt="" loading="lazy" className="w-full object-cover object-top transition-transform duration-300 group-hover/thumb:scale-[1.02] motion-reduce:transition-none" />
                        )}
                      </span>
                      <span className="block space-y-1 border-t px-3 py-2.5">
                        <span className="block text-xs font-medium text-foreground">{context}</span>
                        <span className="line-clamp-2 text-xs leading-snug text-muted-foreground">“{evidence.quote}”</span>
                        <span className="tnum block text-[11px] text-faint">
                          {evidence.doc_label} · {pageLabel(evidence)}
                        </span>
                      </span>
                    </button>
                  }
                />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export function HouseholdCard({ card }: { card: Card }) {
  const h = card.household;
  if (!h || h.members.length < 2) return null;
  const others = h.members.filter((m) => m.id !== card.id);
  return (
    <section className="rounded-xl border bg-surface p-5 shadow-(--shadow-card)">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Users className="size-4 text-muted-foreground" aria-hidden /> {h.label}
      </h2>
      <p className="mt-1 text-xs leading-snug text-muted-foreground">{rmText(h.reason)}</p>
      <ul className="mt-3 divide-y divide-hairline">
        {others.map((m) => (
          <li key={m.id}>
            <Link href={`/people/${m.id}`} className="group/m flex items-center justify-between gap-3 py-2.5">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground group-hover/m:underline">{m.name}</span>
                {m.role ? <span className="block truncate text-xs text-muted-foreground">{m.role}</span> : null}
              </span>
              <Money amount={m.amount} size="sm" align="end" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function EventCard({ card }: { card: Card }) {
  const f = (card.event_facts ?? {}) as EventFacts;
  return (
    <section className="rounded-xl border bg-surface p-5 shadow-(--shadow-card)">
      <h2 className="text-sm font-semibold text-foreground">The event</h2>
      <Link href={`/events/${encodeURIComponent(card.event.id)}`} className="group/e mt-2 flex items-start justify-between gap-3">
        <span>
          <span className="block text-[15px] font-medium text-foreground group-hover/e:underline">{card.event.company}</span>
          <span className="block text-xs text-muted-foreground">{card.event.type_label ?? card.event.type}</span>
        </span>
        <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      </Link>
      <dl className="mt-4 space-y-3 border-t border-hairline pt-4">
        {f.price ? (
          <div className="flex items-start justify-between gap-3">
            <dt className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
              <Tag className="size-3.5" aria-hidden /> {f.price.label}
            </dt>
            <dd className="tnum text-right text-sm font-medium text-foreground">{f.price.display}</dd>
          </div>
        ) : null}
        {f.money_date?.date_iso ? (
          <div className="flex items-start justify-between gap-3">
            <dt className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
              <CalendarDays className="size-3.5" aria-hidden /> {f.money_date.label}
            </dt>
            <dd className="tnum text-right text-sm font-medium text-foreground">
              {formatDate(f.money_date.date_iso)}
              {!f.money_date.confirmed ? <span className="block text-xs font-normal text-muted-foreground">expected</span> : null}
            </dd>
          </div>
        ) : null}
      </dl>
      {card.freshness?.documents.length ? (
        <div className="mt-4 border-t border-hairline pt-4">
          <h3 className="mb-2 text-[13px] text-muted-foreground">Where these facts come from</h3>
          <ul className="space-y-1.5">
            {card.freshness.documents.map((d) => (
              <li key={d.doc_sha} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <span className="text-sm text-foreground">{d.label}</span>
                <FreshnessBadge fetchedAt={d.fetched_at} ageDays={d.age_days} stale={d.stale} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {f.price?.inputs?.length ? <Chips className="mt-3" list={f.price.inputs.flatMap((i) => i.evidence ?? [])} /> : null}
    </section>
  );
}
