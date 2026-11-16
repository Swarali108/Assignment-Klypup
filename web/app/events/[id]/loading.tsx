import { SkeletonList } from "@/components/ds";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading event">
      <Skeleton className="mb-6 h-7 w-20" />
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2.5">
          <Skeleton className="h-8 w-80 max-w-full" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-9 w-32 rounded-lg" />
      </div>
      <div className="space-y-10">
        <div className="grid gap-px overflow-hidden rounded-xl border bg-hairline sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-2.5 bg-surface px-5 py-4">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-3 w-24" />
            </div>
          ))}
        </div>
        <div className="space-y-3">
          <Skeleton className="h-4 w-36" />
          <SkeletonList rows={6} />
        </div>
      </div>
    </div>
  );
}
