import { Banknote, KeyRound, Landmark } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Tier } from "@/lib/types";

const TIER: Record<Tier, { label: string; icon: typeof Banknote; cls: string }> = {
  cash_now: { label: "Cash in hand", icon: Banknote, cls: "bg-brand-soft text-brand-ink ring-brand/15" },
  unlock: { label: "Shares just unlocked", icon: KeyRound, cls: "bg-caution-soft text-caution ring-caution/15" },
  holding: { label: "Holds shares", icon: Landmark, cls: "bg-secondary text-muted-foreground ring-border" },
};

export function TierBadge({ tier, label, className }: { tier: Tier; label?: string; className?: string }) {
  const t = TIER[tier] ?? TIER.holding;
  const Icon = t.icon;
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-md px-2 text-xs font-medium ring-1 ring-inset",
        t.cls,
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {label ?? t.label}
    </span>
  );
}
