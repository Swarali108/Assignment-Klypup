import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Confidence } from "@/lib/types";

const LEVEL = { high: 3, medium: 2, low: 1 } as const;
const LABEL = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" } as const;

/** Three-step signal glyph + label; the reason shows on hover (and inline when `showReason`). */
export function ConfidenceBadge({
  confidence,
  showReason = false,
  compact = false,
  className,
}: {
  confidence: Confidence;
  showReason?: boolean;
  compact?: boolean;
  className?: string;
}) {
  const n = LEVEL[confidence.level] ?? 1;
  const tone = n === 3 ? "bg-positive" : n === 2 ? "bg-caution" : "bg-negative";
  const glyph = (
    <span className="inline-flex h-3 items-end gap-[2px]" aria-hidden>
      {[1, 2, 3].map((i) => (
        <span
          key={i}
          className={cn("w-[3px] rounded-[1px]", i <= n ? tone : "bg-border")}
          style={{ height: `${4 + i * 3}px` }}
        />
      ))}
    </span>
  );
  const body = (
    <span className={cn("inline-flex items-center gap-2 text-[13px]", className)}>
      {glyph}
      <span className={cn(compact && "sr-only")}>{LABEL[confidence.level]}</span>
    </span>
  );
  if (showReason) {
    return (
      <span className="inline-flex flex-col gap-1">
        {body}
        <span className="text-xs leading-snug text-muted-foreground">{confidence.reason}</span>
      </span>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="cursor-default rounded-sm">
          {body}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{confidence.reason}</TooltipContent>
    </Tooltip>
  );
}
