"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { EmptyState, SkeletonCard } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";

/** The admin pages are for admins; everyone else gets a plain explanation instead of a failed load. */
export function AdminGate({ what, children }: { what: string; children: React.ReactNode }) {
  const { can, loading } = useSession();
  if (loading) return <SkeletonCard />;
  if (!can("ops"))
    return (
      <EmptyState
        icon={Lock}
        title="This page is for admins"
        action={
          <Button asChild variant="outline">
            <Link href="/today">Back to Today</Link>
          </Button>
        }
      >
        {what} Ask an admin if you need it.
      </EmptyState>
    );
  return <>{children}</>;
}
