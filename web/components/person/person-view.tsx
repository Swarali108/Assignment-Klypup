"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Building2, Route, UserX } from "lucide-react";
import { api } from "@/lib/api";
import { Can, EmptyState, ErrorState, EvidenceViewer, RmStatusControl, SkeletonCard, SkeletonText } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RM_STATUS_LABEL } from "@/components/ds/rm-status-control";
import { rmText, useLoad } from "@/components/today/use-load";
import type { RmState, RmStatus } from "@/lib/types";
import { CallCard } from "./call-card";
import { AmountsSection, EventCard, EvidenceTrail, HouseholdCard, TimingSection } from "./sections";
import { EnrichmentPanels } from "./enrichment-panels";
import { TrailTab } from "./trail";
import { allEvidence, type Card, type TimingDetail } from "./types";
import { DownloadMenu } from "@/components/tower/download-menu";
import { callPackPrintHref, downloadCallPackMarkdown } from "@/lib/exports";
import { AssignControl } from "@/components/team/assign-control";
import { FollowButton } from "@/components/watch/follow-button";
import { ReviewedBy } from "@/components/review/review-view";

function Back() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
      <Link href="/today">
        <ArrowLeft /> Today
      </Link>
    </Button>
  );
}

export function PersonView({ eventId, personId }: { eventId: string; personId: string }) {
  const { load, retry } = useLoad<{ card: Card; asOf: string }>(async () => {
    const [card, summary] = await Promise.all([api.person(eventId, personId) as Promise<Card>, api.summary().catch(() => null)]);
    return { card, asOf: summary?.as_of ?? new Date().toISOString().slice(0, 10) };
  }, [eventId, personId]);
  const [rmStatus, setRmStatus] = useState<RmStatus | null>(null);

  // ?evidence=amount opens the headline amount's source; ?evidence=<n> opens the n-th source on the card.
  const params = useSearchParams();
  const evParam = params.get("evidence");
  const [evClosed, setEvClosed] = useState(false);
  // ?tab=trail opens "How we found them" directly.
  const [tab, setTab] = useState<"details" | "trail">(params.get("tab") === "trail" ? "trail" : "details");

  const deepEvidence = useMemo(() => {
    if (load.state !== "ready" || evParam === null) return null;
    const card = load.data.card;
    if (evParam === "amount") {
      const a = card.amounts.find((x) => x.key === card.amount.source) ?? card.amounts[0];
      return a?.inputs?.[0]?.evidence?.[0] ?? null;
    }
    return allEvidence(card)[Number(evParam)]?.evidence ?? null;
  }, [load, evParam]);

  if (load.state === "loading") return <PersonLoading />;
  if (load.state === "error") {
    const notFound = /not found|no such|unknown/i.test(load.reason);
    return (
      <div className="space-y-6">
        <Back />
        {notFound ? (
          <EmptyState
            icon={UserX}
            title="This person is not on any call list"
            action={
              <Button asChild variant="outline">
                <Link href="/today">Back to Today</Link>
              </Button>
            }
          >
            The link may be from an older run of this event. Open Today to see the current call list.
          </EmptyState>
        ) : (
          <ErrorState title="This call card could not be loaded" reason={load.reason} onRetry={retry} />
        )}
      </div>
    );
  }

  const { card, asOf } = load.data;
  const status = rmStatus ?? card.rm.status;
  const offList = card.list && card.list !== "callable";

  const save = async (next: RmState) => {
    const res = await api.saveRm(card.event.id, card.person.id, { status: next.status, note: next.note, follow_up_date: next.follow_up_date ?? "" });
    setRmStatus(res.status);
    return res;
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-3">
        <Back />
        <div className="flex flex-wrap items-center justify-end gap-2">
        <FollowButton kind="person" eventId={card.event.id} personId={card.person.id} />
        <FollowButton kind="company" eventId={card.event.id} label="Follow company" />
        <DownloadMenu
          label="Call pack"
          what="call pack"
          pdfHref={callPackPrintHref(card.event.id, card.person.id)}
          onMarkdown={() => downloadCallPackMarkdown(card.event.id, card.person.id, card.person.name)}
        />
        </div>
      </div>
      {(card as { reviewed?: { id: string; label: string; by: string; at: string | null }[] }).reviewed?.length ? (
        <div className="-mt-4 space-y-1">
          {(card as { reviewed?: { id: string; label: string; by: string; at: string | null }[] }).reviewed!.map((r) => (
            <ReviewedBy key={r.id} label={r.label} by={r.by} at={r.at} />
          ))}
        </div>
      ) : null}
      {offList ? (
        <div className="-mt-4 flex items-start gap-3 rounded-xl border bg-surface-sunken px-5 py-4">
          <Building2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <div>
            <p className="text-sm font-medium text-foreground">{card.list === "entities" ? "Also on the register, not on the call list" : "No money from this event"}</p>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              {rmText(card.context_reason) || (card.list === "entities" ? "This holder reads as a fund, trust or company rather than a person." : "This holder receives no money from this event.")}
            </p>
          </div>
        </div>
      ) : null}

      <CallCard card={card} asOf={asOf} rmStatus={status} />

      <Tabs value={tab} onValueChange={(v) => setTab(v as "details" | "trail")} className="gap-6">
        <TabsList variant="line" className="h-10 w-full justify-start gap-4 border-b border-hairline px-0 pb-0">
          <TabsTrigger value="details" className="flex-none px-1">
            The call card
          </TabsTrigger>
          <TabsTrigger value="trail" className="flex-none px-1">
            <Route aria-hidden /> How we found them
          </TabsTrigger>
        </TabsList>
        <TabsContent value="trail" className="min-w-0">
          <TrailTab
            eventId={card.event.id}
            personId={card.person.id}
            onOpenPanels={() => {
              setTab("details");
              setTimeout(() => document.getElementById("public-h")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
            }}
          />
        </TabsContent>
        <TabsContent value="details">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="min-w-0 space-y-10">
          <AmountsSection amounts={card.amounts} />
          <TimingSection timing={(card.timing_detail ?? []) as unknown as TimingDetail[]} />
          <EvidenceTrail card={card} defaultOpen={params.get("trail") === "open"} />
          <EnrichmentPanels eventId={card.event.id} personId={card.person.id} />
        </div>
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <section id="log-call" className="scroll-mt-24 rounded-xl border bg-surface p-5 shadow-(--shadow-card)">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-foreground">Log the call</h2>
              <AssignControl eventId={card.event.id} personId={card.person.id} />
            </div>
            <Can
              permission="edit_rm"
              fallback={
                <div className="space-y-2 text-sm">
                  <p className="text-foreground">{RM_STATUS_LABEL[card.rm.status]}</p>
                  {card.rm.note ? <p className="whitespace-pre-wrap text-muted-foreground">{card.rm.note}</p> : <p className="text-muted-foreground">No notes yet.</p>}
                  <p className="text-xs text-faint">Your role can view call notes but not edit them.</p>
                </div>
              }
            >
            <RmStatusControl
              eventId={card.event.id}
              personId={card.person.id}
              initial={{ status: card.rm.status, note: card.rm.note ?? "", follow_up_date: card.rm.follow_up_date ?? card.rm.follow_up ?? null, updated_at: card.rm.updated_at ?? null }}
              onSave={save}
              className="[&_.grid]:grid-cols-1"
            />
            </Can>
          </section>
          <HouseholdCard card={card} />
          <EventCard card={card} />
        </aside>
      </div>
        </TabsContent>
      </Tabs>

      {deepEvidence ? <EvidenceViewer evidence={deepEvidence} open={!evClosed} onOpenChange={(o) => setEvClosed(!o)} /> : null}
    </div>
  );
}

function PersonLoading() {
  return (
    <div className="space-y-8" role="status" aria-label="Loading the call card">
      <Back />
      <div className="overflow-hidden rounded-2xl border bg-surface">
        <div className="flex gap-4 p-8">
          <Skeleton className="size-12 rounded-full" />
          <div className="flex-1 space-y-3">
            <Skeleton className="h-7 w-72 max-w-full" />
            <Skeleton className="h-4 w-96 max-w-full" />
            <Skeleton className="h-6 w-32" />
          </div>
        </div>
        <div className="grid gap-6 border-y bg-surface-sunken/50 p-8 md:grid-cols-3">
          <Skeleton className="h-10 w-40" />
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-10 w-44" />
        </div>
        <div className="p-8">
          <SkeletonText lines={3} />
        </div>
      </div>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}
