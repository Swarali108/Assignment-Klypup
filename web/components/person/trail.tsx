"use client";

import { useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  BookOpenText,
  CheckCircle2,
  ChevronDown,
  Coins,
  FileSearch,
  FileText,
  Fingerprint,
  Globe,
  ListOrdered,
  Quote,
  ScrollText,
  Timer,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { EmptyState, ErrorState, EvidenceChip, SkeletonCard } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { rmText, useLoad } from "@/components/today/use-load";
import { modelLabel } from "@/lib/chat";
import type { Evidence } from "@/lib/types";
import type { Trail, TrailStatus, TrailStep } from "@/lib/trail";
import { evKey, uniquePages } from "./types";

const ICON: Record<TrailStep["key"], typeof FileText> = {
  documents: FileText,
  pages: FileSearch,
  quotes: Quote,
  checks: BadgeCheck,
  identity: Fingerprint,
  money: Coins,
  rank: ListOrdered,
  brief: ScrollText,
  enrichment: Globe,
  cost: Timer,
};

const STATUS_RING: Record<TrailStatus, string> = {
  ok: "bg-brand-soft text-brand-ink ring-brand/20",
  warn: "bg-caution-soft text-caution ring-caution/25",
  info: "bg-info-soft text-info ring-info/20",
  none: "bg-surface-sunken text-faint ring-border",
};

const OPEN_BY_DEFAULT = new Set<TrailStep["key"]>(["money", "rank"]);

function Chips({ list }: { list: Evidence[] }) {
  const seen = new Set<string>();
  const unique = list.filter((e) => (seen.has(evKey(e)) ? false : (seen.add(evKey(e)), true)));
  const pages = uniquePages(unique);
  if (!pages.length) return null;
  return (
    <span className="flex flex-wrap gap-1.5">
      {pages.map((e) => (
        <EvidenceChip key={evKey(e)} evidence={e} />
      ))}
    </span>
  );
}

function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "positive" | "caution" | "negative" | "info" }) {
  const tones = {
    neutral: "bg-surface-sunken text-muted-foreground",
    positive: "bg-positive-soft text-positive",
    caution: "bg-caution-soft text-caution",
    negative: "bg-negative-soft text-negative",
    info: "bg-info-soft text-info",
  } as const;
  return <span className={cn("inline-flex h-5 items-center rounded-md px-1.5 text-[11px] font-medium whitespace-nowrap", tones[tone])}>{children}</span>;
}

function Sub({ children }: { children: React.ReactNode }) {
  return <h4 className="mb-2 text-xs font-medium text-muted-foreground">{children}</h4>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg bg-surface-sunken px-3.5 py-3 text-[13px] text-muted-foreground">{children}</p>;
}

/* ---------- step bodies ---------- */

function Documents({ step }: { step: Extract<TrailStep, { key: "documents" }> }) {
  if (!step.documents.length) return <Empty>No source documents are listed for this event.</Empty>;
  return (
    <ul className="divide-y divide-hairline rounded-lg border border-hairline">
      {step.documents.map((d) => (
        <li key={d.source_url} className="flex items-center justify-between gap-3 px-3.5 py-2.5">
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium text-foreground">{d.label}</span>
            <span className="tnum block text-xs text-muted-foreground">{d.pages ? `${d.pages.toLocaleString("en-IN")} pages` : "Page count not recorded"}</span>
          </span>
          <a href={d.url} target="_blank" rel="noreferrer" className="shrink-0 text-xs font-medium text-brand-ink hover:underline">
            {d.cached ? "Open the PDF" : "Open the original"}
          </a>
        </li>
      ))}
    </ul>
  );
}

