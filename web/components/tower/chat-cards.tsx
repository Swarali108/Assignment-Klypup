"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, CalendarDays, Check, ChevronDown, Copy, ExternalLink, FileText, Globe, Landmark, Layers, ScrollText, Sigma, User, UserSearch, Users } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { EVENT_TYPE_LABEL, formatCr } from "@/lib/format";
import { Avatar, CallList, EvidenceChip, InBookBadge, Money, PersonCardHeader, TierBadge, TimingPill, personHref } from "@/components/ds";
import { EventCard } from "@/components/events/event-card";
import type { CallItem, Evidence, EventSummary, PersonCard } from "@/lib/types";
import type { ChatCard, ChatScriptCard } from "@/lib/chat";
import { scriptText } from "@/lib/call-script";
import { callPackPrintHref, downloadCallPackMarkdown } from "@/lib/exports";
import { Button } from "@/components/ui/button";
import { DownloadMenu } from "./download-menu";

function CardFrame({ title, icon: Icon, children, aside }: { title: string; icon: typeof User; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="mt-5">
      <div className="mb-2.5 flex items-center gap-2">
        <Icon className="size-4 text-faint" aria-hidden />
        <h3 className="text-[13px] font-semibold text-foreground">{title}</h3>
        {aside ? <div className="ml-auto">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** A call-list row sized for the conversation column (the full PersonRow needs the page width). */
function ChatPersonRow({ item, asOf, rank }: { item: CallItem; asOf?: string; rank: number }) {
  const entity = item.person.holder_type !== "person";
  const sub = [item.person.kind_label, item.person.role, `${item.event.company} ${item.event.type_label ?? EVENT_TYPE_LABEL[item.event.type] ?? ""}`.trim()]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="group/row relative grid grid-cols-[auto_minmax(0,1fr)] gap-x-3.5 px-4 py-3.5 transition-colors hover:bg-accent/50 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:px-5">
      <div className="flex items-center gap-2.5 self-start">
        <span className="tnum hidden w-4 text-right text-xs text-faint sm:block">{rank}</span>
        <Avatar name={item.person.name} entity={entity} />
      </div>
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            href={personHref(item)}
            className="truncate text-[15px] font-semibold text-foreground after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {item.person.name}
          </Link>
          {item.in_book ? <InBookBadge /> : null}
        </div>
        <p className="truncate text-[13px] text-muted-foreground">{sub}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <TierBadge tier={item.tier} label={item.tier_label} />
          <TimingPill timing={item.timing} asOf={asOf} className="text-xs" />
        </div>
        {item.trades && item.trades.length > 1 ? (
          <p className="tnum mt-1.5 text-xs text-muted-foreground">
            Latest of {item.trades.length} sales at {item.event.company} in this answer
            {item.trades_total_display ? ` · ${item.trades_total_display} together` : ""}
          </p>
        ) : null}
      </div>
      <div className="col-start-2 mt-2 sm:col-start-auto sm:mt-0 sm:self-start">
        <Money amount={item.amount} size="md" align="end" showKind className="max-sm:items-start max-sm:text-left" />
      </div>
    </div>
  );
}

function PeopleCard({ card, asOf }: { card: ChatCard; asOf?: string }) {
  const items = (card.items as CallItem[]).filter((i) => i?.person?.name && i?.event?.id);
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 5);
  if (!items.length) return null;
  return (
    <CardFrame title={card.title} icon={Users} aside={<span className="tnum text-xs text-muted-foreground">{card.total && card.total > items.length ? `${items.length} of ${card.total} people` : `${items.length} ${items.length === 1 ? "person" : "people"}`}</span>}>
      <CallList>
        {shown.map((item, i) => (
          <ChatPersonRow key={item.id ?? `${item.event.id}/${item.person.id}`} item={item} asOf={asOf} rank={i + 1} />
        ))}
      </CallList>
      {items.length > 5 ? (
        <button type="button" onClick={() => setAll((a) => !a)} className="mt-2 inline-flex items-center gap-1 rounded-md px-1 text-xs font-medium text-brand-ink hover:underline">
          {all ? "Show fewer" : `Show all ${items.length}`}
          <ChevronDown className={cn("size-3.5 transition-transform", all && "rotate-180")} aria-hidden />
        </button>
      ) : null}
    </CardFrame>
  );
}

function EventsCard({ card }: { card: ChatCard }) {
  const items = (card.items as EventSummary[]).filter((e) => e?.id && e?.company);
  if (!items.length) return null;
  return (
    <CardFrame title={card.title} icon={Layers}>
      <div className={cn("grid gap-3", items.length > 1 && "sm:grid-cols-2")}>
        {items.map((e) => (
          <EventCard key={e.id} event={{ ...e, docs: e.docs ?? [] }} />
        ))}
      </div>
    </CardFrame>
  );
}

function PersonCallCard({ card, asOf }: { card: ChatCard; asOf?: string }) {
  const p = card.items[0] as PersonCard | undefined;
  if (!p?.person?.name || !p.brief) return null;
  const amounts = (p.amounts ?? []).filter((a) => a.inputs?.length);
  return (
    <CardFrame
      title={card.title}
      icon={User}
      aside={
        <Link href={personHref(p)} className="inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline">
          Open the full call card <ArrowUpRight className="size-3.5" aria-hidden />
        </Link>
      }
    >
      <PersonCardHeader card={p} asOf={asOf} />
      {amounts.length ? (
        <div className="mt-3 divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          {amounts.map((a, i) => (
            <div key={a.key} className="grid gap-2 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-foreground">{a.label}</p>
                {a.working ? <p className="tnum mt-0.5 text-xs text-muted-foreground">{a.working}</p> : null}
                <div className="mt-2 flex flex-wrap gap-1.5" data-tour={i === 0 ? "evidence" : undefined}>
                  {dedupe(a.inputs.flatMap((input) => input.evidence.slice(0, 1))).map((e) => (
                    <EvidenceChip key={`${e.doc_sha}-${e.pdf_index}-${e.quote.slice(0, 12)}`} evidence={e} />
                  ))}
                </div>
              </div>
              <Money value={a.value_cr} estimate={a.key === "retained"} size="md" align="end" className="max-sm:items-start max-sm:text-left" />
            </div>
          ))}
        </div>
      ) : null}
    </CardFrame>
  );
}

