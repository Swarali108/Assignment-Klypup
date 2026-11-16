"use client";

import Link from "next/link";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EVENT_TYPE_LABEL } from "@/lib/format";
import type { PersonCard } from "@/lib/types";
import { Avatar } from "./avatar";
import { Money } from "./money";
import { TierBadge } from "./tier-badge";
import { TimingPill } from "./timing-pill";
import { ConfidenceBadge } from "./confidence-badge";

/** Top of the 2-minute call card: identity, the headline amount, timing, confidence, and the brief. */
export function PersonCardHeader({ card, asOf, actions }: { card: PersonCard; asOf?: string; actions?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(card.brief.lines.join("\n"));
      setCopied(true);
      toast.success("Brief copied");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not copy. Select the text and copy it instead.");
    }
  };
  return (
    <section className="overflow-hidden rounded-2xl border bg-surface shadow-(--shadow-card)">
      <div className="flex flex-col gap-6 p-6 sm:p-8 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-4">
          <Avatar name={card.person.name} size="lg" entity={card.person.holder_type !== "person"} />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold leading-tight tracking-[-0.02em] text-foreground sm:text-[1.75rem]">{card.person.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {card.person.role ? `${card.person.role} · ` : ""}
              <Link href={`/events/${encodeURIComponent(card.event.id)}`} className="text-foreground underline decoration-border hover:decoration-foreground">
                {card.event.company}
              </Link>{" "}
              {card.event.type_label ?? EVENT_TYPE_LABEL[card.event.type]}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <TierBadge tier={card.tier} label={card.tier_label} />
            </div>
          </div>
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      {card.household && card.household.members.length > 1 ? (
        <p className="-mt-2 flex flex-wrap items-center gap-x-2 px-6 pb-5 text-[13px] text-muted-foreground sm:px-8">
          <span className="font-medium text-foreground">{card.household.label}:</span>
          {card.household.members
            .filter((m) => m.id !== card.id)
            .map((m, i) => (
              <Link key={m.id} href={`/people/${m.id}`} className="text-brand-ink hover:underline">
                {i > 0 ? ", " : ""}
                {m.name}
              </Link>
            ))}
        </p>
      ) : null}

      <dl className="grid grid-cols-1 divide-y divide-hairline border-y border-hairline bg-surface-sunken/50 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div className="px-6 py-5 sm:px-8">
          <dt className="mb-2 text-xs text-muted-foreground">Money</dt>
          <dd>
            <Money amount={card.amount} size="xl" showKind />
          </dd>
        </div>
        <div className="px-6 py-5 sm:px-8">
          <dt className="mb-2 text-xs text-muted-foreground">When</dt>
          <dd>
            <TimingPill timing={card.timing} asOf={asOf} className="text-sm" />
          </dd>
        </div>
        <div className="px-6 py-5 sm:px-8">
          <dt className="mb-2 text-xs text-muted-foreground">How sure</dt>
          <dd>
            <ConfidenceBadge confidence={card.confidence} showReason />
          </dd>
        </div>
      </dl>

      <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div>
          <div className="mb-3 flex items-center justify-between gap-4">
            <h2 className="text-sm font-semibold text-foreground">Call brief</h2>
            <Button variant="ghost" size="sm" onClick={copy} aria-label="Copy brief">
              {copied ? <Check className="text-positive" /> : <Copy />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <ol className="space-y-2.5">
            {card.brief.lines.map((line, i) => (
              <li key={i} className="flex gap-3 text-[15px] leading-relaxed text-foreground">
                <span className="tnum mt-[3px] grid size-5 shrink-0 place-items-center rounded-full bg-secondary text-[11px] font-medium text-muted-foreground">
                  {i + 1}
                </span>
                <span className="max-w-[72ch]">{line}</span>
              </li>
            ))}
          </ol>
        </div>
        <aside className="self-start rounded-xl bg-brand-soft/70 p-5">
          <h2 className="text-sm font-semibold text-brand-ink">Why now</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-foreground">{card.why_now}</p>
        </aside>
      </div>
    </section>
  );
}
