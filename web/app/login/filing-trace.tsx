"use client";

import { useEffect, useState } from "react";
import { FileText, KeyRound } from "lucide-react";
import { cn } from "@/lib/utils";
import specimen from "@/lib/login-specimen.json";

/** Count up to the figure once (after the highlight lands). Reduced motion: the final figure at once. */
function useCountUp(target: number, delayMs: number, durationMs: number) {
  const [value, setValue] = useState(target);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const start = performance.now() + delayMs;
    const tick = (now: number) => {
      const t = Math.min(1, Math.max(0, (now - start) / durationMs));
      const eased = 1 - Math.pow(1 - t, 4);
      setValue(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, delayMs, durationMs]);
  return value;
}

const cr = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * The login's one authored moment: a real holdings table from a filing, one line highlighted, and the
 * call-card figure that line becomes lifting off the page. Every value is copied from a stored output.
 */
export function FilingTrace({ compact = false }: { compact?: boolean }) {
  const s = specimen;
  const amount = useCountUp(s.amount_cr, 1950, 900);
  const hi = s.rows[s.highlight_row];

  if (compact) {
    return (
      <div className="trace-page relative overflow-hidden rounded-xl border bg-surface px-4 py-3.5 shadow-(--shadow-card)">
        <p className="text-[11px] text-muted-foreground">
          {s.doc} · p. {s.page}
        </p>
        <p className="tnum relative mt-1.5 inline-block text-[13px] text-foreground">
          <span aria-hidden className="trace-sweep absolute -inset-x-1 -inset-y-0.5 -z-0 rounded-[3px] bg-highlight/70" />
          <span className="relative">
            {hi[0]} {hi[1]} {hi[2]} {hi[3]}
          </span>
        </p>
        <div className="trace-rise mt-3 flex items-end justify-between gap-3 border-t border-hairline pt-3">
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-foreground">{s.person}</p>
            <p className="tnum truncate text-[11px] text-muted-foreground">{s.working}</p>
          </div>
          <p className="tnum shrink-0 text-lg font-semibold tracking-[-0.01em] text-foreground">
            <span className="text-faint">≈ </span>₹{cr(amount)} Cr
          </p>
        </div>
      </div>
    );
  }

  return (
    <figure className="relative w-full max-w-[30rem]" aria-label={`${s.person}: ${s.figure_label} ₹${cr(s.amount_cr)} crore, from ${s.doc} page ${s.page}`}>
      {/* The page */}
      <div className="trace-page relative rounded-[6px] border bg-surface px-6 pt-5 pb-16 shadow-(--shadow-card)">
        <div className="flex items-baseline justify-between border-b border-hairline pb-2.5 text-[11px] text-muted-foreground">
          <span>{s.doc}</span>
          <span className="tnum">p. {s.page}</span>
        </div>
        <p className="mt-3.5 text-[11px] leading-snug font-medium text-foreground/70">{s.table_title}</p>
        <table className="tnum mt-2.5 w-full text-[12px] leading-[1.9]">
          <thead>
            <tr className="border-b border-hairline text-left text-[10.5px] text-faint">
              <th className="w-7 font-normal">{s.columns[0]}</th>
              <th className="font-normal">{s.columns[1]}</th>
              <th className="w-[6.5rem] text-right font-normal">{s.columns[2]}</th>
              <th className="w-[4.5rem] text-right font-normal">{s.columns[3]}</th>
            </tr>
          </thead>
          <tbody>
            {s.rows.slice(0, s.highlight_row + 1).map((r, i) => {
              const on = i === s.highlight_row;
              return (
                <tr key={r[0]} className={cn(!on && "trace-dim", "text-foreground/90")}>
                  <td className="text-faint">{r[0]}</td>
                  <td className="relative">
                    {on ? <span aria-hidden className="trace-sweep absolute top-[3px] bottom-[3px] -left-1.5 w-[calc(100%+11rem+0.375rem)] rounded-[3px] bg-highlight/75" /> : null}
                    <span className="relative">{r[1]}</span>
                  </td>
                  <td className="relative text-right">
                    <span className={cn("relative", on && "font-semibold text-foreground")}>{r[2]}</span>
                  </td>
                  <td className="relative text-right">
                    <span className="relative">{r[3]}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* The thread from the line to the figure */}
      <span aria-hidden className="trace-drop absolute right-[7.4rem] w-px bg-brand" style={{ top: "9.95rem", height: "2.85rem" }} />
      <span aria-hidden className="trace-drop absolute right-[7.4rem] size-[7px] translate-x-[3px] -translate-y-[3px] rounded-full bg-brand" style={{ top: "9.95rem" }} />

      {/* The call card it becomes */}
      <div className="trace-rise relative -mt-10 ml-auto w-[88%] rounded-2xl border bg-surface p-5 shadow-(--shadow-raised)">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-brand-ink">MS</span>
            <div className="min-w-0">
              <p className="truncate text-[15px] font-semibold text-foreground">{s.person}</p>
              <p className="truncate text-xs text-muted-foreground">
                {s.role} · {s.event}
              </p>
            </div>
          </div>
          <span className="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-md bg-caution-soft px-2 text-xs font-medium whitespace-nowrap text-caution ring-1 ring-caution/15 ring-inset">
            <KeyRound className="size-3.5" aria-hidden /> {s.tier}
          </span>
        </div>
        <div className="mt-4 flex items-end justify-between gap-4 border-t border-hairline pt-4">
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{s.figure_label}</p>
            <p className="tnum mt-1 text-[11.5px] text-muted-foreground">{s.working}</p>
          </div>
          <p className="tnum text-[1.75rem] leading-none font-semibold tracking-[-0.02em] text-foreground">
            <span className="text-faint">≈ </span>₹{cr(amount)}
            <span className="ml-1 text-base font-medium text-muted-foreground">Cr</span>
          </p>
        </div>
        <div className="trace-fade mt-3.5 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-flex h-6 items-center gap-1.5 rounded-md border border-brand/35 bg-brand-soft px-2 font-medium text-brand-ink">
            <FileText className="size-3.5" aria-hidden />
            Prospectus · <span className="tnum">p. {s.page}</span>
          </span>
          the line this figure came from
        </div>
      </div>
    </figure>
  );
}
