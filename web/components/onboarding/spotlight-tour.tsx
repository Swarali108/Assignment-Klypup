"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, Coins, FileText, Play } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/lib/prefs";
import { Button } from "@/components/ui/button";

type Stop = { targets: string[]; title: string; body: string; specimen?: "evidence" | "confirm" };

const STOPS: Stop[] = [
  { targets: ["prompt"], title: "Ask in plain words", body: "Type a name, a company or an amount. Lookups cost nothing and answer at once, with every step shown." },
  { targets: ["nav-today", "menu"], title: "Today is your call list", body: "Everyone worth a call, ranked by cash in hand, with the reason and the timing on each row. On a phone it sits in this menu." },
  {
    targets: ["evidence", "evidence-amount"],
    title: "Every ₹ has a source",
    body: "Click an evidence chip to open the filing page, with the exact line highlighted. No link, no number.",
    specimen: "evidence",
  },
  {
    targets: ["confirm", "prompt"],
    title: "Nothing paid runs without you",
    body: "Processing a new filing or a deep dive shows an itemised estimate first. It runs only when you press Confirm.",
    specimen: "confirm",
  },
];

type Rect = { top: number; left: number; width: number; height: number };

function findTarget(names: string[]): HTMLElement | null {
  for (const name of names) {
    const all = Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`));
    const visible = all.find((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
    });
    if (visible) return visible;
    const any = all.find((el) => el.getBoundingClientRect().width > 0);
    if (any) return any;
  }
  return null;
}

/** Small static specimens so stops 3 and 4 always have something real-looking to point at. */
function Specimen({ kind }: { kind: "evidence" | "confirm" }) {
  if (kind === "evidence") {
    return (
      <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border bg-surface-sunken/60 px-3 py-2.5" aria-hidden>
        <span className="tnum text-sm font-semibold text-foreground">≈ ₹110.73 Cr</span>
        <span className="inline-flex h-6 items-center gap-1.5 rounded-md border border-brand/40 bg-brand-soft px-2 text-xs font-medium text-brand-ink">
          <FileText className="size-3.5" /> Prospectus · <span className="tnum">p. 18</span>
        </span>
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-lg border bg-surface-sunken/60 px-3 py-2.5 text-xs" aria-hidden>
      <div className="flex items-center gap-2 text-foreground">
        <Coins className="size-3.5 text-caution" />
        <span className="font-medium">Process a new filing</span>
        <span className="tnum ml-auto font-semibold">$0.012–$0.034</span>
      </div>
      <div className="mt-2 flex justify-end gap-1.5">
        <span className="rounded-md px-2 py-1 text-muted-foreground">Cancel</span>
        <span className="inline-flex items-center gap-1 rounded-md bg-brand px-2 py-1 font-medium text-brand-foreground">
          <Play className="size-3" /> Confirm & run
        </span>
      </div>
    </div>
  );
}

/** A 4-stop spotlight over the live page. Missing targets (e.g. the rail inside a closed sheet) fall back to a centred card. */
export function SpotlightTour() {
  const { tourOpen, endTour } = usePrefs();
  const pathname = usePathname();
  const router = useRouter();
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const [vw, setVw] = useState(1440);
  const [vh, setVh] = useState(900);
  const card = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const stop = STOPS[i];

  useEffect(() => {
    if (tourOpen && pathname !== "/") router.push("/");
  }, [tourOpen, pathname, router]);

  const measure = useCallback(() => {
    setVw(window.innerWidth);
    setVh(window.innerHeight);
    const el = findTarget(stop.targets);
    if (!el) return setRect(null);
    const r = el.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight) {
      el.scrollIntoView({ block: "center", behavior: "instant" as ScrollBehavior });
    }
    const r2 = el.getBoundingClientRect();
    const pad = 8;
    setRect({ top: r2.top - pad, left: r2.left - pad, width: r2.width + pad * 2, height: r2.height + pad * 2 });
  }, [stop]);

  useLayoutEffect(() => {
    if (!tourOpen) return;
    const t = setTimeout(measure, 60);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [tourOpen, measure, pathname]);

  useEffect(() => {
    if (!tourOpen) return;
    next.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") setI((x) => Math.min(x + 1, STOPS.length - 1));
      if (e.key === "ArrowLeft") setI((x) => Math.max(x - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tourOpen, i]);

  function close() {
    endTour();
    setI(0);
  }

  if (!tourOpen) return null;

  // Card placement: under the target if there is room, else above; centred when there is no target.
  const W = Math.min(352, vw - 32);
  const mobile = vw < 640;
  let style: React.CSSProperties;
  if (!rect) style = { top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: W };
  else if (mobile) style = { left: 16, right: 16, ...(rect.top + rect.height / 2 > vh / 2 ? { top: Math.max(16, rect.top - 16 - 260) } : { top: Math.min(vh - 276, rect.top + rect.height + 14) }) };
  else {
    const below = rect.top + rect.height + 14;
    const fitsBelow = below + 250 < vh;
    const left = Math.min(Math.max(16, rect.left + rect.width / 2 - W / 2), vw - W - 16);
    const sideRight = rect.width < 320 && rect.left + rect.width + W + 28 < vw;
    style = sideRight
      ? { top: Math.max(16, Math.min(rect.top, vh - 280)), left: rect.left + rect.width + 16, width: W }
      : fitsBelow
        ? { top: below, left, width: W }
        : { top: Math.max(16, rect.top - 14 - 260), left, width: W };
  }

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {rect ? (
        <div
          aria-hidden
          className="pointer-events-none absolute rounded-2xl ring-2 ring-brand/70 transition-all duration-300 ease-(--ease-out-expo) motion-reduce:transition-none"
          style={{ ...rect, boxShadow: "0 0 0 200vmax oklch(0.2 0.02 255 / 0.5)" }}
        />
      ) : (
        <div aria-hidden className="absolute inset-0 bg-[oklch(0.2_0.02_255/0.5)]" />
      )}
      <div className="absolute inset-0" onClick={close} aria-hidden />
      <div
        ref={card}
        className="absolute rounded-2xl border bg-popover p-5 shadow-(--shadow-raised) transition-[top,left] duration-300 ease-(--ease-out-expo) motion-reduce:transition-none"
        style={style}
      >
        <div className="flex items-center gap-1.5" aria-hidden>
          {STOPS.map((_, j) => (
            <span key={j} className={cn("h-1 rounded-full transition-all duration-300", j === i ? "w-5 bg-brand" : "w-1.5 bg-border")} />
          ))}
          <span className="tnum ml-auto text-xs text-muted-foreground">
            {i + 1} / {STOPS.length}
          </span>
        </div>
        <h2 id="tour-title" className="mt-3 text-base font-semibold text-foreground">
          {stop.title}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{stop.body}</p>
        {stop.specimen ? <Specimen kind={stop.specimen} /> : null}
        <div className="mt-4 flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={close} className="-ml-2 text-muted-foreground">
            End tour
          </Button>
          <div className="ml-auto flex gap-1.5">
            {i > 0 ? (
              <Button variant="outline" size="sm" onClick={() => setI(i - 1)} aria-label="Previous stop">
                <ArrowLeft />
              </Button>
            ) : null}
            <Button
              ref={next}
              size="sm"
              onClick={() => (i === STOPS.length - 1 ? close() : setI(i + 1))}
              className="bg-brand text-brand-foreground hover:bg-brand/90"
            >
              {i === STOPS.length - 1 ? (
                <>
                  <Check /> Done
                </>
              ) : (
                <>
                  Next <ArrowRight />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
