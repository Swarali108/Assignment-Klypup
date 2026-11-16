import { cn } from "@/lib/utils";

const TITLE: Record<string, string> = {
  SEBI: "From SEBI's public filing lists",
  NSE: "From NSE (read on the owner's call; NSE's terms forbid automated collection)",
  BSE: "From BSE (read on the owner's call; BSE's terms forbid reproduction)",
};

/** Who published a filing: SEBI, NSE or BSE. Neutral on purpose: the owner is a fact, not a status. */
export function SourceBadge({ owner, className }: { owner?: string | null; className?: string }) {
  if (!owner || owner === "Other") return null;
  return (
    <span
      title={TITLE[owner] ?? owner}
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center rounded-[5px] px-1.5 text-[10.5px] font-semibold tracking-[0.02em] text-muted-foreground ring-1 ring-inset ring-border",
        owner !== "SEBI" && "bg-surface-sunken",
        className,
      )}
    >
      {owner}
    </span>
  );
}
