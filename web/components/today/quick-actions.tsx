"use client";

import { useState } from "react";
import { CalendarClock, Check, Loader2, MoonStar, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { formatDate, formatDateShort } from "@/lib/format";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { RmStatus } from "@/lib/types";

export type RowRm = { status: RmStatus; follow_up: string | null; note?: string };

export const HANDLED = new Set<RmStatus>(["called", "meeting_booked", "won", "not_now", "not_a_fit"]);
const DONE_LABEL: Partial<Record<RmStatus, string>> = { called: "Called", not_now: "Not now", not_a_fit: "Not a fit" };

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Save an RM status from a list row. Resolves to the stored state, or throws with a plain message. */
export async function saveRowRm(eventId: string, personId: string, patch: { status: RmStatus; follow_up_date?: string }) {
  const res = await api.saveRm(eventId, personId, { status: patch.status, follow_up_date: patch.follow_up_date ?? "" });
  return { status: res.status, follow_up: res.follow_up_date, note: res.note } satisfies RowRm;
}

/**
 * Called / Follow up / Not now for one queue row. Labels show on wide screens and phones; between
 * 1024 and 1360 px the group collapses to icons with tooltips so the row keeps its columns.
 */
export function QuickActions({
  name,
  rm,
  asOf,
  onSave,
  className,
}: {
  name: string;
  rm: RowRm;
  asOf: string;
  onSave: (patch: { status: RmStatus; follow_up_date?: string }) => Promise<void>;
  className?: string;
}) {
  const [busy, setBusy] = useState<RmStatus | null>(null);
  const [fuOpen, setFuOpen] = useState(false);
  const [custom, setCustom] = useState("");

  const run = async (status: RmStatus, follow_up_date?: string) => {
    setBusy(status);
    setFuOpen(false);
    try {
      await onSave({ status, follow_up_date });
    } finally {
      setBusy(null);
    }
  };

  if (HANDLED.has(rm.status)) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <span className="inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-positive-soft px-2.5 text-[13px] font-medium text-positive">
          <Check className="size-3.5" aria-hidden />
          {DONE_LABEL[rm.status]}
        </span>
        <button
          type="button"
          onClick={() => run("to_call")}
          disabled={busy !== null}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-60"
          aria-label={`Move ${name} back to the call list`}
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
          <span className="lg:max-[1359px]:sr-only">Undo</span>
        </button>
      </div>
    );
  }

  const options = [
    { label: "Tomorrow", date: addDays(asOf, 1) },
    { label: "In 3 days", date: addDays(asOf, 3) },
    { label: "Next week", date: addDays(asOf, 7) },
  ];
  const fuLabel = rm.status === "follow_up" && rm.follow_up ? `Follow up ${formatDateShort(rm.follow_up)}` : "Follow up";

  const seg =
    "inline-flex h-8 flex-1 items-center justify-center gap-1.5 px-2.5 text-[13px] font-medium whitespace-nowrap transition-colors disabled:opacity-60 lg:flex-none lg:max-[1359px]:w-9 lg:max-[1359px]:px-0";
  const label = "lg:max-[1359px]:sr-only";

  return (
    <div
      role="group"
      aria-label={`Log the call with ${name}`}
      className={cn("flex divide-x divide-border overflow-hidden rounded-lg border bg-surface shadow-(--shadow-card)", className)}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className={cn(seg, "text-foreground hover:bg-brand-soft hover:text-brand-ink")} disabled={busy !== null} onClick={() => run("called")}>
            {busy === "called" ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" aria-hidden />}
            <span className={label}>Called</span>
          </button>
        </TooltipTrigger>
        <TooltipContent>Mark as called</TooltipContent>
      </Tooltip>

      <Popover open={fuOpen} onOpenChange={setFuOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(
              seg,
              rm.status === "follow_up" ? "bg-info-soft text-info hover:bg-info-soft" : "text-foreground hover:bg-accent",
            )}
            disabled={busy !== null}
            aria-label={rm.status === "follow_up" && rm.follow_up ? `Follow up on ${formatDate(rm.follow_up)}; change` : "Set a follow-up"}
          >
            {busy === "follow_up" ? <Loader2 className="size-3.5 animate-spin" /> : <CalendarClock className="size-3.5" aria-hidden />}
            <span className={cn(label, rm.status === "follow_up" && "tnum")}>{rm.status === "follow_up" ? fuLabel.replace("Follow up ", "") : fuLabel}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-60 p-2">
          <p className="px-2 pt-1 pb-2 text-xs font-medium text-muted-foreground">Remind me to call back</p>
          <div className="grid gap-0.5">
            {options.map((o) => (
              <button
                key={o.label}
                type="button"
                onClick={() => run("follow_up", o.date)}
                className="flex h-8 items-center justify-between rounded-md px-2 text-sm hover:bg-accent"
              >
                {o.label}
                <span className="tnum text-xs text-muted-foreground">{formatDateShort(o.date)}</span>
              </button>
            ))}
          </div>
          <form
            className="mt-2 flex gap-1.5 border-t pt-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (custom) run("follow_up", custom);
            }}
          >
            <input
              type="date"
              value={custom}
              min={asOf}
              onChange={(e) => setCustom(e.target.value)}
              aria-label="Pick a date"
              className="tnum h-8 min-w-0 flex-1 rounded-md border bg-surface px-2 text-sm"
            />
            <button type="submit" disabled={!custom} className="h-8 rounded-md bg-primary px-2.5 text-[13px] font-medium text-primary-foreground disabled:opacity-50">
              Set
            </button>
          </form>
        </PopoverContent>
      </Popover>

      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className={cn(seg, "text-muted-foreground hover:bg-accent hover:text-foreground")} disabled={busy !== null} onClick={() => run("not_now")}>
            {busy === "not_now" ? <Loader2 className="size-3.5 animate-spin" /> : <MoonStar className="size-3.5" aria-hidden />}
            <span className={label}>Not now</span>
          </button>
        </TooltipTrigger>
        <TooltipContent>Not now</TooltipContent>
      </Tooltip>
    </div>
  );
}

export function notifySaved(name: string, status: RmStatus, follow?: string | null, undo?: () => void) {
  const first = name.split(/\s+/)[0];
  const msg =
    status === "called"
      ? `${first} marked as called`
      : status === "not_now"
        ? `${first} moved to not now`
        : status === "follow_up"
          ? `Follow up with ${first} on ${formatDate(follow ?? null) ?? "the chosen date"}`
          : `${first} is back on the call list`;
  toast.success(msg, undo ? { action: { label: "Undo", onClick: undo } } : undefined);
}
