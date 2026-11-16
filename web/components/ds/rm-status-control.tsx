"use client";

import { useState } from "react";
import { CalendarClock, Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { RmState, RmStatus } from "@/lib/types";

export const RM_STATUS: { value: RmStatus; label: string }[] = [
  { value: "to_call", label: "To call" },
  { value: "called", label: "Called" },
  { value: "follow_up", label: "Follow up" },
  { value: "meeting_booked", label: "Meeting booked" },
  { value: "won", label: "Won" },
  { value: "not_now", label: "Not now" },
  { value: "not_a_fit", label: "Not a fit" },
];

export const RM_STATUS_LABEL = Object.fromEntries(RM_STATUS.map((s) => [s.value, s.label])) as Record<RmStatus, string>;

/**
 * Status + note + follow-up date for one person. Saves through `onSave` if given, otherwise PUTs
 * /api/rm/{eventId}/{personId}. Status buttons save immediately; the note saves on "Save note".
 */
export function RmStatusControl({
  eventId,
  personId,
  initial,
  onSave,
  className,
}: {
  eventId: string;
  personId: string;
  initial: RmState;
  onSave?: (next: RmState) => Promise<RmState | void> | RmState | void;
  className?: string;
}) {
  const [state, setState] = useState<RmState>(initial);
  const [note, setNote] = useState(initial.note ?? "");
  const [saving, setSaving] = useState<"status" | "note" | null>(null);
  // A deal can only be marked won with the amount the RM entered (crore); the amount is never worked out.
  const [wonAmount, setWonAmount] = useState(initial.won_amount_cr != null ? String(initial.won_amount_cr) : "");
  const [askWon, setAskWon] = useState(false);
  const [askDate, setAskDate] = useState(false);

  const save = async (patch: Partial<RmState>, what: "status" | "note") => {
    const next = { ...state, ...patch };
    setSaving(what);
    try {
      const amount = Number(wonAmount);
      const body = {
        status: next.status,
        note: next.note,
        follow_up_date: next.follow_up_date ?? "",
        ...(next.status === "won" && wonAmount.trim() !== "" && Number.isFinite(amount) ? { won_amount_cr: amount } : {}),
      };
      const res = onSave ? await onSave(next) : await api.saveRm(eventId, personId, body);
      setState(res ?? next);
      setAskWon(false);
      toast.success(what === "note" ? "Note saved" : `Marked “${RM_STATUS_LABEL[next.status]}”`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save. Try again.");
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className={cn("space-y-5", className)}>
      <div>
        <Label className="mb-2 block text-xs text-muted-foreground">Status</Label>
        <div role="radiogroup" aria-label="Call status" className="flex flex-wrap gap-1.5">
          {RM_STATUS.map((s) => {
            const on = state.status === s.value;
            return (
              <button
                key={s.value}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={saving !== null}
                onClick={() => {
                  if (on) return;
                  if (s.value === "won") setAskWon(true);
                  else if (s.value === "follow_up" && !state.follow_up_date) {
                    // a follow-up needs a date or it never comes back as a reminder: ask for it instead of saving
                    setAskDate(true);
                    document.getElementById(`fu-${personId}`)?.focus();
                  } else save({ status: s.value }, "status");
                }}
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium transition-colors disabled:opacity-60",
                  on ? "border-primary bg-primary text-primary-foreground" : "bg-surface text-foreground hover:bg-accent",
                )}
              >
                {on ? <Check className="size-3.5" /> : null}
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      {askWon || state.status === "won" ? (
        <div className="rounded-lg border bg-brand-soft/50 p-3">
          <Label htmlFor={`won-${personId}`} className="mb-2 block text-xs text-muted-foreground">
            New money in, as you entered it (₹ Cr)
          </Label>
          <div className="flex items-center gap-2">
            <Input
              id={`won-${personId}`}
              type="number"
              inputMode="decimal"
              min={0}
              step="0.01"
              value={wonAmount}
              onChange={(e) => setWonAmount(e.target.value)}
              placeholder="e.g. 2.5"
              className="tnum w-36 bg-surface"
            />
            <Button
              size="sm"
              disabled={saving !== null || wonAmount.trim() === "" || !(Number(wonAmount) >= 0)}
              onClick={() => save({ status: "won" }, "status")}
            >
              {saving === "status" ? <Loader2 className="animate-spin" /> : null}
              {state.status === "won" ? "Update amount" : "Mark as won"}
            </Button>
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_12rem]">
        <div>
          <Label htmlFor={`note-${personId}`} className="mb-2 block text-xs text-muted-foreground">
            Note
          </Label>
          <Textarea
            id={`note-${personId}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What was discussed, what they asked for, next step"
            className="min-h-24 bg-surface"
          />
        </div>
        <div>
          <Label htmlFor={`fu-${personId}`} className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <CalendarClock className="size-3.5" /> Follow-up date
          </Label>
          <Input
            id={`fu-${personId}`}
            type="date"
            value={state.follow_up_date ?? ""}
            aria-invalid={askDate && !state.follow_up_date ? true : undefined}
            onChange={(e) => {
              setAskDate(false);
              save({ follow_up_date: e.target.value || null, status: e.target.value ? "follow_up" : state.status }, "status");
            }}
            className={cn("tnum bg-surface", askDate && !state.follow_up_date && "border-brand ring-2 ring-ring")}
          />
          {askDate && !state.follow_up_date ? (
            <p className="mt-1.5 text-xs text-brand-ink" role="status">
              Pick a date to set the follow-up.
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-muted-foreground">
          {state.updated_at ? `Last updated ${new Date(state.updated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}` : "Not updated yet"}
        </span>
        <Button size="sm" onClick={() => save({ note }, "note")} disabled={saving !== null || note === (state.note ?? "")}>
          {saving === "note" ? <Loader2 className="animate-spin" /> : null}
          Save note
        </Button>
      </div>
    </div>
  );
}
