"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Banknote, CalendarPlus, Inbox, Layers, PhoneCall, UserX } from "lucide-react";
import {
  CallList,
  ConfidenceBadge,
  EmptyState,
  ErrorState,
  EvidenceChip,
  EvidenceViewer,
  Money,
  PageHeader,
  PersonCardHeader,
  PersonRow,
  RmStatusControl,
  SectionHeader,
  SkeletonCard,
  SkeletonList,
  SkeletonStat,
  SkeletonText,
  StatCard,
  StatStrip,
  StatusBadge,
  TierBadge,
  TimingPill,
  useCommandPalette,
} from "@/components/ds";
import { Button } from "@/components/ui/button";
import { fixtures } from "@/lib/fixtures";
import { formatCrCompact } from "@/lib/format";
import type { RmState } from "@/lib/types";

const asOf = fixtures.summary.as_of;

function Block({ title, note, children, id }: { title: string; note?: string; children: React.ReactNode; id: string }) {
  return (
    <section id={id} className="scroll-mt-20 space-y-4 border-t pt-8">
      <SectionHeader title={title} description={note} />
      {children}
    </section>
  );
}

function Specimen({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2.5 rounded-xl border bg-surface p-4">
      <span className="text-[11px] font-medium text-faint">{label}</span>
      <div className="flex min-w-0 flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

export function Gallery() {
  const { setOpen } = useCommandPalette();
  const initialViewer = useSearchParams().get("viewer");
  const [viewer, setViewer] = useState<"hl" | "plain" | null>(initialViewer === "hl" || initialViewer === "plain" ? initialViewer : null);
  useEffect(() => {
    if (initialViewer === "palette") setOpen(true);
  }, [initialViewer, setOpen]);
  const t = fixtures.today;
  const unknown = t.find((r) => r.amount.value_cr === null)!;
  const shares = t.find((r) => r.amount.kind === "shares")!;
  const cash = t.find((r) => r.amount.kind === "cash" && r.amount.value_cr !== null)!;
  const household = t.find((r) => r.members?.length)!;
  const ev = fixtures.evidence;
  const mockSave = async (s: RmState): Promise<RmState> => {
    await new Promise((r) => setTimeout(r, 400));
    return { ...s, updated_at: new Date().toISOString() };
  };

  return (
    <div className="space-y-12">
      <PageHeader
        title="Component gallery"
        description="Every building block and state, rendered with real SEDEMAC and Spacenet data."
        actions={
          <Button variant="outline" onClick={() => setOpen(true)}>
            Open search <kbd className="ml-1 rounded border bg-secondary px-1 text-[11px]">⌘K</kbd>
          </Button>
        }
      />

      <Block id="money" title="Money" note="Crore in Indian grouping with tabular numerals. Unknown is never ₹0.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Specimen label="Cash, exact">
            <Money value={92.05} kind="cash" size="lg" showKind />
          </Specimen>
          <Specimen label="Cash, estimate">
            <Money amount={cash.amount} size="lg" showKind />
          </Specimen>
          <Specimen label="Shares, not cash">
            <Money amount={shares.amount} size="lg" showKind />
          </Specimen>
          <Specimen label="Not disclosed, with reason">
            <Money amount={unknown.amount} size="lg" />
          </Specimen>
        </div>
        <Specimen label="Sizes">
          <Money value={1234567.89} size="xl" />
          <Money value={166.9} size="lg" />
          <Money value={6.08} size="md" />
          <Money value={0.24} size="sm" />
        </Specimen>
      </Block>

      <Block id="badges" title="Tier, timing, confidence, status">
        <div className="grid gap-3 lg:grid-cols-2">
          <Specimen label="TierBadge">
            <TierBadge tier="cash_now" />
            <TierBadge tier="cash_now" label="Cash due soon" />
            <TierBadge tier="unlock" />
            <TierBadge tier="holding" />
          </Specimen>
          <Specimen label="ConfidenceBadge (hover for reason)">
            <ConfidenceBadge confidence={{ level: "high", reason: "Name, shares and price all read from the same filing table" }} />
            <ConfidenceBadge confidence={{ level: "medium", reason: "Shares verified; amount is valued at the offer price" }} />
            <ConfidenceBadge confidence={{ level: "low", reason: "Only part of the holding could be matched to a table row" }} />
          </Specimen>
          <Specimen label="TimingPill">
            <div className="flex flex-col gap-2.5">
              <TimingPill timing={{ label: "In hand since 11 Mar 2026", status: "in_hand", date_iso: "2026-03-11" }} asOf={asOf} />
              <TimingPill timing={{ label: "Listing on 26 Nov 2026", status: "scheduled", date_iso: "2026-11-26" }} asOf={asOf} />
              <TimingPill timing={{ label: "Listing was due 21 Oct 2026 (25 days ago); listing notice not yet seen", status: "due_past", date_iso: "2026-10-21" }} asOf={asOf} />
              <TimingPill timing={{ label: "Unlocked since 9 Sep 2026", status: "unlocked", date_iso: "2026-09-09" }} asOf={asOf} />
              <TimingPill timing={{ label: "Locked until 9 Sep 2027", status: "locked_in", date_iso: "2027-09-09" }} asOf={asOf} />
              <TimingPill timing={{ label: "Settled after the sale on 21 Apr 2026", status: "past", date_iso: "2026-04-21" }} asOf={asOf} />
              <TimingPill timing={{ label: "Timing not printed in the filing", status: "unknown", date_iso: null }} asOf={asOf} />
            </div>
          </Specimen>
          <Specimen label="StatusBadge">
            <div className="grid gap-4 sm:grid-cols-2">
              <StatusBadge status="ready" />
              <StatusBadge status="processing" />
              <StatusBadge status="scanned" />
              <StatusBadge status="failed" reason="The prospectus link stopped responding, so the last good call list is kept" />
              <StatusBadge status="not_supported" reason="Employee stock buybacks are not covered yet" />
              <StatusBadge status="not_processed" reason="Found in today's filings; not read yet" />
            </div>
          </Specimen>
        </div>
      </Block>

      <Block id="stats" title="StatCard and StatStrip">
        <StatStrip>
          <StatCard label="People to call" icon={PhoneCall} value={fixtures.summary.people_to_call} />
          <StatCard label="Cash in hand" icon={Banknote} value={formatCrCompact(fixtures.summary.cash_now_cr)} sub="Across people with proceeds now" />
          <StatCard label="New events this week" icon={CalendarPlus} value={fixtures.summary.new_events_this_week} />
          <StatCard label="Events covered" icon={Layers} value="–" muted sub="Not available yet" />
        </StatStrip>
      </Block>

      <Block id="rows" title="PersonRow" note="Call-list row; the household row expands to its members.">
        <CallList>
          {t.slice(0, 2).map((r, i) => (
            <PersonRow key={r.person.id} item={r} asOf={asOf} rank={i + 1} />
          ))}
          <PersonRow item={household} asOf={asOf} rank={3} />
          <PersonRow item={shares} asOf={asOf} rank={4} />
          <PersonRow
            item={unknown}
            asOf={asOf}
            rank={5}
            actions={
              <Button size="sm" variant="outline">
                Called
              </Button>
            }
          />
        </CallList>
      </Block>

      <Block id="card" title="PersonCardHeader" note="Top of the 2-minute call card.">
        <PersonCardHeader card={fixtures.person} asOf={asOf} />
      </Block>

      <Block id="evidence" title="EvidenceChip and EvidenceViewer" note="Source page image from the filing, quote highlighted; or the plain page with the quote beside it.">
        <Specimen label="Chips: quote marked · quote not marked · filing not stored">
          <EvidenceChip evidence={ev} imageSrc="/fixtures/evidence-highlight.png" highlight />
          <EvidenceChip evidence={{ ...ev, doc_label: "Red herring prospectus" }} imageSrc="/fixtures/evidence-plain.png" highlight={false} />
          <EvidenceChip evidence={{ ...ev, cached: false }} />
        </Specimen>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setViewer("hl")}>
            Viewer: quote found
          </Button>
          <Button variant="outline" onClick={() => setViewer("plain")}>
            Viewer: quote not found on page
          </Button>
        </div>
        <EvidenceViewer evidence={ev} imageSrc="/fixtures/evidence-highlight.png" highlight open={viewer === "hl"} onOpenChange={(o) => setViewer(o ? "hl" : null)} />
        <EvidenceViewer evidence={ev} imageSrc="/fixtures/evidence-plain.png" highlight={false} open={viewer === "plain"} onOpenChange={(o) => setViewer(o ? "plain" : null)} />
      </Block>

      <Block id="rm" title="RmStatusControl" note="Saves to a mock in the gallery; on real pages it saves to the desk's notes.">
        <div className="rounded-xl border bg-surface p-6">
          <RmStatusControl eventId="sedemac_ipo" personId="p_manish_sharma" initial={fixtures.person.rm} onSave={mockSave} />
        </div>
      </Block>

      <Block id="states" title="Empty, error and loading states">
        <div className="grid gap-4 lg:grid-cols-2">
          <EmptyState icon={UserX} title="No one to call from this event">
            Jio Platforms is a fresh issue by the company: no individual shareholder sells shares in it, so no one on the register receives money.
          </EmptyState>
          <EmptyState icon={Inbox} title="You are all caught up" tone="brand" action={<Button variant="outline">Show calls marked Not now</Button>}>
            Every person on today&apos;s list has a status. New events appear here as soon as they are read.
          </EmptyState>
          <ErrorState
            title="Processing stopped at “Reading the tables”"
            reason="The prospectus link stopped responding. The last good call list for this event is kept."
            onRetry={() => {}}
            retryLabel="Process again"
          />
          <ErrorState title="Could not load today's calls" reason="The data service is not reachable. Start it and try again." onRetry={() => {}} />
        </div>
        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <SkeletonList rows={3} />
          <div className="space-y-4">
            <div className="rounded-xl border bg-surface">
              <SkeletonStat />
            </div>
            <SkeletonCard />
            <SkeletonText lines={2} />
          </div>
        </div>
      </Block>

      <Block id="dark" title="Dark surface" note="The same components under the dark theme tokens.">
        <div className="dark rounded-2xl bg-background p-6 text-foreground">
          <div className="space-y-4">
            <StatStrip>
              <StatCard label="People to call" icon={PhoneCall} value={fixtures.summary.people_to_call} />
              <StatCard label="Cash in hand" icon={Banknote} value={formatCrCompact(fixtures.summary.cash_now_cr)} />
              <StatCard label="New events this week" icon={CalendarPlus} value={fixtures.summary.new_events_this_week} />
              <StatCard label="Events covered" icon={Layers} value={fixtures.summary.events_processed} />
            </StatStrip>
            <CallList>
              <PersonRow item={t[0]} asOf={asOf} rank={1} />
              <PersonRow item={shares} asOf={asOf} rank={2} />
              <PersonRow item={unknown} asOf={asOf} rank={3} />
            </CallList>
            <div className="flex flex-wrap gap-3">
              <TierBadge tier="cash_now" />
              <TierBadge tier="unlock" />
              <TierBadge tier="holding" />
              <StatusBadge status="ready" />
              <StatusBadge status="failed" />
              <StatusBadge status="scanned" reason={null} />
              <EvidenceChip evidence={ev} imageSrc="/fixtures/evidence-highlight.png" highlight />
            </div>
          </div>
        </div>
      </Block>
    </div>
  );
}
