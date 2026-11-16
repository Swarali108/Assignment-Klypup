"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, CheckCircle2, Loader2, Lock, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";
import { v3, type ReviewItem, type ReviewQueue } from "@/lib/v3";
import { useSession } from "@/lib/session";
import { EmptyState, ErrorState, SkeletonCard, SkeletonRow } from "@/components/ds";
import { rmText, useLoad } from "@/components/today/use-load";
import { Button } from "@/components/ui/button";

const KIND: Record<ReviewItem["kind"], string> = { pair: "Same holder?", holder: "Person or organisation?", low: "Low confidence" };
type Tab = "open" | "decided";

/** "2026-11-15T20:00:00Z" → "2026-11-16": the India calendar day (fixed +05:30), like the rest of the app. */
function istDay(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? iso.slice(0, 10) : new Date(t + 330 * 60_000).toISOString().slice(0, 10);
}

/** The small "Reviewed by" line. */
export function ReviewedBy({ label, by, at }: { label: string; by: string; at: string | null }) {
  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <CheckCircle2 className="size-3.5 text-positive" aria-hidden />
      <span>
        Reviewed by <span className="font-medium text-foreground">{by || "a reviewer"}</span>
        {at ? <span className="tnum"> · {formatDate(istDay(at))}</span> : null}
        <span> · {label}</span>
      </span>
    </p>
  );
}

function Item({ item, onChange }: { item: ReviewItem; onChange: (next: ReviewItem) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const why = rmText(item.why);
  const decide = async (action: string) => {
    setBusy(action);
    try {
      const { decision } = await v3.decide(item.id, action);
      onChange({ ...item, decision });
      toast.success("Decision saved and applied");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save the decision.");
    } finally {
      setBusy(null);
    }
  };
  const undo = async () => {
    setBusy("undo");
    try {
      await v3.undo(item.id);
      onChange({ ...item, decision: null });
      toast.success("Decision taken back");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not take it back.");
    } finally {
      setBusy(null);
    }
  };
  return (
    <li className="px-5 py-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">{KIND[item.kind]}</span>
        <span className="text-xs text-muted-foreground">
          {item.event.company}
          {item.event.type_label ? ` · ${item.event.type_label}` : ""}
        </span>
      </div>
      <h3 className="mt-2 text-[15px] font-semibold">{item.title}</h3>
      <ul className="mt-2 space-y-1">
        {item.names.map((n, i) => (
          <li key={i} className="text-sm leading-snug text-foreground">
            {item.kind === "pair" ? <span className="mr-2 text-faint">{i === 0 ? "A" : "B"}</span> : null}
            {n}
          </li>
        ))}
      </ul>
      <p className="mt-2.5 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
        {why && item.pipeline ? `${why.replace(/[.!?]?\s*$/, ".")} ` : why}
        {item.pipeline ? `${item.pipeline}${item.by ? ` by ${item.by}` : ""}${item.score ? `, name match ${Math.round(item.score)}%` : ""}.` : ""}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {item.decision ? (
          <>
            <ReviewedBy label={item.decision.label} by={item.decision.by} at={item.decision.at} />
            <Button size="sm" variant="ghost" className="ml-auto" disabled={busy !== null} onClick={undo}>
              {busy === "undo" ? <Loader2 className="animate-spin" /> : <Undo2 />}
              Undo
            </Button>
          </>
        ) : (
          <>
            {item.actions.map((a, i) => (
              <Button key={a.action} size="sm" variant={i === 0 ? "default" : "outline"} disabled={busy !== null} onClick={() => decide(a.action)}>
                {busy === a.action ? <Loader2 className="animate-spin" /> : null}
                {a.label}
              </Button>
            ))}
            {item.link ? (
              <Button asChild size="sm" variant="ghost" className="ml-auto text-muted-foreground">
                <Link href={item.link}>
                  Open the call card <ArrowUpRight />
                </Link>
              </Button>
            ) : null}
          </>
        )}
      </div>
    </li>
  );
}

function Queue({ initial }: { initial: ReviewQueue }) {
  const [items, setItems] = useState(initial.items);
  const [tab, setTab] = useState<Tab>("open");
  const open = items.filter((i) => !i.decision);
  const decided = items.filter((i) => i.decision);
  const shown = tab === "open" ? open : decided;
  const replace = (next: ReviewItem) => setItems((xs) => xs.map((x) => (x.id === next.id ? next : x)));
  return (
    <div className="space-y-5">
      <div role="tablist" aria-label="Review items" className="flex gap-1.5">
        {(
          [
            ["open", `To review ${open.length}`],
            ["decided", `Decided ${decided.length}`],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "tnum h-8 rounded-lg border px-3 text-[13px] font-medium transition-colors",
              tab === id ? "border-primary bg-primary text-primary-foreground" : "bg-surface text-foreground hover:bg-accent",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <EmptyState icon={CheckCircle2} tone="brand" title={tab === "open" ? "Nothing waiting for review" : "No decisions yet"}>
          {tab === "open"
            ? "Every match and row the system was unsure about has a decision."
            : "Decisions you make are listed here with your name, and can be taken back."}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          {shown.map((i) => (
            <Item key={i.id} item={i} onChange={replace} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function ReviewView() {
  const { can, loading } = useSession();
  if (loading) return <SkeletonCard />;
  if (!can("review"))
    return (
      <EmptyState icon={Lock} title="The review queue is for the Head of RMs and admins" action={<Button asChild variant="outline"><Link href="/today">Back to Today</Link></Button>}>
        Ask your Head of RMs or an admin to review matches the system was unsure about.
      </EmptyState>
    );
  return <LoadedQueue />;
}

/** Only mounted once the session is known to allow review, so a viewer never fires a 403 request. */
function LoadedQueue() {
  const { load, retry } = useLoad(() => v3.review(), []);
  if (load.state === "loading")
    return (
      <div className="overflow-hidden rounded-xl border bg-surface" role="status" aria-label="Loading the review queue">
        {[0, 1, 2].map((i) => (
          <SkeletonRow key={i} />
        ))}
      </div>
    );
  if (load.state === "error") return <ErrorState title="The review queue could not be loaded" reason={load.reason} onRetry={retry} />;
  return <Queue initial={load.data} />;
}
