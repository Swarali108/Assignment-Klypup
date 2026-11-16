"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, GraduationCap, Globe, Loader2, MapPin, RefreshCw, Search, Briefcase, ShieldAlert, UserSearch } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import { ErrorState, SectionHeader, SkeletonCard } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { EnrichKind, LinkedInCandidate, PersonEnrichment } from "@/lib/trail";

const POLL_MS = 4000;

function Match({ level }: { level: LinkedInCandidate["match"] }) {
  const likely = level === "likely";
  return (
    <span className={cn("inline-flex h-5 items-center rounded-md px-1.5 text-[11px] font-medium", likely ? "bg-positive-soft text-positive" : "bg-caution-soft text-caution")}>
      {likely ? "Likely match" : "Unconfirmed match"}
    </span>
  );
}

function Fetched({ iso }: { iso?: string | null }) {
  if (!iso) return null;
  return <span className="tnum text-xs text-muted-foreground">Fetched {formatDate(iso.slice(0, 10))}</span>;
}

/** Panel frame: title, what it is, the refresh action, then the body. */
function Panel({ icon: Icon, title, note, action, children }: { icon: typeof Globe; title: string; note: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <article className="rounded-xl border bg-surface p-5 shadow-(--shadow-card) sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-sunken text-muted-foreground">
            <Icon className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-foreground">{title}</h3>
            <p className="mt-0.5 max-w-[60ch] text-xs leading-snug text-muted-foreground">{note}</p>
          </div>
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </article>
  );
}

function NotYet({ reason, what, plural, action }: { reason: string | null; what: string; plural?: boolean; action: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed bg-surface-sunken/60 px-4 py-5 sm:flex-row sm:items-center sm:justify-between">
      <p className="max-w-[52ch] text-[13px] leading-snug text-muted-foreground">
        {reason ?? `${what} ${plural ? "have" : "has"} not been looked up for this person yet. A lookup is a paid step: you will see the request count and confirm it first.`}
      </p>
      {reason ? null : action}
    </div>
  );
}

function ProfileCard({ c, primary }: { c: LinkedInCandidate; primary: boolean }) {
  const roles = (c.positions ?? []).filter((p) => p.title || p.company).slice(0, 4);
  const schools = (c.education ?? []).filter((e) => e.school).slice(0, 3);
  return (
    <div className={cn("rounded-lg border px-4 py-4", primary ? "border-hairline bg-surface" : "border-hairline bg-surface-sunken/50")}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold text-foreground">{c.name ?? "Name not shown"}</p>
          {c.headline ? <p className="mt-0.5 max-w-[60ch] text-[13px] leading-snug text-foreground">{c.headline}</p> : null}
        </div>
        <Match level={c.match} />
      </div>
      <p className="mt-2 text-xs leading-snug text-muted-foreground">{c.reason}</p>
      <dl className="mt-3 space-y-2 text-[13px]">
        {c.city ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <MapPin className="size-3.5 shrink-0" aria-hidden />
            <dd className="text-foreground">{c.city}</dd>
          </div>
        ) : null}
        {roles.length ? (
          <div className="flex items-start gap-2 text-muted-foreground">
            <Briefcase className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <dd className="space-y-0.5 text-foreground">
              {roles.map((p, i) => (
                <span key={i} className="tnum block">
                  {[p.title, p.company].filter(Boolean).join(" at ")}
                  {p.start || p.end ? <span className="text-muted-foreground"> ({[p.start, p.end].filter(Boolean).join(" to ")})</span> : null}
                </span>
              ))}
            </dd>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Briefcase className="size-3.5 shrink-0" aria-hidden />
            <dd>No roles returned for this profile</dd>
          </div>
        )}
        {schools.length ? (
          <div className="flex items-start gap-2 text-muted-foreground">
            <GraduationCap className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <dd className="space-y-0.5 text-foreground">
              {schools.map((e, i) => (
                <span key={i} className="tnum block">
                  {e.school}
                  {e.start_year || e.end_year ? <span className="text-muted-foreground"> ({[e.start_year, e.end_year].filter(Boolean).join(" to ")})</span> : null}
                </span>
              ))}
            </dd>
          </div>
        ) : null}
      </dl>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-hairline pt-3">
        <Fetched iso={c.fetched_at} />
        {c.profile_url ? (
          <a href={c.profile_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline">
            Open the public profile <ExternalLink className="size-3" aria-hidden />
          </a>
        ) : null}
      </div>
    </div>
  );
}

