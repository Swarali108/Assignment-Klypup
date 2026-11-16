"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Copy, Info, PhoneCall } from "lucide-react";
import { toast } from "sonner";
import { InBookBadge } from "@/components/ds/in-book-badge";
import { Avatar, ConfidenceBadge, EvidenceChip, Money, TierBadge, TimingPill } from "@/components/ds";
import { RM_STATUS_LABEL } from "@/components/ds";
import { Can } from "@/components/ds/can";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { isBareAmount, rmConfidence, rmText, rmTiming } from "@/components/today/use-load";
import type { RmStatus } from "@/lib/types";
import { uniqueEvidence, uniquePages, type Card } from "./types";

const ENTITY = /\b(trust|fund|llp|limited|ltd|huf|private|company|holdings|partners|mauritius)\b/i;

/** The 2-minute call card: who, how much (with working), when, how sure, the brief, and why now. */
export function CallCard({ card, asOf, rmStatus }: { card: Card; asOf: string; rmStatus: RmStatus }) {
  const [copied, setCopied] = useState(false);
  const headline = card.amounts.find((a) => a.key === card.amount.source) ?? card.amounts.find((a) => a.value_cr !== null) ?? card.amounts[0];
  const headlineEvidence = uniquePages(uniqueEvidence((headline?.inputs ?? []).flatMap((i) => i.evidence ?? [])));
  const lines = card.brief?.lines?.length ? card.brief.lines : [card.brief_first_line].filter(Boolean);
  const conf = rmConfidence(card.confidence);
  const entity = card.person.holder_type !== "person" || ENTITY.test(card.person.name);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(lines.map(rmText).join("\n"));
      setCopied(true);
      toast.success("Brief copied");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not copy. Select the text and copy it instead.");
    }
  };

  const money = <Money amount={{ ...card.amount, reason: rmText(card.amount.reason) || null }} size="xl" />;

  return (
    <section aria-label="Call card" className="overflow-hidden rounded-2xl border bg-surface shadow-(--shadow-card)">
      <div className="flex flex-col gap-5 p-6 sm:flex-row sm:items-start sm:justify-between sm:p-8">
        <div className="flex min-w-0 gap-4">
          <Avatar name={card.person.name} size="lg" entity={entity} />
          <div className="min-w-0">
            <h1 className="text-2xl leading-tight font-semibold tracking-[-0.02em] text-balance text-foreground sm:text-[1.75rem]">{card.person.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {card.person.kind_label ? <span className="mr-1.5 inline-flex h-5 items-center rounded-md bg-secondary px-1.5 align-middle text-[11px] font-medium text-secondary-foreground">{card.person.kind_label}</span> : null}
              {card.person.role ? <span className="text-foreground/85">{card.person.role} · </span> : null}
              <Link href={`/events/${encodeURIComponent(card.event.id)}`} className="text-foreground underline decoration-border underline-offset-3 hover:decoration-foreground">
                {card.event.company}
              </Link>{" "}
              · {card.event.type_label ?? card.event.type}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <TierBadge tier={card.tier} label={card.tier_label} />
              {card.in_book ? <InBookBadge /> : null}
              {card.household && card.household.members.length > 1 ? (
                <span className="inline-flex h-6 items-center rounded-md bg-secondary px-2 text-xs font-medium text-muted-foreground">{card.household.label}</span>
              ) : null}
              <span
                className={cn(
                  "inline-flex h-6 items-center gap-1.5 rounded-md px-2 text-xs font-medium ring-1 ring-inset",
                  rmStatus === "to_call" ? "bg-surface text-muted-foreground ring-border" : rmStatus === "follow_up" ? "bg-info-soft text-info ring-info/15" : "bg-positive-soft text-positive ring-positive/15",
                )}
              >
                {rmStatus === "to_call" ? <PhoneCall className="size-3" aria-hidden /> : <Check className="size-3" aria-hidden />}
                {RM_STATUS_LABEL[rmStatus]}
              </span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" size="lg" onClick={copy} className="bg-surface">
            {copied ? <Check className="text-positive" /> : <Copy />}
            {copied ? "Copied" : "Copy brief"}
          </Button>
          <Can permission="edit_rm">
            <Button asChild size="lg">
              <a href="#log-call">
                <PhoneCall /> Log the call
              </a>
            </Button>
          </Can>
        </div>
      </div>

      <dl className="grid grid-cols-1 divide-y divide-hairline border-y border-hairline bg-surface-sunken/50 md:grid-cols-[1.25fr_1fr_1fr] md:divide-x md:divide-y-0">
        <div className="px-6 py-5 sm:px-8">
          <dt className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            {card.amount.kind === "shares" ? "Value of shares held" : "Money"}
            {card.amount.estimate && card.amount.value_cr !== null ? <span className="text-faint">· estimate</span> : null}
          </dt>
          <dd>
            {headline?.working ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0} className="inline-flex cursor-help rounded-md">
                    {money}
                  </span>
                </TooltipTrigger>
                <TooltipContent className="tnum max-w-80">{headline.working}</TooltipContent>
              </Tooltip>
            ) : (
              money
            )}
            {card.amount.value_cr !== null && card.amount.detail && !isBareAmount(card.amount.detail) ? <p className="mt-2 max-w-[42ch] text-[13px] leading-snug text-muted-foreground">{card.amount.detail}</p> : null}
            {headline?.working ? <p className="tnum mt-1.5 text-[13px] text-foreground/80">{headline.working}</p> : null}
            {headlineEvidence.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {headlineEvidence.slice(0, 3).map((e) => (
                  <EvidenceChip key={`${e.doc_sha}${e.pdf_index}${e.quote}`} evidence={e} />
                ))}
              </div>
            ) : null}
          </dd>
        </div>
        <div className="px-6 py-5 sm:px-8">
          <dt className="mb-2 text-xs text-muted-foreground">When</dt>
          <dd className="space-y-2">
            <TimingPill timing={rmTiming(card.timing)} asOf={asOf} className="text-sm" />
            {card.tier_reason ? <p className="text-[13px] leading-snug text-muted-foreground">{rmText(card.tier_reason)}</p> : null}
          </dd>
        </div>
        <div className="px-6 py-5 sm:px-8">
          <dt className="mb-2 text-xs text-muted-foreground">How sure</dt>
          <dd>
            <ConfidenceBadge confidence={conf} showReason={false} className="text-sm font-medium" />
            <ul className="mt-2 space-y-1">
              {(conf.reasons?.length ? conf.reasons : [conf.reason]).map((r) => (
                <li key={r} className="flex gap-2 text-[13px] leading-snug text-muted-foreground">
                  <span className="mt-[7px] size-1 shrink-0 rounded-full bg-faint" aria-hidden />
                  {rmText(r)}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      </dl>

      <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div>
          <h2 className="mb-3 text-sm font-semibold text-foreground">Call brief</h2>
          <ol className="space-y-3">
            {lines.map((line, i) => (
              <li key={i} className="flex gap-3 text-[15px] leading-relaxed text-foreground">
                <span className="tnum mt-[3px] grid size-5 shrink-0 place-items-center rounded-full bg-secondary text-[11px] font-medium text-muted-foreground">{i + 1}</span>
                <span className="max-w-[70ch]">{rmText(line)}</span>
              </li>
            ))}
          </ol>
        </div>
        <aside className="self-start rounded-xl bg-brand-soft/70 p-5">
          <h2 className="text-sm font-semibold text-brand-ink">Why now</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-foreground">{rmText(card.why_now || card.why)}</p>
          {card.flags?.length ? (
            <ul className="mt-3 space-y-1.5 border-t border-brand/15 pt-3">
              {card.flags.map((f) => (
                <li key={f} className="flex gap-2 text-[13px] leading-snug text-foreground/80">
                  <Info className="mt-0.5 size-3.5 shrink-0 text-caution" aria-hidden />
                  {rmText(f)}
                </li>
              ))}
            </ul>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
