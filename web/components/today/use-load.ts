"use client";

import { useCallback, useEffect, useState } from "react";

export type Load<T> = { state: "loading" } | { state: "error"; reason: string } | { state: "ready"; data: T };

/** Client-side fetch with loading / error / retry. `deps` re-run the loader. */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [load, setLoad] = useState<Load<T>>({ state: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    loader()
      .then((data) => !cancelled && setLoad({ state: "ready", data }))
      .catch((e: unknown) => !cancelled && setLoad({ state: "error", reason: e instanceof Error ? e.message : "Could not load." }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);
  const retry = useCallback(() => {
    setLoad({ state: "loading" });
    setTick((t) => t + 1);
  }, []);
  return { load, retry, setLoad };
}

/** Rewords the few stored phrases that use internal words, so screens read in RM language. */
export function rmText(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/Holder type unsure: no entity marker and \d+ words/gi, "Holder type unsure")
    .replace(/No entity marker and \d+ words/gi, "Reads as a person's name")
    .replace(/Holder type unsure/gi, "Not sure if this is a person or an organisation")
    .replace(/\bis not extracted\b/gi, "is not known yet")
    .replace(/\bnot extracted\b/gi, "not known yet")
    .replace(/\bextracted\b/gi, "read")
    .replace(/\bLLM\b/g, "assistant")
    .replace(/\bpipeline\b/gi, "process");
}

/** Confidence with RM-worded reasons (for badges and tooltips). */
export function rmConfidence<T extends { reason: string; reasons?: string[] }>(c: T): T {
  const uniq = (xs: string[]) => [...new Set(xs.map(rmText).filter(Boolean))];
  return { ...c, reason: uniq(c.reason.split(/;\s*/)).join("; "), reasons: c.reasons ? uniq(c.reasons) : undefined };
}

/** Timing with an RM-worded label. */
export function rmTiming<T extends { label: string }>(t: T): T {
  return { ...t, label: rmText(t.label) };
}

/** True when a sentence only restates the amount ("₹468.85 crore"), so it adds nothing under the figure. */
export function isBareAmount(s: string | null | undefined): boolean {
  return !!s && /^₹[\d,.]+ crore$/.test(s.trim());
}
