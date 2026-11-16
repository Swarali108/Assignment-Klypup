import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { AdminGate } from "@/components/admin/admin-gate";
import { AccuracyView } from "@/components/admin/accuracy-view";

export const metadata: Metadata = { title: "Accuracy" };

export default function AccuracyPage() {
  return (
    <>
      <PageHeader title="Accuracy" description="The call lists scored against people whose figures were read by hand from the filings. Every miss links to the page it should have come from." />
      <AdminGate what="This page scores the pipeline against hand-read filings.">
        <AccuracyView />
      </AdminGate>
    </>
  );
}
