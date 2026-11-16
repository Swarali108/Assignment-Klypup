import { AlertTriangle, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
  tone = "neutral",
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  tone?: "neutral" | "brand" | "caution";
}) {
  return (
    <div className={cn("flex flex-col items-center rounded-xl border border-dashed bg-surface px-6 py-12 text-center", className)}>
      <span
        className={cn(
          "mb-4 grid size-11 place-items-center rounded-full",
          tone === "brand" ? "bg-brand-soft text-brand-ink" : tone === "caution" ? "bg-caution-soft text-caution" : "bg-secondary text-muted-foreground",
        )}
      >
        <Icon className="size-5" />
      </span>
      <h3 className="text-[15px] font-semibold text-foreground">{title}</h3>
      {children ? <div className="mt-1.5 max-w-[52ch] text-sm leading-relaxed text-muted-foreground">{children}</div> : null}
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  reason,
  onRetry,
  retryLabel = "Try again",
  children,
  className,
}: {
  title?: string;
  reason: string;
  onRetry?: () => void;
  retryLabel?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("flex items-start gap-4 rounded-xl border border-negative/20 bg-negative-soft/60 p-5", className)}>
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-negative-soft text-negative">
        <AlertTriangle className="size-4.5" />
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="text-[15px] font-semibold text-foreground">{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{reason}</p>
        {children}
        {onRetry ? (
          <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
            <RotateCw /> {retryLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-3.5" style={{ width: `${i === lines - 1 ? 60 : 100 - i * 6}%` }} />
      ))}
    </div>
  );
}

export function SkeletonRow({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-4 px-5 py-4", className)} aria-hidden>
      <Skeleton className="size-9 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-3.5 w-48" />
        <Skeleton className="h-3 w-72 max-w-full" />
      </div>
      <Skeleton className="hidden h-6 w-28 md:block" />
      <Skeleton className="h-5 w-20" />
    </div>
  );
}

export function SkeletonList({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("divide-y divide-hairline overflow-hidden rounded-xl border bg-surface", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}

export function SkeletonStat({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-3 px-5 py-4", className)} aria-hidden>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-6 w-32" />
    </div>
  );
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-4 rounded-xl border bg-surface p-5", className)} aria-hidden>
      <div className="flex items-center gap-3">
        <Skeleton className="size-10 rounded-full" />
        <div className="space-y-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-56" />
        </div>
      </div>
      <SkeletonText lines={3} />
    </div>
  );
}
