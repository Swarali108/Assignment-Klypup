"use client";

import { useEffect, useState } from "react";
import { Bell, BellRing, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { v3 } from "@/lib/v3";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";

/** Follow / unfollow a person or a company. Alerts for what you follow appear in the bell. */
export function FollowButton({ kind, eventId, personId, label }: { kind: "person" | "company"; eventId: string; personId?: string; label?: string }) {
  const [state, setState] = useState<{ following: boolean; key: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    apiFetch<{ following: boolean; key: string }>("/watch/status", { query: { kind, event_id: eventId, person_id: personId } })
      .then((r) => live && setState({ following: r.following, key: r.key }))
      .catch(() => live && setState(null));
    return () => {
      live = false;
    };
  }, [kind, eventId, personId]);

  if (!state) return null; // not loaded, or not allowed: no half-working button
  const toggle = async () => {
    setBusy(true);
    try {
      if (state.following) {
        await v3.unfollow(kind, state.key);
        setState({ ...state, following: false });
        toast.success("Stopped following");
      } else {
        const r = await v3.follow(kind, eventId, personId);
        setState({ following: true, key: r.key });
        window.dispatchEvent(new Event("finsight:alerts-refresh"));
        toast.success(`Following ${r.label}. New events, lock-ins and amount changes will show in the bell.`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update.");
    } finally {
      setBusy(false);
    }
  };
  const words = label ?? (kind === "person" ? "Follow" : "Follow company");
  return (
    <Button variant={state.following ? "secondary" : "outline"} size="sm" onClick={toggle} disabled={busy} aria-pressed={state.following}>
      {busy ? <Loader2 className="animate-spin" /> : state.following ? <BellRing className="text-brand" /> : <Bell />}
      {state.following ? "Following" : words}
    </Button>
  );
}
