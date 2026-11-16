import { Building2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";

export function Avatar({ name, entity = false, size = "md", className }: { name: string; entity?: boolean; size?: "sm" | "md" | "lg"; className?: string }) {
  const dim = size === "lg" ? "size-12 text-base" : size === "sm" ? "size-7 text-[11px]" : "size-9 text-xs";
  return (
    <span
      aria-hidden
      className={cn(
        "grid shrink-0 place-items-center rounded-full bg-surface-sunken font-semibold tracking-wide text-muted-foreground ring-1 ring-inset ring-border",
        dim,
        className,
      )}
    >
      {entity ? <Building2 className="size-4" /> : initials(name)}
    </span>
  );
}