function Pages({ step }: { step: Extract<TrailStep, { key: "pages" }> }) {
  if (!step.sections.length) return <Empty>No table pages are recorded for this person.</Empty>;
  return (
    <div className="space-y-4">
      {step.sections.map((s) => (
        <div key={s.section}>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-medium text-foreground">{s.label}</p>
            <p className="text-xs text-muted-foreground">{rmText(s.why)}</p>
          </div>
          <ul className="flex flex-wrap gap-2">
            {s.pages.map((p) => (
              <li
                key={p.pdf_index}
                title={p.terms.length ? `Matched: ${p.terms.join(", ")}` : undefined}
                className={cn("tnum rounded-lg border px-2.5 py-1.5 text-xs", p.used ? "border-brand/30 bg-brand-soft text-brand-ink" : "border-hairline bg-surface text-muted-foreground")}
              >
                <span className="font-medium">{p.printed_page ? `p. ${p.printed_page}` : `PDF p. ${p.pdf_index}`}</span>
                {p.score !== null ? <span className="ml-1.5 opacity-80">score {p.score}</span> : null}
                {p.used ? <span className="ml-1.5 font-medium">· this person</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function Quotes({ step }: { step: Extract<TrailStep, { key: "quotes" }> }) {
  if (!step.groups.length) return <Empty>No quotes are stored for this person.</Empty>;
  return (
    <div className="space-y-5">
      {step.groups.map((g) => (
        <div key={g.section}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">{g.label}</p>
            {g.model ? <Pill>Read by {modelLabel(g.model)}</Pill> : null}
            {g.cached === true ? <Pill tone="positive">Saved copy, no new cost</Pill> : g.cached === false ? <Pill tone="info">Read fresh</Pill> : null}
          </div>
          <ul className="divide-y divide-hairline rounded-lg border border-hairline">
            {g.rows.map((r, i) => (
              <li key={`${r.field}-${i}`} className="grid gap-2 px-3.5 py-3 sm:grid-cols-[minmax(0,9rem)_minmax(0,1fr)_auto] sm:items-start sm:gap-4">
                <span className="text-[13px] text-muted-foreground">{r.label}</span>
                <span className="min-w-0 text-sm">
                  {r.value ? <span className="tnum block font-medium break-words text-foreground">{r.value}</span> : null}
                  {r.quote ? <span className="tnum mt-0.5 block text-xs leading-snug break-words text-muted-foreground">“{r.quote}”</span> : null}
                  {r.page_corrected ? <span className="mt-1 block text-[11px] text-faint">Page reference corrected to where the quote really is</span> : null}
                </span>
                <EvidenceChip evidence={r.evidence} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function Checks({ step }: { step: Extract<TrailStep, { key: "checks" }> }) {
  return (
    <div className="space-y-4">
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {step.applied.map((a) => (
          <li key={a} className="flex items-start gap-2 text-[13px] text-muted-foreground">
            <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-positive" aria-hidden />
            {a}
          </li>
        ))}
      </ul>
      <div>
        <Sub>Passed ({step.passed.length})</Sub>
        {step.passed.length ? (
          <ul className="flex flex-wrap gap-1.5">
            {step.passed.map((p, i) => (
              <li key={`${p.label}-${p.page}-${i}`} className="tnum inline-flex items-center gap-1 rounded-md bg-positive-soft px-2 py-1 text-xs text-positive">
                <CheckCircle2 className="size-3" aria-hidden />
                {p.label} <span className="opacity-70">· {p.section}{p.page ? `, p. ${p.page}` : ""}</span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Nothing was kept for this person.</Empty>
        )}
      </div>
      <div>
        <Sub>Rejected ({step.rejected.length})</Sub>
        {step.rejected.length ? (
          <ul className="divide-y divide-hairline rounded-lg border border-negative/20 bg-negative-soft/40">
            {step.rejected.map((r, i) => (
              <li key={`${r.field}-${i}`} className="flex items-start gap-2.5 px-3.5 py-2.5">
                <XCircle className="mt-0.5 size-4 shrink-0 text-negative" aria-hidden />
                <span className="min-w-0 text-[13px]">
                  <span className="font-medium text-foreground">{r.label}</span> <span className="text-muted-foreground">({r.section})</span>
                  {r.value ? <span className="tnum block break-words text-muted-foreground">“{r.value}”</span> : null}
                  <span className="block text-foreground">{r.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="inline-flex items-center gap-2 text-[13px] text-muted-foreground">
            <CheckCircle2 className="size-4 text-positive" aria-hidden /> Nothing about this person was rejected.
          </p>
        )}
      </div>
      {step.conflicts.length ? (
        <div>
          <Sub>Disagreements between tables</Sub>
          <ul className="space-y-1.5">
            {step.conflicts.map((c) => (
              <li key={c.field} className="flex items-start gap-2 text-[13px] text-foreground">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-caution" aria-hidden />
                <span>
                  <span className="font-medium">{c.field}</span>: {rmText(c.detail)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Identity({ step }: { step: Extract<TrailStep, { key: "identity" }> }) {
  return (
    <div className="space-y-4">
      <div>
        <Sub>Names printed in the filings</Sub>
        <ul className="flex flex-wrap gap-1.5">
          {step.names.map((n) => (
            <li key={n} className="rounded-md border border-hairline bg-surface px-2 py-1 text-[13px] text-foreground">
              {n}
            </li>
          ))}
        </ul>
        {step.holder_type_reason ? <p className="mt-2 text-xs text-muted-foreground">{rmText(step.holder_type_reason)}</p> : null}
      </div>
      {step.merges.length ? (
        <div>
          <Sub>Name matches</Sub>
          <ul className="divide-y divide-hairline rounded-lg border border-hairline">
            {step.merges.map((m, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 text-[13px]">
                <span className="text-foreground">{m.pair.join("  =  ")}</span>
                <span className="flex items-center gap-1.5">
                  <Pill tone={m.outcome === "merge" ? "positive" : "neutral"}>{m.outcome === "merge" ? "Joined" : "Kept apart"}</Pill>
                  <span className="text-xs text-muted-foreground">{m.method}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg bg-surface-sunken px-3.5 py-3">
          <p className="text-xs text-muted-foreground">Family and household</p>
          {step.family && step.family.members.length ? (
            <>
              <p className="mt-0.5 text-sm font-medium text-foreground">{step.family.members.join(", ")}</p>
              <p className="mt-1 text-xs leading-snug text-muted-foreground">{step.family.reasons.map((r) => rmText(r)).join(" ")}</p>
            </>
          ) : (
            <p className="mt-0.5 text-sm text-foreground">No family link found</p>
          )}
        </div>
        <div className="rounded-lg bg-surface-sunken px-3.5 py-3">
          <p className="text-xs text-muted-foreground">Stronger-model checks</p>
          <p className="tnum mt-0.5 text-sm text-foreground">
            {step.strong_model_checks ? `${step.strong_model_checks} borderline name pair${step.strong_model_checks === 1 ? "" : "s"} settled` : "None needed. Code settled every pair."}
          </p>
          <p className="tnum mt-1 text-xs text-muted-foreground">{step.other_filings ? `Also appears in ${step.other_filings} other filing${step.other_filings === 1 ? "" : "s"}.` : "Not seen in other processed events."}</p>
        </div>
      </div>
    </div>
  );
}

function Money({ step }: { step: Extract<TrailStep, { key: "money" }> }) {
  if (!step.amounts.length) return <Empty>No amount could be worked out from the filings.</Empty>;
  return (
    <div className="space-y-5">
      {step.amounts.map((a) => (
        <div key={a.key} className="rounded-lg border border-hairline">
          <div className="flex flex-wrap items-baseline justify-between gap-2 px-3.5 pt-3">
            <p className="text-sm font-medium text-foreground">{a.label}</p>
            <p className="tnum text-sm font-semibold text-foreground">{a.short ?? ""}</p>
          </div>
          {a.working ? <p className="tnum mx-3.5 mt-2 rounded-md bg-surface-sunken px-3 py-2 text-[13px] text-foreground">{a.working}</p> : null}
          <ul className="mt-2 divide-y divide-hairline">
            {(a.inputs ?? []).map((i) => (
              <li key={i.label} className="grid gap-2 px-3.5 py-2.5 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
                <span className="text-[13px] text-muted-foreground">{i.label}</span>
                <span className="tnum text-sm font-medium break-words text-foreground">{i.value}</span>
                <Chips list={i.evidence ?? []} />
              </li>
            ))}
          </ul>
        </div>
      ))}
      {step.timing.length ? (
        <div>
          <Sub>Lock-in and payment rules</Sub>
          <ul className="space-y-3">
            {step.timing.map((t) => (
              <li key={t.key} className="rounded-lg border border-hairline px-3.5 py-3">
                <p className="text-sm font-medium text-foreground">{t.label}</p>
                {t.periods?.length ? null : <p className="tnum mt-0.5 text-[13px] text-muted-foreground first-letter:uppercase">{rmText(t.display)}</p>}
                {t.periods?.length ? (
                  <ul className="mt-1 space-y-1">
                    {t.periods.map((p) => (
                      <li key={p.label} className="tnum text-xs text-muted-foreground">
                        {rmText(p.display)}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {t.note ? <p className="mt-2 text-xs leading-snug text-muted-foreground">{rmText(t.note)}</p> : null}
                {t.rule_evidence?.length ? (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Rule cited from</span>
                    <Chips list={t.rule_evidence} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Rank({ step }: { step: Extract<TrailStep, { key: "rank" }> }) {
  if (!step.parts.length) return <Empty>This person was not ranked.</Empty>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {step.tier ? <Pill tone="positive">{step.tier}</Pill> : null}
        {step.rank ? <Pill>Rank {step.rank}</Pill> : null}
        {step.group && step.group !== "callable" ? <Pill tone="caution">{step.group === "entities" ? "Fund or company" : "Context only"}</Pill> : null}
      </div>
      <div className="tnum flex flex-wrap items-stretch gap-2 text-sm">
        {step.parts.map((p, i) => (
          <div key={p.label} className="flex items-stretch gap-2">
            {i > 0 ? <span className="self-center text-faint">×</span> : null}
            <div className="min-w-24 rounded-lg border border-hairline bg-surface px-3 py-2">
              <p className="text-[11px] text-muted-foreground">{p.label}</p>
              <p className="text-[15px] font-semibold text-foreground">{p.value}</p>
              {p.note ? <p className="mt-0.5 max-w-[22ch] text-[11px] leading-tight text-faint">{rmText(p.note)}</p> : null}
            </div>
          </div>
        ))}
        {step.score ? (
          <div className="flex items-stretch gap-2">
            <span className="self-center text-faint">=</span>
            <div className="min-w-24 rounded-lg border border-brand/30 bg-brand-soft px-3 py-2">
              <p className="text-[11px] text-brand-ink">Score</p>
              <p className="text-[15px] font-semibold text-brand-ink">{Number(step.score).toFixed(2)}</p>
            </div>
          </div>
        ) : null}
      </div>
      {step.later ? (
        <p className="tnum text-xs text-muted-foreground">
          Later value of shares kept: ₹{step.later.value_cr} Cr, scored {step.later.score ? Number(step.later.score).toFixed(2) : "n/a"}. The score above sets the order; this one only breaks a tie.
        </p>
      ) : null}
    </div>
  );
}

function Brief({ step }: { step: Extract<TrailStep, { key: "brief" }> }) {
  if (!step.lines?.length && !step.written_by) return <Empty>No brief was written for this person.</Empty>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={step.written_by === "assistant" ? "info" : "neutral"}>{step.written_by === "assistant" ? "Written by the assistant" : "Written from a template"}</Pill>
        {step.model ? <Pill>{modelLabel(step.model)}</Pill> : null}
        {step.prompt_version ? <Pill>Instructions {step.prompt_version}</Pill> : null}
        {step.fallback_reason ? <Pill tone="caution">Draft not used: {rmText(step.fallback_reason)}</Pill> : null}
      </div>
      {step.template_lines?.length ? (
        <div>
          <Sub>What the assistant wrote (numbers left as blanks)</Sub>
          <ul className="space-y-1 rounded-lg bg-surface-sunken px-3.5 py-3 text-[13px] leading-snug text-muted-foreground">
            {step.template_lines.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {step.placeholders?.length ? (
        <div>
          <Sub>Blanks filled by code from the verified figures</Sub>
          <dl className="divide-y divide-hairline rounded-lg border border-hairline">
            {step.placeholders.map((p) => (
              <div key={p.key} className="grid gap-1 px-3.5 py-2 sm:grid-cols-[9rem_1fr] sm:gap-4">
                <dt className="font-mono text-xs text-muted-foreground">{`{${p.key}}`}</dt>
                <dd className="tnum text-[13px] break-words text-foreground">{p.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
      {step.attempts && step.attempts.length > 1 ? (
        <div>
          <Sub>Attempts</Sub>
          <ul className="space-y-1">
            {step.attempts.map((a) => (
              <li key={a.n} className="flex items-start gap-2 text-[13px]">
                {a.problem ? <XCircle className="mt-0.5 size-3.5 shrink-0 text-negative" aria-hidden /> : <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-positive" aria-hidden />}
                <span className="text-foreground">
                  Attempt {a.n}: <span className="text-muted-foreground">{a.problem ? `rejected, it ${rmText(a.problem)}` : "accepted"}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Enrichment({ step, onOpenPanels }: { step: Extract<TrailStep, { key: "enrichment" }>; onOpenPanels?: () => void }) {
  const li = step.linkedin;
  const web = step.web;
  if (!li && !web) {
    return (
      <div className="space-y-2">
        <Empty>Not looked up yet. A lookup is a paid step (counted in Bright Data requests) and only runs after you confirm the request count.</Empty>
        {onOpenPanels ? (
          <Button variant="outline" size="sm" onClick={onOpenPanels}>
            Open the profile panels
          </Button>
        ) : null}
      </div>
    );
  }
  const best = li?.candidates?.[0];
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg bg-surface-sunken px-3.5 py-3">
          <p className="text-xs text-muted-foreground">Public profile</p>
          {best ? (
            <>
              <p className="mt-0.5 flex items-center gap-2 text-sm font-medium text-foreground">
                {best.name} <Pill tone={best.match === "likely" ? "positive" : "caution"}>{best.match === "likely" ? "Likely match" : "Unconfirmed match"}</Pill>
              </p>
              <p className="mt-1 text-xs leading-snug text-muted-foreground">{best.reason}</p>
            </>
          ) : (
            <p className="mt-0.5 text-sm text-foreground">{li?.error ? rmText(li.error) : "No public profile found"}</p>
          )}
        </div>
        <div className="rounded-lg bg-surface-sunken px-3.5 py-3">
          <p className="text-xs text-muted-foreground">Mentions on the web</p>
          <p className="tnum mt-0.5 text-sm text-foreground">{web?.rows?.length ? `${web.rows.length} results, from web search, not verified` : web?.error ? rmText(web.error) : "None found"}</p>
        </div>
      </div>
      <p className="tnum text-xs text-muted-foreground">
        {step.requests ? `${step.requests} Bright Data requests used.` : "No new requests used."}
        {step.updated_at ? ` Last looked up ${formatDate(step.updated_at.slice(0, 10))}.` : ""}
      </p>
    </div>
  );
}

function Cost({ step }: { step: Extract<TrailStep, { key: "cost" }> }) {
  const run = step.run;
  const cell = (label: string, value: string, sub?: string) => (
    <div className="rounded-lg bg-surface-sunken px-3.5 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="tnum mt-0.5 text-[15px] font-semibold text-foreground">{value}</p>
      {sub ? <p className="text-[11px] text-faint">{sub}</p> : null}
    </div>
  );
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        {cell("Charged in the last run", step.cost_usd != null ? `$${step.cost_usd.toFixed(4)}` : "n/a", run?.cached_share === 1 ? "everything came from saved copies" : undefined)}
        {cell("If read fresh", step.fresh_usd != null ? `$${step.fresh_usd.toFixed(4)}` : "n/a", step.calls != null ? `about ${step.calls.toFixed(1)} model calls` : undefined)}
        {cell("Share of the run", step.seconds != null ? `${step.seconds} s` : "n/a", run?.seconds && run.people ? `${run.seconds} s for ${run.people} people` : undefined)}
      </div>
      {step.enrichment_requests ? <p className="tnum text-xs text-muted-foreground">Public lookups for this person used {step.enrichment_requests} Bright Data requests (counted separately, no dollar cost on the free allowance).</p> : null}
    </div>
  );
}

function Body({ step, onOpenPanels }: { step: TrailStep; onOpenPanels?: () => void }) {
  switch (step.key) {
    case "documents":
      return <Documents step={step} />;
    case "pages":
      return <Pages step={step} />;
    case "quotes":
      return <Quotes step={step} />;
    case "checks":
      return <Checks step={step} />;
    case "identity":
      return <Identity step={step} />;
    case "money":
      return <Money step={step} />;
    case "rank":
      return <Rank step={step} />;
    case "brief":
      return <Brief step={step} />;
    case "enrichment":
      return <Enrichment step={step} onOpenPanels={onOpenPanels} />;
    case "cost":
      return <Cost step={step} />;
  }
}

/* ---------- timeline ---------- */

function StepRow({ step, index, last, open, onToggle, onOpenPanels }: { step: TrailStep; index: number; last: boolean; open: boolean; onToggle: () => void; onOpenPanels?: () => void }) {
  const Icon = ICON[step.key] ?? BookOpenText;
  const id = `trail-${step.key}`;
  return (
    <li className="relative flex gap-4 sm:gap-5">
      <div className="flex flex-col items-center">
        <span className={cn("z-10 grid size-9 shrink-0 place-items-center rounded-full ring-1 ring-inset", STATUS_RING[step.status])}>
          <Icon className="size-4" aria-hidden />
        </span>
        {!last ? <span className="mt-1 w-px flex-1 bg-border" aria-hidden /> : null}
      </div>
      <div className={cn("min-w-0 flex-1", last ? "pb-0" : "pb-6")}>
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            aria-controls={id}
            className="flex w-full items-start justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-surface-sunken/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <span className="min-w-0">
              <span className="tnum block text-[11px] text-faint">Step {index + 1}</span>
              <span className="block text-[15px] font-semibold text-foreground">{step.title}</span>
              <span className="tnum mt-0.5 block text-[13px] leading-snug text-muted-foreground">{rmText(step.summary)}</span>
            </span>
            <span className="mt-1 flex shrink-0 items-center gap-2">
              {step.status === "warn" ? <Pill tone="caution">Check</Pill> : null}
              <ChevronDown className={cn("size-4 text-muted-foreground transition-transform duration-200 motion-reduce:transition-none", open && "rotate-180")} aria-hidden />
            </span>
          </button>
          {open ? (
            <div id={id} className="border-t border-hairline px-5 py-5">
              <Body step={step} onOpenPanels={onOpenPanels} />
            </div>
          ) : null}
        </div>
      </div>
    </li>
  );
}

function TrailLoading() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading how we found them">
      {[0, 1, 2, 3].map((i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

export function TrailTab({ eventId, personId, onOpenPanels }: { eventId: string; personId: string; onOpenPanels?: () => void }) {
  const { load, retry } = useLoad<Trail>(() => api.trail(eventId, personId), [eventId, personId]);
  const [open, setOpen] = useState<Set<string>>(() => new Set(OPEN_BY_DEFAULT));

  if (load.state === "loading") return <TrailLoading />;
  if (load.state === "error") return <ErrorState title="The trail could not be loaded" reason={load.reason} onRetry={retry} />;
  const { steps } = load.data;
  if (!steps.length) {
    return (
      <EmptyState icon={FileSearch} title="No trail recorded for this person">
        The files from the last run do not hold enough to rebuild how this person was found. Run the event again to record it.
      </EmptyState>
    );
  }
  const allOpen = open.size >= steps.length;
  const toggle = (key: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  return (
    <section className="space-y-5" aria-labelledby="trail-h">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h2 id="trail-h" className="text-base font-semibold text-foreground">
            How we found {load.data.person.name}
          </h2>
          <p className="max-w-[70ch] text-sm text-muted-foreground">
            Every step below comes from the record of the last run. Open any source chip to see the page the fact came from.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setOpen(allOpen ? new Set() : new Set(steps.map((s) => s.key)))}>
          {allOpen ? "Collapse all" : "Expand all"}
        </Button>
      </div>
      <ol className="list-none">
        {steps.map((s, i) => (
          <StepRow key={s.key} step={s} index={i} last={i === steps.length - 1} open={open.has(s.key)} onToggle={() => toggle(s.key)} onOpenPanels={onOpenPanels} />
        ))}
      </ol>
    </section>
  );
}