function dedupe(list: Evidence[]): Evidence[] {
  const seen = new Set<string>();
  return list.filter((e) => {
    const k = `${e.doc_sha}:${e.pdf_index}:${e.quote}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

type CalRow = {
  date_iso: string;
  display: string;
  relative?: string;
  label: string;
  event: { id: string; company: string };
  people_count?: number;
  total_cr?: number | null;
  people?: { id: string; name: string }[];
};

function CalendarCard({ card }: { card: ChatCard }) {
  const rows = (card.items as CalRow[]).filter((r) => r?.date_iso && r?.event);
  if (!rows.length) return null;
  return (
    <CardFrame title={card.title} icon={CalendarDays} aside={<Link href="/calendar" className="text-xs font-medium text-brand-ink hover:underline">Open calendar</Link>}>
      <ol className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
        {rows.map((r) => (
          <li key={`${r.date_iso}-${r.event.id}-${r.label}`} className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-4 px-5 py-3.5">
            <div className="tnum leading-tight">
              <p className="text-[13px] font-semibold text-foreground">{r.display}</p>
              {r.relative ? <p title={r.display} className="text-[11px] text-muted-foreground">{r.relative}</p> : null}
            </div>
            <div className="min-w-0">
              <Link href={`/events/${encodeURIComponent(r.event.id)}`} className="block truncate text-[13px] font-medium text-foreground hover:underline">
                {r.event.company}
              </Link>
              <p className="truncate text-xs text-muted-foreground">
                {r.label}
                {r.people_count ? ` · ${r.people_count} ${r.people_count === 1 ? "person" : "people"}` : ""}
              </p>
            </div>
            <span className="tnum text-sm font-semibold text-foreground">{formatCr(r.total_cr) ?? <span className="text-xs font-normal text-muted-foreground">Not disclosed</span>}</span>
          </li>
        ))}
      </ol>
    </CardFrame>
  );
}

/**
 * Lineage (reverse tree): person → event → each figure → the filing line it came from.
 * Accepts nested `children`, or flat items with `parent_id`; unknown kinds render as plain nodes.
 */
export type LineageNode = {
  id: string;
  label: string;
  kind?: "person" | "event" | "figure" | "filing" | "household" | string;
  detail?: string | null;
  href?: string | null;
  evidence?: Evidence | null;
  parent_id?: string | null;
  /** The API's own field names for the same things (parent, source, match, status, amount, date). */
  parent?: string | null;
  source?: { label?: string | null; url?: string | null; source_url?: string | null } | null;
  /** LinkedIn nodes: how sure the match is. The reason is in `detail`. */
  match?: "likely" | "unconfirmed" | null;
  status?: string | null;
  amount?: string | null;
  date?: string | null;
  children?: LineageNode[];
};

function nest(raw: LineageNode[]): LineageNode[] {
  const items = raw.map((i) => ({ ...i, parent_id: i.parent_id ?? i.parent ?? null }));
  if (!items.some((i) => i.parent_id)) return items;
  const byId = new Map(items.map((i) => [i.id, { ...i, children: [...(i.children ?? [])] }]));
  const roots: LineageNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
    if (parent) parent.children!.push(node);
    else roots.push(node);
  }
  return roots;
}

const KIND_ICON: Record<string, typeof User> = { person: User, event: Layers, figure: Sigma, filing: FileText, household: Users, same_person: User, family: Users, process: Layers, linkedin: UserSearch, web: Globe };
const STATUS_NOTE: Record<string, string> = { candidate: "Not run", skipped: "Not run", stopped: "Stopped", failed: "Failed" };

function LineageBranch({ node, depth }: { node: LineageNode; depth: number }) {
  const Icon = KIND_ICON[node.kind ?? ""] ?? Landmark;
  const kids = node.children ?? [];
  const label = node.href ? (
    <Link href={node.href} className="font-medium text-foreground hover:underline">
      {node.label}
    </Link>
  ) : (
    <span className={cn("text-foreground", node.kind !== "filing" && "font-medium")}>{node.label}</span>
  );
  return (
    <li className="relative">
      <div className="relative flex items-start gap-2.5 py-1.5">
        <span
          className={cn(
            "mt-0.5 grid size-6 shrink-0 place-items-center rounded-md ring-1 ring-inset",
            node.kind === "person" ? "bg-brand-soft text-brand-ink ring-brand/15" : node.kind === "figure" ? "bg-surface text-foreground ring-border" : "bg-surface-sunken text-muted-foreground ring-border",
          )}
        >
          <Icon className="size-3.5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 text-[13px] leading-snug">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="tnum">{label}</span>
            {node.match ? (
              <span className={cn("inline-flex h-5 items-center rounded-md px-1.5 text-[11px] font-medium", node.match === "likely" ? "bg-positive-soft text-positive" : "bg-caution-soft text-caution")}>
                {node.match === "likely" ? "Likely match" : "Unconfirmed match"}
              </span>
            ) : null}
            {node.amount ? <span className="tnum text-xs font-medium text-foreground">{node.amount}</span> : null}
            {node.status && STATUS_NOTE[node.status] ? <span className="rounded-md bg-surface-sunken px-1.5 py-0.5 text-[11px] text-muted-foreground">{STATUS_NOTE[node.status]}</span> : null}
            {node.detail && !node.evidence ? <span className="tnum text-xs text-muted-foreground">{node.detail}</span> : null}
          </div>
          {node.evidence ? <EvidenceChip evidence={node.evidence} className="mt-1" /> : null}
          {!node.evidence && node.source?.url ? (
            <a href={node.source.url} target="_blank" rel="noreferrer noopener" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline">
              {node.source.label || "Open the source"} <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
        </div>
      </div>
      {kids.length ? (
        <ul className={cn("relative ml-3 border-l border-border pl-5", depth > 2 && "pl-4")}>
          {kids.map((k) => (
            <LineageBranch key={k.id} node={k} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function LineageCard({ card }: { card: ChatCard }) {
  const roots = nest((card.items as LineageNode[]).filter((n) => n?.id && n?.label));
  if (!roots.length) return null;
  return (
    <CardFrame title={card.title} icon={Sigma}>
      <div className="rounded-xl border bg-surface px-5 py-4 shadow-(--shadow-card)">
        <ul>
          {roots.map((n) => (
            <LineageBranch key={n.id} node={n} depth={0} />
          ))}
        </ul>
      </div>
    </CardFrame>
  );
}

/** Lines that start with a quoted objection read as "objection — answer". */
function ScriptLine({ line }: { line: string }) {
  const m = line.match(/^(“[^”]+”)\s*[—–→-]\s*(.+)$/);
  if (!m) return <>{line}</>;
  return (
    <>
      <span className="font-medium text-foreground">{m[1]}</span>
      <span className="mt-0.5 block text-foreground/80">{m[2]}</span>
    </>
  );
}

/** v2 call script: sections the RM reads on the call, copy-all, and the call pack download. */
export function ScriptCardView({ card, actions = true }: { card: ChatScriptCard; actions?: boolean }) {
  const [copied, setCopied] = useState(false);
  const sections = (card.sections ?? []).filter((s) => s?.heading && Array.isArray(s.lines) && s.lines.length);
  if (!sections.length) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(scriptText({ title: card.title, sections }));
      setCopied(true);
      toast.success("Script copied");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not copy. Select the text and copy it instead.");
    }
  };
  const p = card.person;
  return (
    <section className="mt-5 overflow-hidden rounded-2xl border bg-surface shadow-(--shadow-card)" aria-label={card.title}>
      <header className="flex flex-col gap-3 border-b border-hairline px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-ink">
            <ScrollText className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-[15px] leading-snug font-semibold text-foreground">{card.title}</h3>
            {p?.event_id && p?.person_id ? (
              <Link href={`/people/${encodeURIComponent(p.event_id)}/${encodeURIComponent(p.person_id)}`} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline">
                Numbers filled from {p.name}&rsquo;s call card <ArrowUpRight className="size-3" aria-hidden />
              </Link>
            ) : null}
          </div>
        </div>
        {actions ? (
          <div className="flex shrink-0 gap-2">
            <Button variant="outline" size="sm" onClick={copy} className="bg-surface">
              {copied ? <Check className="text-positive" /> : <Copy />}
              {copied ? "Copied" : "Copy all"}
            </Button>
            {p?.event_id && p?.person_id ? (
              <DownloadMenu
                label="Download call pack"
                what="call pack"
                pdfHref={callPackPrintHref(p.event_id, p.person_id)}
                onMarkdown={() => downloadCallPackMarkdown(p.event_id, p.person_id, p.name)}
              />
            ) : null}
          </div>
        ) : null}
      </header>
      <ol className="divide-y divide-hairline">
        {sections.map((s) => {
          const numbered = /question/i.test(s.heading);
          return (
            <li key={s.heading} className="grid gap-x-6 gap-y-2 px-5 py-4 sm:grid-cols-[8.5rem_minmax(0,1fr)] sm:px-6">
              <h4 className="text-[13px] font-semibold text-foreground sm:pt-px">{s.heading}</h4>
              <ul className="space-y-2">
                {s.lines.map((line, i) => (
                  <li key={i} className="flex gap-2.5 text-[14px] leading-relaxed text-foreground">
                    {numbered ? (
                      <span className="tnum mt-[3px] grid size-5 shrink-0 place-items-center rounded-full bg-secondary text-[11px] font-medium text-muted-foreground">{i + 1}</span>
                    ) : (
                      <span className="mt-[9px] size-1 shrink-0 rounded-full bg-faint" aria-hidden />
                    )}
                    <span className="tnum max-w-[68ch] text-pretty">
                      <ScriptLine line={line} />
                    </span>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** One `cards` event, drawn with the design-system components. Unknown kinds or shapes render nothing. */
export function ChatCardView({ card, asOf }: { card: ChatCard; asOf?: string }) {
  if (card?.kind === "script") return <ScriptCardView card={card as ChatScriptCard} />;
  if (!card || !Array.isArray(card.items)) return null;
  switch (card.kind) {
    case "people":
      return <PeopleCard card={card} asOf={asOf} />;
    case "events":
      return <EventsCard card={card} />;
    case "person":
      return <PersonCallCard card={card} asOf={asOf} />;
    case "calendar":
      return <CalendarCard card={card} />;
    case "lineage":
      return <LineageCard card={card} />;
    default:
      return null;
  }
}
