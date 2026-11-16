import { BookUser } from "lucide-react";
import { cn } from "@/lib/utils";

/** "In your book": this person's name matches one in the RM's uploaded client list. */
export function InBookBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded-md bg-info-soft px-1.5 max-sm:px-1 text-[11px] font-medium whitespace-nowrap text-info ring-1 ring-info/15 ring-inset",
        className,
      )}
      title="This name is in the client list you uploaded"
    >
      <BookUser className="size-3" aria-hidden />
      <span className="max-sm:sr-only">In your book</span>
    </span>
  );
}
