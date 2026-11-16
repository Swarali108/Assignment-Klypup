import { Suspense } from "react";
import type { Metadata } from "next";
import { CallPackPrint } from "@/components/print/callpack-print";

export const metadata: Metadata = { title: "Call pack" };

export default async function CallPackPrintPage({ params }: PageProps<"/people/[eventId]/[personId]/print">) {
  const { eventId, personId } = await params;
  return (
    <Suspense>
      <CallPackPrint eventId={decodeURIComponent(eventId)} personId={decodeURIComponent(personId)} />
    </Suspense>
  );
}
