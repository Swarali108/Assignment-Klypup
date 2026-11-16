"use client";

import { useState } from "react";
import { ChevronDown, Clock3, ExternalLink, ScanLine, UserX } from "lucide-react";
import { CallList, EmptyState, PersonRow, SectionHeader } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { resolveApiUrl } from "@/lib/api";
import { useSession } from "@/lib/session";
import { bucketOf } from "@/lib/tier";
import type { Tier } from "@/lib/types";
import type { EventDetail, EventPeople, PeopleItem } from "./types";

const TIERS: { tier: Tier; title: string; description: string }[] = [
  { tier: "cash_now", title: "Cash in hand", description: "Sale proceeds already paid out, or due within 30 days" },
  { tier: "unlock", title: "Shares just unlocked", description: "Lock-in ended recently; shares can now be sold or pledged" },
  { tier: "holding", title: "Holds shares", description: "Holdings still locked in, or with no money date yet" },
];

/** "Not tendering" rows: the section heading already says why, so drop the long filing quote under the amount. */
function quiet(r: PeopleItem): PeopleItem {
  return r.amount.value_cr === null && r.amount.display === "Not tendering" ? { ...r, amount: { ...r.amount, reason: null } } : r;
}

function Collapsible({ items, asOf, initial = 5, showTier = true }: { items: PeopleItem[]; asOf: string; initial?: number; showTier?: boolean }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, initial);
  return (
    <CallList>
      {shown.map((r) => (
        <PersonRow key={r.id ?? r.person.id} item={quiet(r)} asOf={asOf} showEvent={false} showTier={showTier && r.timing.status !== "not_applicable"} />
      ))}
      {items.length > initial ? (
        <button
          type="button"
          aria-expanded={all}
          onClick={() => setAll((a) => !a)}
          className="flex w-full items-center justify-center gap-1.5 px-5 py-3 text-[13px] font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
        >
          {all ? "Show fewer" : <>Show all <span className="tnum">{items.length}</span></>}
          <ChevronDown className={`size-3.5 transition-transform duration-200 ${all ? "rotate-180" : ""}`} />
        </button>
      ) : null}
    </CallList>
  );
}

/** The event's call list by tier, then "Also on the register" (entities) and "No money from this event" (context). */
export function EventPeopleSections({ event, people }: { event: EventDetail; people: EventPeople }) {
  const { can } = useSession();
  const asOf = event.as_of;
  const scanned = event.status === "scanned" || event.docs.some((d) => d.scanned);
  const notRead = event.status === "not_processed";
  const firstDoc = event.docs[0];

  return (
    <div className="space-y-10">
      {people.callable.length === 0 ? (
        <EmptyState
          icon={scanned ? ScanLine : notRead ? Clock3 : UserX}
          tone={scanned ? "caution" : "neutral"}
          title={scanned ? "Scanned filing: text not readable yet" : notRead ? "This event has not been read yet" : "No one to call from this event"}
          action={
            firstDoc ? (
              <Button asChild variant="outline" size="sm">
                <a href={firstDoc.url ? resolveApiUrl(firstDoc.url) : firstDoc.source_url} target="_blank" rel="noreferrer">
                  <ExternalLink /> Open the filing
                </a>
              </Button>
            ) : null
          }
        >
          {scanned ? (
            <p>
              The filing is an image of printed pages, so no names or amounts could be read from it. We show this honestly rather than
              guess.
            </p>
          ) : (
            <p>
              {notRead
                ? (can("process") ? "Press Process now to read the filings and build the call list. It usually takes under a minute." : "This filing has not been read yet. An admin can process it.")
                : (people.empty_reason ?? event.empty_reason ?? "Nobody named in the filings receives money from this event.")}
            </p>
          )}
        </EmptyState>
      ) : (
        TIERS.map((t) => {
          const rows = people.callable.filter((r) => bucketOf(r) === t.tier);
          if (!rows.length) return null;
          return (
            <section key={t.tier} className="space-y-3">
              <SectionHeader title={t.title} description={t.description} count={rows.length} />
              <CallList>
                {rows.map((r) => (
                  <PersonRow key={r.id ?? r.person.id} item={r} asOf={asOf} showEvent={false} showTier={false} rank={r.position} />
                ))}
              </CallList>
            </section>
          );
        })
      )}

      {people.context.length ? (
        <section className="space-y-3">
          <SectionHeader
            title="No money from this event"
            description={people.context[0]?.context_reason ?? "Named in the filings, but receive nothing from this event"}
            count={people.context.length}
          />
          <Collapsible items={people.context} asOf={asOf} showTier={false} />
        </section>
      ) : null}

      {people.entities.length ? (
        <section className="space-y-3">
          <SectionHeader
            title="Also on the register"
            description="Companies, funds and trusts named in the filings. Not individual calls, but useful for mapping relationships."
            count={people.entities.length}
          />
          <Collapsible items={people.entities} asOf={asOf} />
        </section>
      ) : null}
    </div>
  );
}
