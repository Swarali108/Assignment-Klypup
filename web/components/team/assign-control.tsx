"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, ChevronDown, Loader2, UserRound, UserRoundPlus } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { v3, type Assignment, type Rm } from "@/lib/v3";
import { useSession } from "@/lib/session";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

// One fetch is shared by every control on the page (a Today list has dozens of rows).
type Shared = { assignments: Record<string, Assignment>; rms: Rm[] };
let shared: { at: number; withRms: boolean; promise: Promise<Shared> } | null = null;
const listeners = new Set<() => void>();

// The RM list is only for people who can assign (a viewer or RM would get a 403), so it is only asked for then.
function loadShared(withRms: boolean, force = false): Promise<Shared> {
  if (!force && shared && shared.withRms === withRms && Date.now() - shared.at < 30_000) return shared.promise;
  const noRms = Promise.resolve({ rms: [] as Rm[] });
  const promise = Promise.all([v3.assignments(), withRms ? v3.rms().catch(() => ({ rms: [] as Rm[] })) : noRms]).then(([a, r]) => ({ assignments: a.assignments, rms: r.rms }));
  shared = { at: Date.now(), withRms, promise };
  promise.catch(() => {
    shared = null;
  });
  return promise;
}

/** Forget the shared fetch and tell every control on the page to read again. */
function invalidateShared() {
  shared = null;
  listeners.forEach((f) => f());
}

function useAssignments(ready: boolean, withRms: boolean) {
  const [data, setData] = useState<Shared | null>(null);
  const refresh = useCallback(
    (force = false) => {
      loadShared(withRms, force)
        .then(setData)
        .catch(() => setData(null));
    },
    [withRms],
  );
  useEffect(() => {
    if (!ready) return; // wait for the session, so the right requests are made the first time
    refresh();
    const again = () => refresh();
    listeners.add(again);
    return () => {
      listeners.delete(again);
    };
  }, [ready, refresh]);
  return { data, refresh };
}

/** Who a person is assigned to; the Head of RMs and admins can change it. Everyone else sees the name. */
export function AssignControl({ eventId, personId, compact = false, className }: { eventId: string; personId: string; compact?: boolean; className?: string }) {
  const { can, loading } = useSession();
  const { data } = useAssignments(!loading, can("team"));
  const [busy, setBusy] = useState(false);
  if (!data) return null;
  const current = data.assignments[`${eventId}/${personId}`];
  const name = current?.rm_name;

  if (!can("team"))
    return current ? (
      <span className={cn("inline-flex items-center gap-1.5 text-xs text-muted-foreground", className)}>
        <UserRound className="size-3.5" aria-hidden /> Assigned to <span className="font-medium text-foreground">{name}</span>
      </span>
    ) : null;

  const set = async (email: string | null) => {
    setBusy(true);
    try {
      await v3.assign(eventId, personId, email);
      invalidateShared();
      toast.success(email ? `Assigned to ${data.rms.find((r) => r.email === email)?.name ?? email}` : "Assignment cleared");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not assign.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          disabled={busy}
          aria-label={name ? `Assigned to ${name}. Change assignment` : "Assign to an RM"}
          className={cn(
            "relative z-10 inline-flex items-center gap-1.5 rounded-md border bg-surface text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-60",
            compact ? "h-6 px-2" : "h-8 px-2.5 text-[13px]",
            name && "text-foreground",
            className,
          )}
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : name ? <UserRound className="size-3.5 text-brand" /> : <UserRoundPlus className="size-3.5" />}
          {name ?? "Assign"}
          <ChevronDown className="size-3 text-faint" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Assign to</DropdownMenuLabel>
        {data.rms.length === 0 ? <p className="px-2 py-2 text-xs text-muted-foreground">No RMs to assign to yet.</p> : null}
        {data.rms.map((r) => (
          <DropdownMenuItem key={r.email} onSelect={() => void set(r.email)}>
            <span className="min-w-0 flex-1 truncate">{r.name}</span>
            {current?.rm_email === r.email ? <Check className="text-brand" /> : null}
          </DropdownMenuItem>
        ))}
        {current ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void set(null)}>Clear assignment</DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
