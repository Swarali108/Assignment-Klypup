"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { EmptyState, SkeletonCard } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";

/** Trust & Ops is for admins; everyone else gets a plain explanation instead of a failed load. */
export function OpsGate({ children }: { children: React.ReactNode }) {
  const { can, loading } = useSession();
  if (loading) return <SkeletonCard />;
  if (!can("ops"))
    return (
      <EmptyState
        icon={Lock}
        title="Trust & Ops is for admins"
        action={
          <Button asChild variant="outline">
            <Link href="/today">Back to Today</Link>
          </Button>
        }
      >
        This page shows how every value was checked and what each event cost to read. Ask an admin if you need it.
      </EmptyState>
    );
  return <>{children}</>;
}
