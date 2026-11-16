import { Suspense } from "react";
import { PersonView } from "@/components/person/person-view";

export const metadata = { title: "Call card" };

export default async function PersonPage({ params }: PageProps<"/people/[eventId]/[personId]">) {
  const { eventId, personId } = await params;
  return (
    <Suspense>
      <PersonView eventId={decodeURIComponent(eventId)} personId={decodeURIComponent(personId)} />
    </Suspense>
  );
}
