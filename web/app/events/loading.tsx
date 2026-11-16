import { PageHeader, SkeletonCard } from "@/components/ds";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading events">
      <PageHeader title="Events" description="IPOs, buybacks and offers for sale we read, and who gets money from each." />
      <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="space-y-4">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-10 w-96 max-w-full rounded-lg" />
          <div className="grid gap-4 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} className="h-[13.5rem]" />
            ))}
          </div>
        </div>
        <div className="space-y-3 rounded-xl border bg-surface p-5">
          <Skeleton className="h-4 w-32" />
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex gap-3 py-2">
              <Skeleton className="h-9 w-9 rounded-md" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3.5 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
