import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { AdminGate } from "@/components/admin/admin-gate";
import { HealthView } from "@/components/admin/health-view";

export const metadata: Metadata = { title: "System health" };

export default function HealthPage() {
  return (
    <>
      <PageHeader title="System health" description="Sources, caches, today's spend against its limits, and any run that failed." />
      <AdminGate what="This page shows how the platform is running and what it costs.">
        <HealthView />
      </AdminGate>
    </>
  );
}
