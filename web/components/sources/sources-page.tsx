"use client";

import Link from "next/link";
import { useState } from "react";
import { Lock } from "lucide-react";
import { EmptyState, PageHeader, SkeletonCard } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";
import { AutoLogView } from "./auto-log";
import { CheckNowButton } from "./check-now";
import { SourcesView } from "./sources-view";

/** Sources (admin): every signal source, "Check for new filings now", and the auto-processing log. */
export function SourcesPage() {
  const { can, loading } = useSession();
  const [round, setRound] = useState(0);
  const header = (
    <PageHeader
      title="Sources"
      description="Where new filings come from, whether each source is on, what reading it risks, and what ran automatically."
      actions={can("process") ? <CheckNowButton onFinished={() => setRound((n) => n + 1)} /> : undefined}
    />
  );
  if (loading)
    return (
      <>
        {header}
        <SkeletonCard />
      </>
    );
  if (!can("ops"))
    return (
      <>
        {header}
        <EmptyState
          icon={Lock}
          title="Sources is for admins"
          action={
            <Button asChild variant="outline">
              <Link href="/today">Back to Today</Link>
            </Button>
          }
        >
          This page shows which filing sources are read, their terms and risks, and what was processed automatically. Ask an admin if you need it.
        </EmptyState>
      </>
    );
  return (
    <>
      {header}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-10 xl:grid-cols-[minmax(0,1fr)_26rem]">
        <SourcesView key={`s-${round}`} />
        <div className="min-w-0 xl:sticky xl:top-20">
          <AutoLogView key={`a-${round}`} />
        </div>
      </div>
    </>
  );
}
