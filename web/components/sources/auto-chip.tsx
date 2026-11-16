"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSession } from "@/lib/session";
import { CHECK_FINISHED, sourcesApi, usd, type AutoLog } from "./api";

/**
 * "Auto-processed today: $0.012 of $1.00": today's automatic spend against the daily cap, for admins.
 * Links to the log on the Sources page. Renders nothing for other roles or when the log cannot load.
 */
export function AutoChip({ className, refreshKey = 0 }: { className?: string; refreshKey?: number }) {
  const { can } = useSession();
  const allowed = can("ops");
  const [data, setData] = useState<AutoLog["today"] | null>(null);
  const [round, setRound] = useState(0);
  useEffect(() => {
    const bump = () => setRound((n) => n + 1);
    window.addEventListener(CHECK_FINISHED, bump);
    return () => window.removeEventListener(CHECK_FINISHED, bump);
  }, []);
  useEffect(() => {
    if (!allowed) return;
    let live = true;
    sourcesApi
      .autoLog()
      .then((log) => live && setData(log.today))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [allowed, refreshKey, round]);
  if (!allowed || !data) return null;
  const share = data.cap_usd > 0 ? Math.min(1, data.spent_usd / data.cap_usd) : 1;
  const full = data.cap_usd <= 0 || data.spent_usd >= data.cap_usd;
  return (
    <Link
      href="/sources#auto-log"
      className={cn(
        "group inline-flex h-9 items-center gap-2.5 rounded-lg border bg-surface px-3 text-[13px] text-muted-foreground shadow-(--shadow-card) transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        className,
      )}
      aria-label={`Auto-processed today: ${usd(data.spent_usd)} of ${usd(data.cap_usd)}. Open the auto-processing log.`}
    >
      <Bot className="size-4 text-brand" aria-hidden />
      <span>
        Auto-processed today: <span className="tnum font-semibold text-foreground">{usd(data.spent_usd)}</span> of{" "}
        <span className="tnum">{usd(data.cap_usd)}</span>
      </span>
      <span className="relative h-1.5 w-12 overflow-hidden rounded-full bg-secondary" aria-hidden>
        <span
          className={cn("absolute inset-y-0 left-0 rounded-full", full ? "bg-caution" : "bg-brand")}
          style={{ width: `${Math.max(share * 100, data.spent_usd > 0 ? 6 : 0)}%` }}
        />
      </span>
    </Link>
  );
}
