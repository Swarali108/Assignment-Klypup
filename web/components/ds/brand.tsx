import { cn } from "@/lib/utils";

/** FinSight mark: an authored monogram (an F: a stem and top bar, with a lighter middle bar). */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 28" className={cn("size-7", className)} aria-hidden>
      <rect x="1" y="1" width="26" height="26" rx="7" className="fill-brand" />
      <path d="M10 20.5 V7.5 H18.5" fill="none" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" className="stroke-brand-foreground" />
      <path d="M10 14 H16.5" fill="none" strokeWidth="2.1" strokeLinecap="round" className="stroke-brand-foreground opacity-70" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <BrandMark />
      <span className="flex flex-col leading-none">
        <span className="text-[13px] font-semibold tracking-wide text-foreground">FinSight</span>
        <span className="mt-1 text-[11px] text-muted-foreground">Wealth event desk</span>
      </span>
    </span>
  );
}
