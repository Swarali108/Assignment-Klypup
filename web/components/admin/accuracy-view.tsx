"use client";

import { useState } from "react";
import { ExternalLink, FileSearch, Loader2, RefreshCw, Target } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, SectionHeader, SkeletonCard, SkeletonList, StatCard, StatStrip } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { ApiError, resolveApiUrl } from "@/lib/api";
import { useLoad } from "@/lib/insights";
import { adminApi, istStamp, pct, type AccuracyResult } from "@/lib/admin";

/** "hd_fire_protect_limited_ipo_202610" → "Hd Fire Protect Limited" (type and month dropped, words capitalised). */
function companyOf(eventId: string): string {
  return eventId
    .replace(/_(ipo|buyback|ofs)(_\d+)?$/, "")
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** Plain words for the two internal shapes the checker prints: "buyback_price 500" and "unknown: no role printed". */
function missValue(v: string | number | null): string | number | null {
  if (typeof v !== "string") return v;
  const unknown = /^unknown:\s*(.+)$/i.exec(v);
  if (unknown) return `Unknown (${unknown[1]})`;
  const keyed = /^([a-z]+(?:_[a-z]+)+)\s+(.+)$/.exec(v);
  if (keyed) return `${keyed[1][0].toUpperCase()}${keyed[1].slice(1).replace(/_/g, " ")} ${keyed[2]}`;
  return v;
}

export function AccuracyView() {
  const [res, retry] = useLoad(adminApi.accuracy);
  const [fresh, setFresh] = useState<AccuracyResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function rerun() {
    setBusy(true);
    try {
      const r = await adminApi.runAccuracy();
      setFresh(r.result);
      toast.success("Scored again against the hand-read filings.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "The check could not run.");
    } finally {
      setBusy(false);
    }
  }

  if (res.state === "loading")
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <SkeletonList rows={4} />
      </div>
    );
  if (res.state === "error") return <ErrorState title="Accuracy could not load" reason={res.reason} onRetry={retry} />;
  const result = fresh ?? res.data.result;
  const button = (
    <Button variant={result ? "outline" : "default"} size="sm" onClick={() => void rerun()} disabled={busy}>
      {busy ? <Loader2 className="animate-spin" /> : <RefreshCw />} {result ? "Check again" : "Run the check"}
    </Button>
  );
  if (!result)
    return (
      <EmptyState icon={Target} title="The check has not run yet" tone="brand" action={button}>
        It compares the call lists with 20 people whose names, roles, shares, prices, amounts and dates were read by hand from the filings. It makes no model calls and costs nothing.
      </EmptyState>
    );
  return <Result result={result} button={button} />;
}

function rateTone(rate: number | null) {
  if (rate === null) return "bg-secondary";
  return rate >= 0.95 ? "bg-positive" : rate >= 0.8 ? "bg-brand" : rate >= 0.6 ? "bg-caution" : "bg-negative";
}

const OUTCOME: Record<string, { label: string; cls: string }> = {
  wrong: { label: "Wrong value", cls: "bg-negative-soft text-negative ring-negative/15" },
  missing: { label: "Not found", cls: "bg-caution-soft text-caution ring-caution/15" },
  invented: { label: "Invented", cls: "bg-negative-soft text-negative ring-negative/15" },
};

function Result({ result, button }: { result: AccuracyResult; button: React.ReactNode }) {
  const { overall } = result;
  const [event, setEvent] = useState<string | null>(null);
  const misses = result.misses.filter((m) => !event || m.event_id === event);
  return (
    <div className="space-y-8">
      <StatStrip>
        <StatCard icon={Target} label="Hit rate" value={pct(overall.hit_rate, 1)} muted={overall.hit_rate === null} sub={`${overall.hits} of ${overall.value_fields} values right`} />
        <StatCard label="People fully right" value={`${overall.fully_right} of ${overall.people}`} sub="Every field correct" />
        <StatCard label="Wrong or invented" value={String(overall.wrong + overall.invented)} sub={overall.wrong + overall.invented === 0 ? "Nothing shown that the filings do not say" : "Shown, but not what the filing says"} />
        <StatCard label="Not found" value={String(overall.missing)} sub="Printed in the filing, absent from the list" />
      </StatStrip>

      <section className="space-y-3">
        <SectionHeader title="Hit rate by field" description={`Scored ${istStamp(result.ran_at)}. A hit means the call list holds the value the filing prints.`} actions={button} />
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <ul className="divide-y divide-hairline">
            {result.fields.map((f) => (
              <li key={f.field} className="grid items-center gap-x-4 gap-y-1.5 px-5 py-3 sm:grid-cols-[10rem_minmax(0,1fr)_14rem]">
                <span className="text-sm font-medium text-foreground">{f.label}</span>
                <div className="h-2 overflow-hidden rounded-full bg-secondary" role="img" aria-label={`${pct(f.hit_rate)} hit rate`}>
                  <div className={cn("h-full rounded-full", rateTone(f.hit_rate))} style={{ width: `${(f.hit_rate ?? 0) * 100}%` }} />
                </div>
                <span className="tnum text-xs text-muted-foreground sm:text-right">
                  <span className="text-sm font-medium text-foreground">{pct(f.hit_rate)}</span> · {f.hit} of {f.value_fields}
                  {f.blank_ok + f.invented ? ` · ${f.blank_ok} blank right` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="space-y-3">
        <SectionHeader title="By event" description="Pick one to see only its misses." />
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setEvent(null)} className={cn("h-8 rounded-lg border px-3 text-[13px] font-medium", event === null ? "border-brand/50 bg-brand-soft text-brand-ink" : "bg-surface text-muted-foreground hover:text-foreground")}>
            All events
          </button>
          {result.events.map((e) => (
            <button
              key={e.event_id}
              type="button"
              onClick={() => setEvent(e.event_id === event ? null : e.event_id)}
              className={cn("h-8 rounded-lg border px-3 text-[13px] font-medium", event === e.event_id ? "border-brand/50 bg-brand-soft text-brand-ink" : "bg-surface text-muted-foreground hover:text-foreground")}
            >
              {companyOf(e.event_id)} <span className="tnum ml-1 text-xs">{pct(e.hit_rate)}</span>
            </button>
          ))}
        </div>
        {result.events_missing.length ? <p className="text-xs text-caution">Not run yet, so every field there counts as missing: {result.events_missing.join(", ")}</p> : null}
      </section>

      <section className="space-y-3">
        <SectionHeader title="Every miss" count={misses.length} description="Open the page to see what the filing prints." />
        {misses.length === 0 ? (
          <EmptyState icon={FileSearch} title="No misses" tone="brand">
            Every checked value in {event ? "this event" : "these events"} matches the filing.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
            {misses.map((m) => (
              <li key={`${m.person_id}-${m.field}`} className="grid gap-x-6 gap-y-2 px-5 py-3.5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_auto]">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">{m.name}</p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <span className={cn("inline-flex h-5 items-center rounded-md px-1.5 text-[11px] font-medium ring-1 ring-inset", OUTCOME[m.outcome]?.cls)}>{OUTCOME[m.outcome]?.label}</span>
                    {m.label}
                  </p>
                </div>
                <dl className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
                  <dt className="text-muted-foreground">Filing says</dt>
                  <dd className="break-words text-foreground">{missValue(m.gold) ?? "not printed"}</dd>
                  <dt className="text-muted-foreground">We hold</dt>
                  <dd className="break-words text-foreground">{missValue(m.pipeline) ?? "nothing"}</dd>
                </dl>
                <div className="flex flex-wrap items-start gap-1.5 md:justify-end">
                  {m.pages.length === 0 ? <span className="text-xs text-faint">No page recorded</span> : null}
                  {m.pages.map((p) => (
                    <Button key={p.url} asChild variant="outline" size="sm" title={p.quote ?? undefined}>
                      <a href={resolveApiUrl(p.url)} target="_blank" rel="noreferrer">
                        <ExternalLink /> {p.label}
                      </a>
                    </Button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
