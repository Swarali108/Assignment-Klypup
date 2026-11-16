"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { briefApi, type Brief } from "@/lib/brief";
import { localDay } from "@/lib/market";
import { usePrefs } from "@/lib/prefs";
import { useSession } from "@/lib/session";
import { BriefSheet } from "./brief-sheet";

type Ctx = {
  brief: Brief | null;
  open: boolean;
  loading: boolean;
  failed: boolean;
  /** Show the brief (loads it first when needed). */
  openBrief: () => void;
  closeBrief: () => void;
  /** Admin only: write today's brief again. */
  rewrite: () => void;
};
const BriefCtx = createContext<Ctx | null>(null);

/**
 * Loads today's brief once a user is signed in. On the first sign-in of the local day (the server remembers
 * "shown" per user and date) the sheet opens by itself; after that it opens from home or the user menu.
 */
export function BriefProvider({ children }: { children: React.ReactNode }) {
  const { user } = useSession();
  const { prefs } = usePrefs();
  const pathname = usePathname();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const autoDone = useRef(false);
  const email = user?.email;
  const quiet = pathname.startsWith("/login") || /\/print\/?$/.test(pathname) || pathname.startsWith("/weekly");

  const load = useCallback(async (refresh = false): Promise<Brief | null> => {
    setLoading(true);
    try {
      const b = await briefApi.get(localDay(), refresh);
      setBrief(b);
      setFailed(false);
      return b;
    } catch {
      setFailed(true);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Once per page load and user: fetch, and open when this is the day's first sign-in. A user who still has the
  // setup guide to do is not interrupted (the brief waits for the next day's first sign-in).
  useEffect(() => {
    if (!email || quiet || !prefs || autoDone.current) return;
    autoDone.current = true;
    void load().then((b) => {
      if (!b || b.shown || !prefs.onboarded) return;
      setOpen(true);
      void briefApi.shown(b.day).catch(() => {});
    });
  }, [email, quiet, prefs, load]);

  const openBrief = useCallback(() => {
    setOpen(true);
    if (!brief) void load();
  }, [brief, load]);
  const closeBrief = useCallback(() => setOpen(false), []);
  const rewrite = useCallback(() => void load(true), [load]);

  const value = useMemo(
    () => ({ brief, open, loading, failed, openBrief, closeBrief, rewrite }),
    [brief, open, loading, failed, openBrief, closeBrief, rewrite],
  );
  return (
    <BriefCtx.Provider value={value}>
      {children}
      {email && !quiet ? <BriefSheet /> : null}
    </BriefCtx.Provider>
  );
}

export function useBrief() {
  const c = useContext(BriefCtx);
  if (!c) throw new Error("useBrief must be used inside <BriefProvider>");
  return c;
}
