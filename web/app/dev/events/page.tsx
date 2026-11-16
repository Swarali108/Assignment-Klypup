import { SectionHeader, PageHeader } from "@/components/ds";
import { EventsGallery } from "@/components/events/gallery";

export const metadata = { title: "Events gallery" };

/** Design states for the Events screens (progress panel, add-from-links proposals). Not linked from the app. */
export default async function DevEventsPage({ searchParams }: PageProps<"/dev/events">) {
  const sp = await searchParams;
  return (
    <>
      <PageHeader title="Events: design states" description="Live processing and add-from-links states, from captured responses." />
      <SectionHeader title="Processing panel" className="mb-4" />
      <EventsGallery dialog={typeof sp.dialog === "string" ? sp.dialog : null} />
    </>
  );
}
