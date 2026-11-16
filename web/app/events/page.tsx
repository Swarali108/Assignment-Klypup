import type { Metadata } from "next";
import { Can, PageHeader, SectionHeader } from "@/components/ds";
import { ApiError, api } from "@/lib/api";
import { AddEventDialog } from "@/components/events/add-event-dialog";
import { eventsApi } from "@/components/events/api";
import { EventsGrid } from "@/components/events/events-grid";
import { FeedPanel } from "@/components/events/feed-panel";
import { RetryError } from "@/components/events/retry-error";
import { AutoChip } from "@/components/sources/auto-chip";
import { CheckNowButton } from "@/components/sources/check-now";

export const metadata: Metadata = { title: "Events" };

export default async function EventsPage({ searchParams }: PageProps<"/events">) {
  const sp = await searchParams;
  const [eventsRes, feedRes, summaryRes] = await Promise.allSettled([eventsApi.list(), eventsApi.feed(), api.summary()]);
  const events = eventsRes.status === "fulfilled" ? eventsRes.value.events : null;
  const feed = feedRes.status === "fulfilled" ? feedRes.value : null;
  const err = (r: PromiseSettledResult<unknown>) =>
    r.status === "rejected" ? (r.reason instanceof ApiError ? r.reason.message : "The data service did not answer.") : null;
  const asOf = summaryRes.status === "fulfilled" ? summaryRes.value.as_of : (feed?.refreshed_at?.slice(0, 10) ?? new Date().toISOString().slice(0, 10));

  return (
    <>
      <PageHeader
        title="Events"
        description="IPOs, buybacks and offers for sale we read, and who gets money from each."
        actions={
          <div className="flex max-w-[calc(100vw-2rem)] flex-wrap items-center gap-2 lg:max-w-none">
            <AutoChip />
            <CheckNowButton />
            <Can permission="process">
              <AddEventDialog asOf={asOf} defaultOpen={sp.add === "1"} />
            </Can>
          </div>
        }
      />
      <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_23rem]">
        <section aria-labelledby="processed-title" className="min-w-0 space-y-4">
          <SectionHeader
            title={<span id="processed-title">Processed events</span>}
            count={events?.filter((e) => e.status === "ready").length}
            description="Every amount traced to its filing page. Scanned filings that cannot be read yet are marked on the card."
          />
          {events ? (
            <EventsGrid events={events} />
          ) : (
            <RetryError title="Events could not be loaded" reason={err(eventsRes) ?? ""} />
          )}
        </section>
        <aside className="order-first min-w-0 xl:sticky xl:top-20 xl:order-none">
          {feed ? <FeedPanel feed={feed} events={events ?? []} initialGroup={typeof sp.feed === "string" ? sp.feed : undefined} /> : <RetryError title="New filings could not be loaded" reason={err(feedRes) ?? ""} />}
        </aside>
      </div>
    </>
  );
}
