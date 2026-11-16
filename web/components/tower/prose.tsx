"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Reveal streamed text at a steady reading pace. Sentences arrive whole (each is checked before it is sent),
 * so painting them in one jump feels jerky; this eases the visible length toward the received length,
 * faster when more is waiting, and shows everything at once for stored answers or reduced motion.
 */
export function useSmoothText(target: string, streaming: boolean): string {
  const [shown, setShown] = useState(streaming ? 0 : target.length);
  const shownRef = useRef(shown);
  const targetRef = useRef(target);
  const raf = useRef<number | null>(null);
  const last = useRef<number | null>(null);

  useEffect(() => {
    targetRef.current = target;
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || (!streaming && shownRef.current === 0)) {
      shownRef.current = target.length;
      setShown(target.length);
      return;
    }
    if (shownRef.current > target.length) {
      shownRef.current = target.length;
      setShown(target.length);
    }
    if (raf.current !== null) return;
    const tick = (now: number) => {
      const dt = last.current === null ? 16 : Math.min(64, now - last.current);
      last.current = now;
      const goal = targetRef.current.length;
      const backlog = goal - shownRef.current;
      if (backlog <= 0) {
        raf.current = null;
        last.current = null;
        return;
      }
      // ~70 chars/s at rest, clearing any backlog within ~0.6 s.
      const rate = Math.max(70, backlog / 0.6);
      const next = Math.min(goal, shownRef.current + Math.max(1, Math.round((rate * dt) / 1000)));
      shownRef.current = next;
      setShown(next);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
  }, [target, streaming]);

  useEffect(
    () => () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current);
    },
    [],
  );

  return target.slice(0, shown);
}

/** Split on `**` so a half-revealed "**Ash" already renders bold (no stray asterisks mid-stream). */
function inline(text: string) {
  const parts = text.split("**");
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <strong key={i} className="font-semibold">
        {part}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/** Short prose with **bold** and blank-line paragraphs. Digits arrive already checked by the API. */
export function Prose({ text, streaming = false, className }: { text: string; streaming?: boolean; className?: string }) {
  const visible = useSmoothText(text, streaming);
  const typing = streaming || visible.length < text.length;
  const paras = visible.split(/\n{2,}/);
  return (
    <div className={cn("space-y-3 text-[15px] leading-relaxed text-foreground", className)} aria-busy={typing || undefined}>
      {paras.map((p, i) => (
        <p key={i} className="max-w-[72ch] text-pretty">
          {inline(p)}
          {typing && i === paras.length - 1 ? <span className="stream-caret" aria-hidden /> : null}
        </p>
      ))}
    </div>
  );
}
