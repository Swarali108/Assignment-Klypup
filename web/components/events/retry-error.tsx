"use client";

import { useRouter } from "next/navigation";
import { ErrorState } from "@/components/ds";

/** Server-page error with a working "Try again" (re-renders the route). */
export function RetryError({ title, reason }: { title?: string; reason: string }) {
  const router = useRouter();
  return <ErrorState title={title} reason={reason} onRetry={() => router.refresh()} />;
}
