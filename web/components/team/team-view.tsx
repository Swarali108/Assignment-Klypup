"use client";

import Link from "next/link";
import { Lock, PhoneCall, UsersRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCr, formatDate } from "@/lib/format";
import { v3, type TeamCounts, type TeamDashboard } from "@/lib/v3";
import { useSession } from "@/lib/session";
import { EmptyState, ErrorState, SectionHeader, SkeletonCard, SkeletonStat, StatCard, StatStrip } from "@/components/ds";
import { useLoad } from "@/components/today/use-load";
import { Button } from "@/components/ui/button";

const SERIES = [
  { key: "calls", label: "Calls logged", bar: "bg-brand" },
  { key: "meetings", label: "Meetings booked", bar: "bg-chart-2" },
  { key: "won", label: "Won", bar: "bg-positive" },
] as const;

function Legend() {
  return (
    <ul className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted-foreground">
      {SERIES.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className={cn("size-2.5 rounded-sm", s.bar)} aria-hidden />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

/** One row of grouped bars: calls, meetings, won on one shared scale (the largest call count on the page). */
function FunnelRow({ title, sub, c, max }: { title: React.ReactNode; sub?: React.ReactNode; c: TeamCounts; max: number }) {
  return (
    <li className="grid grid-cols-1 items-center gap-x-6 gap-y-3 px-5 py-4 lg:grid-cols-[13rem_minmax(0,1fr)_minmax(0,17rem)]">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold">{title}</p>
        {sub ? <p className="truncate text-xs text-muted-foreground">{sub}</p> : null}
      </div>
      <div className="space-y-1.5" role="img" aria-label={`${c.calls} calls logged, ${c.meetings} meetings booked, ${c.won} won`}>
        {SERIES.map((s) => (
          <div key={s.key} className="flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-sunken">
              <div className={cn("h-full rounded-full", s.bar)} style={{ width: c[s.key] ? `${Math.max(3, (c[s.key] / max) * 100)}%` : "0%" }} />
            </div>
            <span className="tnum w-7 text-right text-xs font-medium">{c[s.key]}</span>
          </div>
        ))}
      </div>
      <dl className="tnum grid grid-cols-3 gap-3 text-xs">
        <div>
          <dt className="text-muted-foreground">Won (₹)</dt>
          <dd className="mt-0.5 text-[13px] font-semibold">{c.won ? formatCr(c.won_cr) : "None yet"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Follow-ups due</dt>
          <dd className={cn("mt-0.5 text-[13px] font-semibold", c.followups_due > 0 && "text-caution")}>{c.followups_due}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">To first call</dt>
          <dd className="mt-0.5 text-[13px] font-semibold">{c.days_to_first_call === null ? "No calls" : `${c.days_to_first_call} ${c.days_to_first_call === 1 ? "day" : "days"}`}</dd>
        </div>
      </dl>
    </li>
  );
}

function TeamBody({ data }: { data: TeamDashboard }) {
  const { total } = data;
  const max = Math.max(1, ...data.rms.map((r) => r.calls), ...data.event_types.map((t) => t.calls));
  const nothing = total.calls === 0 && total.assigned === 0;
  return (
    <div className="space-y-10">
      <StatStrip>
        <StatCard label="Calls logged" value={total.calls} sub={`${total.assigned} people assigned to RMs`} />
        <StatCard label="Meetings booked" value={total.meetings} sub={total.calls ? `${Math.round((total.meetings / total.calls) * 100)}% of calls` : "No calls yet"} />
        <StatCard label="Won" value={total.won} sub={total.won ? `${formatCr(total.won_cr)} new money, entered by the RMs` : "Amounts are entered by the RM"} />
        <StatCard
          label="Event to first call"
          value={total.days_to_first_call === null ? "—" : `${total.days_to_first_call} d`}
          muted={total.days_to_first_call === null}
          sub={total.days_to_first_call === null ? "Shows once a call is logged" : `Median over ${total.days_samples} ${total.days_samples === 1 ? "lead" : "leads"}`}
        />
      </StatStrip>

      {nothing ? (
        <EmptyState icon={PhoneCall} title="No calls logged yet" tone="brand" action={<Button asChild variant="outline"><Link href="/today">Open Today</Link></Button>}>
          Assign people to RMs from Today or a person&apos;s page. Once an RM logs a call, the outcomes appear here.
        </EmptyState>
      ) : null}

      <section className="space-y-4">
        <SectionHeader title="By RM" description="Each lead counts for the RM it is assigned to, or for whoever logged its outcome." actions={<Legend />} />
        {data.rms.length ? (
          <ul className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
            {data.rms.map((r) => (
              <FunnelRow key={r.email} title={r.name} sub={`${r.assigned} assigned${r.role && r.role !== "rm" ? ` · ${r.role === "head" ? "Head of RMs" : "Admin"}` : ""}`} c={r} max={max} />
            ))}
          </ul>
        ) : (
          <EmptyState icon={UsersRound} title="No RMs yet">RMs appear here once they have an account.</EmptyState>
        )}
        {data.unassigned_calls ? (
          <p className="text-xs text-muted-foreground">{data.unassigned_calls} logged {data.unassigned_calls === 1 ? "call has" : "calls have"} no assigned RM and no recorded author (earlier notes).</p>
        ) : null}
      </section>

      <section className="space-y-4">
        <SectionHeader title="By event type" description="The same outcomes, grouped by what kind of event the money came from." />
        {data.event_types.length ? (
          <ul className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
            {data.event_types.map((t) => (
              <FunnelRow key={t.event_type} title={t.type_label} sub={`${t.assigned} assigned`} c={t} max={max} />
            ))}
          </ul>
        ) : (
          <p className="rounded-xl border border-dashed bg-surface px-5 py-6 text-sm text-muted-foreground">Nothing assigned or called for any event type yet.</p>
        )}
      </section>
      <p className="text-xs text-muted-foreground">Data as of {formatDate(data.as_of)}. Counts come from what the RMs logged; nothing here is estimated.</p>
    </div>
  );
}

export function TeamView() {
  const { can, loading } = useSession();
  if (loading) return <SkeletonCard />;
  if (!can("team"))
    return (
      <EmptyState icon={Lock} title="The team dashboard is for the Head of RMs" action={<Button asChild variant="outline"><Link href="/today">Back to Today</Link></Button>}>
        It shows every RM&apos;s calls, meetings and wins. Ask your Head of RMs or an admin if you need it.
      </EmptyState>
    );
  return <LoadedTeam />;
}

/** Only mounted once the session is known to allow the team view, so an RM or viewer never fires a 403 request. */
function LoadedTeam() {
  const { load, retry } = useLoad(() => v3.team(), []);
  if (load.state === "loading")
    return (
      <div className="space-y-8" role="status" aria-label="Loading the team dashboard">
        <StatStrip>
          {[0, 1, 2, 3].map((i) => (
            <SkeletonStat key={i} />
          ))}
        </StatStrip>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  if (load.state === "error") return <ErrorState title="The team dashboard could not be loaded" reason={load.reason} onRetry={retry} />;
  return <TeamBody data={load.data} />;
}
