import Link from "next/link";
import type { Metadata } from "next";
import { ArrowLeft, SearchX } from "lucide-react";
import { EmptyState, StatStrip, StatCard } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { formatCrCompact } from "@/lib/format";
import { eventsApi } from "@/components/events/api";
import { EventLive } from "@/components/events/event-live";
import { EventPeopleSections } from "@/components/events/event-people";
import { FactsStrip } from "@/components/events/facts-strip";
import { RetryError } from "@/components/events/retry-error";
import { TraceView } from "@/components/events/trace-view";
import type { EventPeople, EventRuns, EventTrace } from "@/components/events/types";

export async function generateMetadata({ params }: PageProps<"/events/[id]">): Promise<Metadata> {
  const { id } = await params;
  try {
    const e = await eventsApi.detail(id);
    return { title: e.company };
  } catch {
    return { title: "Event" };
  }
}

function Back() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 mb-4 text-muted-foreground">
      <Link href="/events">
        <ArrowLeft /> Events
      </Link>
    </Button>
  );
}

export default async function EventPage({ params, searchParams }: PageProps<"/events/[id]">) {
  const { id } = await params;
  const sp = await searchParams;
  const job = typeof sp.job === "string" ? sp.job : null;

  let event;
  try {
    event = await eventsApi.detail(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return (
        <>
          <Back />
          <EmptyState
            icon={SearchX}
            title="We could not find this event"
            action={
              <Button asChild variant="outline" size="sm">
                <Link href="/events">See all events</Link>
              </Button>
            }
          >
            It may have been renamed or removed. Every event we read is on the events list.
          </EmptyState>
        </>
      );
    }
    return (
      <>
        <Back />
        <RetryError title="This event could not be loaded" reason={e instanceof ApiError ? e.message : "The data service did not answer."} />
      </>
    );
  }

  // A new event has no call list yet; show it as empty rather than as an error.
  let people: EventPeople;
  try {
    people = await eventsApi.people(id);
  } catch {
    people = { event, callable: [], entities: [], context: [], empty_reason: null };
  }

  // How the list was built: absent until the event has been processed once.
  const [trace, runs] = await Promise.all([
    eventsApi.trace(id).catch((): EventTrace | null => null),
    eventsApi.runs(id).catch((): EventRuns | null => null),
  ]);

  const tc = event.tier_counts ?? {};
  const hasCalls = people.callable.length > 0;

  return (
    <>
      <Back />
      <EventLive event={event} process={sp.process === "1"} job={job}>
        <div className="space-y-10">
          <FactsStrip event={event} />
          {hasCalls ? (
            <StatStrip>
              <StatCard label="People to call" value={people.callable.length} sub={event.entities_count ? `${event.entities_count} companies and funds also named` : "No separate companies or funds named"} />
              <StatCard
                label="Cash in hand"
                value={formatCrCompact(event.cash_cr) ?? (tc.cash_now ? "Not disclosed" : "None yet")}
                muted={event.cash_cr === null}
                sub={
                  tc.cash_now
                    ? `${tc.cash_now} ${tc.cash_now === 1 ? "person" : "people"} with sale proceeds${event.cash_cr === null ? "; amounts not printed" : ""}`
                    : "No one sells in this event"
                }
              />
              <StatCard label="Shares just unlocked" value={tc.unlock ?? 0} sub="Lock-in ended recently" />
              <StatCard label="Holds shares" value={tc.holding ?? 0} sub="Still locked in or no money date" />
            </StatStrip>
          ) : null}
          <EventPeopleSections event={event} people={people} />
          {trace ? <TraceView trace={trace} runs={runs} /> : null}
        </div>
      </EventLive>
    </>
  );
}
