import type { Metadata } from "next";
import { PageHeader } from "@/components/ds";
import { AdminGate } from "@/components/admin/admin-gate";
import { PipelineConsole } from "@/components/admin/pipeline-console";

export const metadata: Metadata = { title: "Pipeline console" };

export default function PipelinePage() {
  return (
    <>
      <PageHeader
        title="Pipeline console"
        description="Run an event by hand: every step or just one, from the answer cache or with every model call paid for again. Watch it live, then compare it with the run before."
      />
      <AdminGate what="This page runs the pipeline and can spend money.">
        <PipelineConsole />
      </AdminGate>
    </>
  );
}
