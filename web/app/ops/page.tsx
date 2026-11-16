import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { OpsGate } from "@/components/insights/ops-gate";
import { OpsView } from "@/components/insights/ops-view";

export const metadata: Metadata = { title: "Trust & Ops" };

export default function OpsPage() {
  return (
    <>
      <PageHeader title="Trust & Ops" description="How we know: every value checked against the filings, what each event cost to read, and how long each step took." />
      <OpsGate>
        <OpsView />
      </OpsGate>
    </>
  );
}
