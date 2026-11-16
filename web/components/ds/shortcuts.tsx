"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useUi } from "@/lib/ui";

const ROWS: { keys: string[]; label: string }[] = [
  { keys: ["⌘", "K"], label: "Search people, or ask a question" },
  { keys: ["g", "t"], label: "Go to Today" },
  { keys: ["g", "e"], label: "Go to Events" },
  { keys: ["g", "h"], label: "Go to History" },
  { keys: ["b"], label: "Boardroom mode on or off" },
  { keys: ["?"], label: "Show this list" },
];
const GO: Record<string, string> = { t: "/today", e: "/events", h: "/history" };

function typing(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.getAttribute?.("role") === "textbox";
}

/** Keyboard shortcuts for the whole app, and the "?" overlay that lists them. Ignored while typing. */
export function Shortcuts() {
  const router = useRouter();
  const { toggleBoardroom, shortcutsOpen, setShortcutsOpen } = useUi();
  const pendingG = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const clear = () => {
      if (pendingG.current) clearTimeout(pendingG.current);
      pendingG.current = null;
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
      if (e.key === "?") {
        e.preventDefault();
        setShortcutsOpen(true);
        return;
      }
      if (pendingG.current) {
        const to = GO[e.key.toLowerCase()];
        clear();
        if (to) {
          e.preventDefault();
          router.push(to);
        }
        return;
      }
      const k = e.key.toLowerCase();
      if (k === "g") pendingG.current = setTimeout(clear, 1200);
      else if (k === "b") toggleBoardroom();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      clear();
    };
  }, [router, toggleBoardroom, setShortcutsOpen]);

  return (
    <Dialog open={shortcutsOpen} onOpenChange={setShortcutsOpen}>
      <DialogContent className="gap-5 p-6 sm:max-w-md">
        <div>
          <DialogTitle className="text-base font-semibold">Keyboard shortcuts</DialogTitle>
          <DialogDescription className="mt-1 text-[13px]">They work anywhere except while you are typing.</DialogDescription>
        </div>
        <dl className="divide-y divide-hairline">
          {ROWS.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-4 py-2.5">
              <dt className="text-[13.5px] text-foreground">{r.label}</dt>
              <dd className="flex items-center gap-1">
                {r.keys.map((k, i) => (
                  <span key={i} className="contents">
                    {i > 0 ? <span className="text-xs text-faint">then</span> : null}
                    <kbd className="min-w-6 rounded border bg-secondary px-1.5 py-0.5 text-center font-sans text-xs font-medium text-foreground">{k}</kbd>
                  </span>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
