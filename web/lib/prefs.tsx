"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { EVENT_TYPE_LABEL } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { CallItem } from "@/lib/types";

export type Alerts = "daily" | "weekly" | "off";
export type Preferences = {
  onboarded: boolean;
  event_types: string[];
  min_ticket_cr: number | null;
  alerts: Alerts;
  book_count: number;
};

export const prefsApi = {
  get: () => apiFetch<Preferences>("/me/preferences"),
  save: (patch: Partial<Omit<Preferences, "book_count">>) =>
    apiFetch<Preferences>("/me/preferences", { method: "PUT", body: JSON.stringify(patch) }),
  saveBook: (names: string[]) => apiFetch<{ book_count: number }>("/me/book", { method: "POST", body: JSON.stringify({ names }) }),
  clearBook: () => apiFetch<{ book_count: number }>("/me/book", { method: "DELETE" }),
};

type Ctx = {
  prefs: Preferences | null;
  setPrefs: (p: Preferences) => void;
  guideOpen: boolean;
  openGuide: () => void;
  closeGuide: () => void;
  /** The 4-stop spotlight tour (runs after the guide, or on its own). */
  tourOpen: boolean;
  startTour: () => void;
  endTour: () => void;
};
const PrefsCtx = createContext<Ctx | null>(null);

/** Loads the RM's preferences once signed in, and opens the setup guide on a first sign-in. */
export function PrefsProvider({ children }: { children: React.ReactNode }) {
  const { user } = useSession();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const email = user?.email;

  useEffect(() => {
    if (!email) return;
    let live = true;
    prefsApi
      .get()
      .then((p) => {
        if (!live) return;
        setPrefs(p);
        if (!p.onboarded) setGuideOpen(true);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [email]);

  const openGuide = useCallback(() => setGuideOpen(true), []);
  const closeGuide = useCallback(() => setGuideOpen(false), []);
  const startTour = useCallback(() => setTourOpen(true), []);
  const endTour = useCallback(() => setTourOpen(false), []);
  const value = useMemo(
    () => ({ prefs, setPrefs, guideOpen, openGuide, closeGuide, tourOpen, startTour, endTour }),
    [prefs, guideOpen, openGuide, closeGuide, tourOpen, startTour, endTour],
  );
  return <PrefsCtx.Provider value={value}>{children}</PrefsCtx.Provider>;
}

export function usePrefs() {
  const c = useContext(PrefsCtx);
  if (!c) throw new Error("usePrefs must be used inside <PrefsProvider>");
  return c;
}

/** True when a call item fits the RM's coverage (event types + minimum ticket). No preferences: everything fits. */
export function fitsCoverage(item: CallItem, prefs: Preferences | null): boolean {
  if (!prefs) return true;
  // A Today slot that folds a holder's repeat sales fits when any of its trades does (same test as api/brief.py).
  const kinds = [item.event.type, ...(item.trades ?? []).map((t) => t.event.type)];
  if (prefs.event_types.length && !kinds.some((k) => prefs.event_types.includes(k))) return false;
  if (prefs.min_ticket_cr && Math.max(item.amount.value_cr ?? 0, item.trades_total_cr ?? 0) < prefs.min_ticket_cr) return false;
  return true;
}

/** "IPO, Buyback · ₹50 Cr and up": the coverage in words. */
export function coverageWords(types: string[], min: number | null) {
  const t = types.map((x) => EVENT_TYPE_LABEL[x] ?? (x.startsWith("ofs") ? "Offers for sale" : x)).join(", ");
  return [t || null, min ? `₹${min} Cr and up` : null].filter(Boolean).join(" · ");
}

/**
 * Names from a CSV a person exported from their CRM: the column headed name / client / client name
 * when there is one, else the first column. Quotes and a byte-order mark are handled; blank rows dropped.
 */
export function namesFromCsv(text: string): string[] {
  const rows = text
    .replace(/^﻿/, "")
    .split(/\r?\n/)
    .map((line) => {
      const cells: string[] = [];
      let cur = "";
      let quoted = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (quoted) {
          if (ch === '"' && line[i + 1] === '"') {
            cur += '"';
            i++;
          } else if (ch === '"') quoted = false;
          else cur += ch;
        } else if (ch === '"') quoted = true;
        else if (ch === "," || ch === ";" || ch === "\t") {
          cells.push(cur.trim());
          cur = "";
        } else cur += ch;
      }
      cells.push(cur.trim());
      return cells;
    })
    .filter((cells) => cells.some((c) => c));
  if (!rows.length) return [];
  const header = rows[0].map((h) => h.toLowerCase());
  let col = header.findIndex((h) => /^(client\s*)?name$|^client$|^full\s*name$/.test(h));
  const hasHeader = col !== -1 || header.some((h) => /name|client|email|phone|city/.test(h));
  if (col === -1) col = 0;
  return (hasHeader ? rows.slice(1) : rows).map((r) => r[col] ?? "").filter((n) => n && /[a-z]/i.test(n));
}
