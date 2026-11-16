"use client";

import { Globe2 } from "lucide-react";
import { ErrorState, SkeletonCard } from "@/components/ds";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/insights";
import type { EnrichmentStatus } from "@/lib/trail";
import { cn } from "@/lib/utils";
import { StateChip } from "./sources-view";

/** Bright Data row: public lookups used for LinkedIn profiles and web mentions, with the month's request count against the cap. */
export function BrightDataCard() {
  const [res, retry] = useLoad(api.enrichmentStatus);
  if (res.state === "loading") return <SkeletonCard />;
  if (res.state === "error") return <ErrorState title="Public lookup status could not be loaded" reason={res.reason} onRetry={retry} />;
  return <Card s={res.data} />;
}

function Card({ s }: { s: EnrichmentStatus }) {
  const state = !s.token_configured ? "off" : s.error ? "failed" : s.linkedin_enabled ? "on" : "off";
  const share = s.cap > 0 ? Math.min(100, Math.round((s.used / s.cap) * 100)) : 0;
  const reason = !s.token_configured
    ? "No Bright Data token is set on this server, so profile and web lookups are not offered."
    : s.error
      ? s.error
      : !s.linkedin_enabled
        ? "LinkedIn lookups are switched off (LINKEDIN_ENRICHMENT). Web mentions can still be fetched."
        : "";
  return (
    <section aria-labelledby="owner-brightdata" className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
      <header className="flex flex-col gap-3 border-b border-hairline px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id="owner-brightdata" className="flex items-center gap-2 text-base font-semibold">
            <Globe2 className="size-4 text-muted-foreground" aria-hidden />
            Public lookups (Bright Data)
          </h2>
          <p className="mt-0.5 max-w-[68ch] text-[13px] leading-relaxed text-muted-foreground">
            Looks up a person&apos;s public LinkedIn profile and recent web mentions, only when someone asks on the person page or in the chat. Never for funds or
            companies. A LinkedIn match is never called confirmed, and web results are leads, not facts.
          </p>
        </div>
        <StateChip state={state} className="shrink-0" />
      </header>
      <div className="space-y-3 px-5 py-4">
        {reason ? <p className="max-w-[72ch] text-[13px] leading-relaxed text-muted-foreground">{reason}</p> : null}
        <dl className="grid grid-cols-3 gap-x-5 text-left sm:max-w-md">
          <div>
            <dt className="text-[11px] text-faint">Used this month</dt>
            <dd className="tnum text-sm font-semibold text-foreground">{s.used.toLocaleString("en-IN")}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-faint">Monthly cap</dt>
            <dd className="tnum text-sm font-semibold text-foreground">{s.cap.toLocaleString("en-IN")}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-faint">Left</dt>
            <dd className={cn("tnum text-sm font-semibold", s.remaining <= 0 ? "text-negative" : "text-foreground")}>{s.remaining.toLocaleString("en-IN")}</dd>
          </div>
        </dl>
        <div
          role="progressbar"
          aria-label="Requests used this month"
          aria-valuemin={0}
          aria-valuemax={s.cap}
          aria-valuenow={Math.min(s.used, s.cap)}
          className="h-1.5 w-full max-w-md overflow-hidden rounded-full bg-secondary"
        >
          <div className={cn("h-full rounded-full", share >= 90 ? "bg-negative" : share >= 70 ? "bg-caution" : "bg-brand")} style={{ width: `${share}%` }} />
        </div>
        <p className="text-xs text-muted-foreground">
          LinkedIn lookups <span className="font-medium text-foreground">{s.linkedin_enabled ? "on" : "off"}</span>
          {s.month ? <span className="tnum"> · month {s.month}</span> : null}. Switch: <code className="rounded bg-secondary px-1 py-0.5 text-[12px] break-words text-foreground">LINKEDIN_ENRICHMENT=on|off</code>.
        </p>
      </div>
    </section>
  );
}