function ConfirmLookup({ open, onOpenChange, kind, data, busy, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; kind: EnrichKind; data: PersonEnrichment; busy: boolean; onConfirm: () => void }) {
  const est = data.estimate;
  const row = est.kinds[kind];
  const requests = row?.requests ?? 0;
  const label = kind === "linkedin" ? "public LinkedIn profile" : "mentions on the web";
  const blocked = !row?.allowed || requests > est.remaining;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Look up the {label}?</DialogTitle>
          <DialogDescription>This is a paid step. It runs only after you confirm.</DialogDescription>
        </DialogHeader>
        <dl className="tnum divide-y divide-hairline rounded-lg border border-hairline text-sm">
          <div className="flex items-center justify-between px-3.5 py-2.5">
            <dt className="text-muted-foreground">Bright Data requests, worst case</dt>
            <dd className="font-semibold text-foreground">{requests}</dd>
          </div>
          <div className="flex items-center justify-between px-3.5 py-2.5">
            <dt className="text-muted-foreground">Left this month ({est.month})</dt>
            <dd className="text-foreground">
              {est.remaining.toLocaleString("en-IN")} of {est.cap.toLocaleString("en-IN")}
            </dd>
          </div>
          <div className="flex items-center justify-between px-3.5 py-2.5">
            <dt className="text-muted-foreground">Dollar cost</dt>
            <dd className="text-foreground">$0 on the free allowance</dd>
          </div>
        </dl>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {kind === "linkedin"
            ? "Only public professional fields are kept (headline, roles, education, city, profile link). The match is shown as likely or unconfirmed with the reason, and it is never added to this person's facts."
            : "Only the title, source, date and link of each result are kept. Results are leads from web search, not verified."}
        </p>
        {blocked ? <p className="text-[13px] font-medium text-negative">{row?.reason ?? `Only ${est.remaining} requests are left this month, so this lookup cannot run.`}</p> : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={busy || blocked}>
            {busy ? <Loader2 className="animate-spin" /> : null} Confirm and look up
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EnrichmentPanels({ eventId, personId }: { eventId: string; personId: string }) {
  const { can } = useSession();
  const [data, setData] = useState<PersonEnrichment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<EnrichKind | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchState = useCallback(async () => {
    try {
      const next = await api.enrichment(eventId, personId);
      setData(next);
      setError(null);
      return next;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load.");
      return null;
    }
  }, [eventId, personId]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const next = await fetchState();
      if (!cancelled && next?.running) timer.current = setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [fetchState]);

  const start = async () => {
    if (!confirm || !data) return;
    setBusy(true);
    try {
      await api.refreshEnrichment(eventId, personId, [confirm], data.estimate.kinds[confirm]?.requests ?? 0);
      toast.success("Lookup started");
      setConfirm(null);
      const next = await fetchState();
      if (next?.running) {
        if (timer.current) clearTimeout(timer.current);
        const poll = async () => {
          const n = await fetchState();
          if (n?.running) timer.current = setTimeout(poll, POLL_MS);
          else toast.success("Lookup finished");
        };
        timer.current = setTimeout(poll, POLL_MS);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start the lookup.");
    } finally {
      setBusy(false);
    }
  };

  const header = <SectionHeader title="Public information" description="Public professional details and web mentions for this person. Fetched only on request, never added to their facts." />;
  if (error && !data) return (
    <section id="public-h" className="scroll-mt-24 space-y-4">
      {header}
      <ErrorState title="Public information could not be loaded" reason={error} onRetry={() => void fetchState()} />
    </section>
  );
  if (!data) return (
    <section id="public-h" className="scroll-mt-24 space-y-4" role="status" aria-label="Loading public information">
      {header}
      <SkeletonCard />
    </section>
  );

  const running = data.running;
  const li = data.record?.linkedin;
  const web = data.record?.web;
  const canRun = can("edit_rm");
  const runBtn = (kind: EnrichKind, label: string, icon: typeof Search) => {
    const Icon = icon;
    const isRunning = !!running?.kinds.includes(kind);
    return (
      <Button variant="outline" size="sm" disabled={isRunning || !canRun || !data.eligibility[kind].allowed} onClick={() => setConfirm(kind)}>
        {isRunning ? <Loader2 className="animate-spin" /> : <Icon />} {isRunning ? "Looking up" : label}
      </Button>
    );
  };

  const candidates = li?.candidates ?? [];
  const rows = web?.rows ?? [];

  return (
    <section id="public-h" className="scroll-mt-24 space-y-4">
      {header}

      <Panel
        icon={UserSearch}
        title="Public profile"
        note="From Bright Data's public LinkedIn people data. Headline, roles, education, city and profile link only. Never contact details."
        action={li && li.state !== "off" ? runBtn("linkedin", "Refresh", RefreshCw) : undefined}
      >
        {running?.kinds.includes("linkedin") && !candidates.length ? (
          <div className="flex items-center gap-3 rounded-lg bg-surface-sunken px-4 py-5 text-[13px] text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Looking up public profiles. This can take a couple of minutes.
          </div>
        ) : candidates.length ? (
          <div className="space-y-3">
            <ProfileCard c={candidates[0]} primary />
            {candidates.length > 1 ? (
              <details className="group/o rounded-lg border border-hairline">
                <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-medium text-foreground">
                  {candidates.length - 1} other public profile{candidates.length > 2 ? "s" : ""} with the same name
                </summary>
                <div className="space-y-3 border-t border-hairline p-3">
                  {candidates.slice(1).map((c, i) => (
                    <ProfileCard key={c.profile_url ?? i} c={c} primary={false} />
                  ))}
                </div>
              </details>
            ) : null}
            {li?.error ? <p className="text-xs text-negative">The last refresh did not work: {li.error} The profile above is the earlier result.</p> : null}
          </div>
        ) : li?.state === "none" ? (
          <p className="rounded-lg bg-surface-sunken px-4 py-4 text-[13px] text-muted-foreground">
            No public profile with this name was found{li.fetched_at ? ` (checked ${formatDate(li.fetched_at.slice(0, 10))})` : ""}. That is common: the data source returns thin results for many people.
          </p>
        ) : li?.state === "error" || li?.state === "off" ? (
          <p className="flex items-start gap-2 rounded-lg bg-negative-soft/60 px-4 py-4 text-[13px] text-foreground">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-negative" aria-hidden /> {li.error ?? "The lookup did not complete."}
          </p>
        ) : (
          <NotYet reason={data.eligibility.linkedin.allowed ? (canRun ? null : "Your role can read looked-up profiles but not start a paid lookup.") : data.eligibility.linkedin.reason} what="The public profile" action={runBtn("linkedin", "Look up public profile", Search)} />
        )}
      </Panel>

      <Panel
        icon={Globe}
        title="Mentions on the web"
        note={`Title, source, date and link of search results, ${data.web_label}. Leads to open, never facts about the person.`}
        action={web && web.state !== "off" ? runBtn("web", "Refresh", RefreshCw) : undefined}
      >
        {running?.kinds.includes("web") && !rows.length ? (
          <div className="flex items-center gap-3 rounded-lg bg-surface-sunken px-4 py-5 text-[13px] text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Searching the web.
          </div>
        ) : rows.length ? (
          <div className="space-y-2">
            <ul className="divide-y divide-hairline rounded-lg border border-hairline">
              {rows.map((r) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noreferrer noopener" className="group/r flex items-start justify-between gap-3 px-4 py-3 hover:bg-surface-sunken/60">
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-foreground group-hover/r:underline">{r.title}</span>
                      <span className="tnum mt-0.5 block text-xs text-muted-foreground">{[r.source, r.date].filter(Boolean).join(" · ")}</span>
                    </span>
                    <ExternalLink className="mt-1 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  </a>
                </li>
              ))}
            </ul>
            <p className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>{data.web_label}</span>
              <Fetched iso={web?.fetched_at} />
            </p>
            {web?.error ? <p className="text-xs text-negative">The last refresh did not work: {web.error} These are the earlier results.</p> : null}
          </div>
        ) : web?.state === "none" ? (
          <p className="rounded-lg bg-surface-sunken px-4 py-4 text-[13px] text-muted-foreground">No web results for this name and company{web.fetched_at ? ` (checked ${formatDate(web.fetched_at.slice(0, 10))})` : ""}.</p>
        ) : web?.state === "error" || web?.state === "off" ? (
          <p className="flex items-start gap-2 rounded-lg bg-negative-soft/60 px-4 py-4 text-[13px] text-foreground">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-negative" aria-hidden /> {web.error ?? "The search did not complete."}
          </p>
        ) : (
          <NotYet reason={data.eligibility.web.allowed ? (canRun ? null : "Your role can read looked-up mentions but not start a paid search.") : data.eligibility.web.reason} what="Web mentions" plural action={runBtn("web", "Search the web", Search)} />
        )}
      </Panel>

      {confirm ? <ConfirmLookup open onOpenChange={(o) => !o && setConfirm(null)} kind={confirm} data={data} busy={busy} onConfirm={() => void start()} /> : null}
    </section>
  );
}
