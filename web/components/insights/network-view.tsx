"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowUpRight, Building2, Layers, Network, PhoneCall, Users } from "lucide-react";
import { EmptyState, ErrorState, SkeletonStat, StatCard, StatStrip, TierBadge } from "@/components/ds";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCr } from "@/lib/format";
import { insightsApi, useLoad, type NetEdge, type NetNode, type NetworkResponse } from "@/lib/insights";
import { cn } from "@/lib/utils";
import type { GNode } from "./graph-canvas";

const GraphCanvas = dynamic(() => import("./graph-canvas").then((m) => m.GraphCanvas), {
  ssr: false,
  loading: () => <GraphLoading />,
});

const GRAPH_H = 620;

/** "ACME STEELS LIMITED" → "Acme Steels Limited" (all-caps company names only). */
export function tidyCompany(name: string): string {
  if (name !== name.toUpperCase()) return name;
  return name.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase());
}

function radius(n: NetNode, maxPeople: number): number {
  if (n.type === "event") return 5 + 6 * Math.sqrt((n.people_count ?? 0) / Math.max(1, maxPeople));
  if (n.type === "entity") return 2.6;
  const v = n.value_cr ?? 0;
  return Math.min(9, 2.8 + Math.sqrt(v) * 0.32);
}

function nodeHref(n: NetNode): string | null {
  if (n.type === "event") return `/events/${encodeURIComponent(n.event?.id ?? n.id.slice(2))}`;
  if (n.event_id && n.person_id) return `/people/${encodeURIComponent(n.event_id)}/${encodeURIComponent(n.person_id)}`;
  return null;
}

export function NetworkView() {
  const [res, retry] = useLoad(insightsApi.network);
  if (res.state === "loading") return <NetworkSkeleton />;
  if (res.state === "error") return <ErrorState title="The network could not load" reason={res.reason} onRetry={retry} />;
  if (res.data.nodes.length === 0)
    return (
      <EmptyState icon={Network} title="No relationships yet" tone="brand">
        Once events are read, holders, households and people who appear in more than one event show up here.
      </EmptyState>
    );
  return <Graph data={res.data} />;
}

type House = { id: string; members: NetNode[]; reason: string; event: string };

type Lens = "across" | "repeat" | "families" | "institutions" | "all";

/** Each lens answers one RM question; the headline under it says what the graph is showing. */
const LENSES: { value: Lens; label: string; test: (n: NetNode) => boolean }[] = [
  { value: "across", label: "Across companies", test: (n) => n.type === "person" && (n.event_count ?? 0) > 1 },
  { value: "repeat", label: "Repeat sellers", test: (n) => n.type === "person" && (n.money_events ?? 0) > 1 },
  { value: "families", label: "Families", test: (n) => Boolean(n.in_household) },
  { value: "institutions", label: "Funds & brokers", test: (n) => n.type === "entity" },
  { value: "all", label: "Everyone", test: () => true },
];
const MIN_CR = [0, 1, 10, 50];

function insight(lens: Lens, people: number, companies: number, families: number): { title: string; sub: string } {
  const p = (n: number, one: string, many: string) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
  switch (lens) {
    case "across":
      return { title: `${p(people, "person", "people")} came into money from more than one company`, sub: "Active investors with cash from several deals: often the strongest first calls." };
    case "repeat":
      return { title: `${p(people, "person", "people")} turned shares into cash more than once`, sub: "Recurring liquidity: promoters and insiders selling again and again. Time the call to the next sale." };
    case "families":
      return { title: `${p(families, "family", "families")}, ${p(people, "person", "people")}`, sub: "One relationship can open several wallets: call the family, not just one name." };
    case "institutions":
      return { title: `${p(people, "fund or broker", "funds and brokers")} across ${p(companies, "company", "companies")}`, sub: "Not on the call list, but they show who is active in the market and who sits on the other side of the deal." };
    default:
      return { title: `${p(people, "holder", "holders")} linked across ${p(companies, "company", "companies")}`, sub: "Everyone who connects more than one deal, sells repeatedly, or belongs to a family group." };
  }
}

function Graph({ data }: { data: NetworkResponse }) {
  const router = useRouter();
  const [lens, setLens] = useState<Lens>("across");
  const [types, setTypes] = useState<Set<string>>(new Set());
  const [minCr, setMinCr] = useState(0);
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState<GNode | null>(null);

  const byId = useMemo(() => new Map(data.nodes.map((n) => [n.id, n])), [data]);
  const kinds = useMemo(() => new Set(data.edges.map((e) => e.kind)), [data]);
  const lensCounts = useMemo(
    () => Object.fromEntries(LENSES.map((l) => [l.value, data.nodes.filter((n) => n.type !== "event" && l.test(n)).length])) as Record<Lens, number>,
    [data],
  );
  const typeCounts = useMemo(() => {
    const c = new Map<string, number>();
    for (const n of data.nodes) if (n.type === "event") for (const t of n.event_types ?? []) c.set(t, (c.get(t) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);

  const view = useMemo(() => {
    const test = LENSES.find((l) => l.value === lens)!.test;
    const q = query.trim().toLowerCase();
    const typeOk = (n: NetNode) => types.size === 0 || (n.event_types ?? []).some((t) => types.has(t));
    const holders = data.nodes.filter(
      (n) =>
        n.type !== "event" &&
        test(n) &&
        typeOk(n) &&
        (minCr === 0 || (n.value_cr ?? -1) >= minCr) &&
        (!q ||
          n.label.toLowerCase().includes(q) ||
          [n.company ?? "", ...(n.also_in ?? [])].some((c) => c.toLowerCase().includes(q))),
    );
    const hid = new Set(holders.map((n) => n.id));
    const linked = new Set(data.edges.filter((e) => e.kind === "holds" && hid.has(e.source)).map((e) => e.target));
    const companies = data.nodes.filter((n) => n.type === "event" && linked.has(n.id) && typeOk(n));
    const keep = new Set([...hid, ...companies.map((c) => c.id)]);
    const edges = data.edges.filter((e) => keep.has(e.source) && keep.has(e.target));
    const maxPeople = Math.max(1, ...companies.map((n) => n.people_count ?? 0));
    const nodes = [...companies, ...holders].map((n) => ({ ...n, r: radius(n, maxPeople) })) as GNode[];
    const counted = holders.filter((n) => n.type !== "entity" && n.value_cr != null);
    const inPlay = counted.reduce((sum, n) => sum + (n.value_cr ?? 0), 0);
    const estimate = counted.some((n) => n.estimate);
    return { nodes, edges, holders, companies, inPlay, estimate, families: groupHouseholds(edges, byId).length };
  }, [data, byId, lens, types, minCr, query]);

  const houses = useMemo(() => groupHouseholds(data.edges, byId), [data, byId]);
  const counts = useMemo(() => {
    const c = { event: 0, person: 0, entity: 0 };
    for (const n of data.nodes) c[n.type] += 1;
    return c;
  }, [data]);
  const linksOf = (id: string) => data.edges.filter((e) => e.kind !== "holds" && (e.source === id || e.target === id));
  const filtered = types.size > 0 || minCr > 0 || query.trim() !== "";
  const headline = insight(lens, view.holders.length, view.companies.length, view.families);
  const toggleType = (t: string) =>
    setTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  const clear = () => {
    setTypes(new Set());
    setMinCr(0);
    setQuery("");
  };

  return (
    <div className="space-y-10">
      <StatStrip>
        <StatCard label="Companies" icon={Layers} value={counts.event} sub="With money events in this network" />
        <StatCard label="People" icon={PhoneCall} value={counts.person} sub="Across companies, repeat sellers, families" />
        <StatCard label="Funds and brokers" icon={Building2} value={counts.entity} sub="Kept off the call list" />
        <StatCard label="Households" icon={Users} value={houses.length} sub={`${houses.reduce((s, h) => s + h.members.length, 0)} people in family groups`} />
      </StatStrip>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <div className="space-y-3 border-b border-hairline px-4 pt-4 pb-3 sm:px-5">
            <div role="tablist" aria-label="What the network shows" className="flex min-w-0 flex-wrap gap-1">
              {LENSES.map((l) => {
                const on = lens === l.value;
                return (
                  <button
                    key={l.value}
                    role="tab"
                    type="button"
                    aria-selected={on}
                    onClick={() => {
                      setLens(l.value);
                      setFocus(null);
                    }}
                    className={cn(
                      "inline-flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors",
                      on ? "bg-primary text-primary-foreground shadow-(--shadow-card)" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    {l.label}
                    <span className={cn("tnum rounded-md px-1.5 text-xs", on ? "bg-primary-foreground/15" : "bg-secondary text-muted-foreground")}>{lensCounts[l.value]}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
              <div className="min-w-0">
                <p className="text-[15px] leading-snug font-semibold text-foreground">{headline.title}</p>
                <p className="mt-0.5 text-[13px] leading-snug text-muted-foreground">{headline.sub}</p>
              </div>
              {view.inPlay > 0 && lens !== "institutions" ? (
                <p className="shrink-0 text-[13px] text-muted-foreground">
                  <span className="tnum font-semibold text-foreground">{view.estimate ? "≈ " : ""}{formatCr(view.inPlay)}</span> in play
                </p>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {typeCounts.map(([t, n]) => {
                const on = types.has(t);
                return (
                  <button
                    key={t}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleType(t)}
                    className={cn(
                      "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors",
                      on ? "border-brand bg-brand/10 text-foreground" : "border-border text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {t} <span className="tnum text-faint">{n}</span>
                  </button>
                );
              })}
              <label className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border px-2.5 text-xs text-muted-foreground">
                <span>Amount</span>
                <select
                  value={minCr}
                  onChange={(e) => setMinCr(Number(e.target.value))}
                  className="bg-transparent text-xs font-medium text-foreground outline-none"
                  aria-label="Minimum amount"
                >
                  {MIN_CR.map((v) => (
                    <option key={v} value={v}>
                      {v === 0 ? "Any" : `₹${v} Cr+`}
                    </option>
                  ))}
                </select>
              </label>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Find a name or company"
                aria-label="Find a name or company"
                className="h-7 w-48 rounded-full border border-border bg-transparent px-3 text-xs text-foreground outline-none placeholder:text-faint focus-visible:ring-2 focus-visible:ring-ring"
              />
              {filtered ? (
                <button type="button" onClick={clear} className="text-xs font-medium text-brand-ink hover:underline">
                  Clear filters
                </button>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
              <Key swatch={<span className="size-3 rounded-full bg-foreground ring-2 ring-surface" />} label="Company with a money event" />
              <Key swatch={<span className="size-2.5 rounded-full bg-brand" />} label="Cash in hand" />
              <Key swatch={<span className="size-2.5 rounded-full bg-caution" />} label="Shares just unlocked" />
              <Key swatch={<span className="size-2.5 rounded-full bg-chart-4" />} label="Holds shares" />
              <Key swatch={<span className="size-2 rounded-[2px] bg-chart-5" />} label={data.legend.entity ?? "Company or fund"} />
              {kinds.has("household") ? <Key swatch={<span className="h-0.5 w-4 rounded bg-brand" />} label={data.legend.household ?? "Same household"} /> : null}
            </div>
          </div>

          <div className="relative bg-surface-sunken/60">
            {view.holders.length ? (
              <GraphCanvas
                key={`${lens}-${[...types].join(",")}-${minCr}-${query}`}
                nodes={view.nodes}
                edges={view.edges}
                height={GRAPH_H}
                focusId={focus?.id ?? null}
                onHover={setFocus}
                onPick={(n) => {
                  const href = nodeHref(n);
                  if (href) router.push(href);
                }}
              />
            ) : (
              <div className="grid place-items-center px-6 text-center" style={{ height: GRAPH_H }}>
                <div className="max-w-sm space-y-2">
                  <p className="text-sm font-medium text-foreground">No one matches this view</p>
                  <p className="text-[13px] text-muted-foreground">Try another lens, a lower amount, or clear the filters.</p>
                  {filtered ? (
                    <button type="button" onClick={clear} className="text-xs font-medium text-brand-ink hover:underline">
                      Clear filters
                    </button>
                  ) : null}
                </div>
              </div>
            )}
            {focus ? (
              <HoverCard node={focus} byId={byId} links={linksOf(focus.id)} onClose={() => setFocus(null)} />
            ) : view.holders.length ? (
              <p className="pointer-events-none absolute bottom-3 left-4 rounded-md bg-surface/90 px-2 py-1 text-xs text-muted-foreground shadow-(--shadow-card)">
                <span className="pointer-coarse:hidden">Hover a dot to see who it is · click to open · click empty space to clear</span>
                <span className="pointer-fine:hidden">Tap a dot to see who it is · pinch to zoom</span>
              </p>
            ) : null}
          </div>
        </div>

        <aside className="space-y-3">
          <div className="space-y-1">
            <h2 className="flex items-baseline gap-2 text-base font-semibold">
              Households <span className="tnum text-sm font-normal text-muted-foreground">{houses.length}</span>
            </h2>
            <p className="text-sm text-muted-foreground">Holders grouped as one family, with the reason we linked them.</p>
          </div>
          {houses.length ? (
            <div className="divide-y divide-hairline overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card) lg:max-h-[620px] lg:overflow-y-auto">
              {houses.map((h) => (
                <div key={h.id} className="px-4 py-3.5">
                  <p className="mb-2 text-xs text-muted-foreground">{h.event}</p>
                  <ul className="space-y-1.5">
                    {h.members.map((m) => (
                      <li key={m.id} className="flex items-center justify-between gap-3">
                        <Link
                          href={nodeHref(m) ?? "#"}
                          onMouseEnter={() => setFocus({ ...m, r: 4 })}
                          onMouseLeave={() => setFocus(null)}
                          className="min-w-0 truncate text-[13px] font-medium hover:text-brand-ink hover:underline"
                        >
                          {m.label}
                        </Link>
                        <span className={cn("tnum shrink-0 text-xs", m.value_cr == null ? "text-faint" : "text-muted-foreground")}>
                          {m.value_cr == null ? "Not disclosed" : `${m.estimate ? "≈ " : ""}${formatCr(m.value_cr)}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 line-clamp-2 text-xs leading-snug text-faint" title={h.reason}>
                    {h.reason}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed bg-surface px-5 py-8 text-center text-sm text-muted-foreground">
              No households found in the filings read so far.
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Key({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className="inline-flex w-4 justify-center">{swatch}</span>
      {label}
    </span>
  );
}

/** "2 people and 1 fund linked here": what the lines into a company dot are. */
function linkedLine(node: NetNode): string {
  const p = node.linked_people ?? 0;
  const e = node.linked_entities ?? 0;
  const parts = [p ? `${p} ${p === 1 ? "person" : "people"}` : null, e ? `${e} ${e === 1 ? "company or fund" : "companies or funds"}` : null];
  const text = parts.filter(Boolean).join(" and ");
  return text ? `${text} linked here` : `${node.people_count ?? 0} linked here`;
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function HoverCard({ node, byId, links, onClose }: { node: NetNode; byId: Map<string, NetNode>; links: NetEdge[]; onClose: () => void }) {
  const href = nodeHref(node);
  const kind =
    node.type === "event"
      ? "Money event"
      : node.type === "entity" || /\b(trust|fund|llp|limited|ltd|huf|private|company|holdings)\b/i.test(node.label)
        ? "Company, trust or fund"
        : "Person";
  const eventLabel = node.type === "event" ? null : node.company ?? null;
  return (
    <div className="absolute top-3 left-3 w-[min(320px,calc(100%-1.5rem))] rounded-xl border bg-surface p-4 shadow-(--shadow-raised)">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium text-muted-foreground">{kind}</p>
        <button type="button" onClick={onClose} className="text-xs text-muted-foreground hover:text-foreground" aria-label="Close">
          Close
        </button>
      </div>
      <p className="mt-0.5 text-[15px] leading-snug font-semibold">{node.type === "event" ? tidyCompany(node.label) : node.label}</p>
      {node.type === "event" ? (
        <>
          <p className="mt-1 text-[13px] text-muted-foreground">
            {node.to_call ? (
              <>
                <span className="tnum font-medium text-foreground">{node.to_call}</span> {node.to_call === 1 ? "person" : "people"} to call
              </>
            ) : (
              "No individual to call here"
            )}
            {" · "}
            {linkedLine(node)}
          </p>
          {(node.events?.length ?? 0) > 1 ? (
            <ul className="mt-3 space-y-1.5 border-t border-hairline pt-3">
              {node.events!.slice(0, 4).map((r) => (
                <li key={r.event.id} className="flex items-baseline justify-between gap-3 text-xs">
                  <Link href={`/events/${encodeURIComponent(r.event.id)}`} className="truncate font-medium text-foreground hover:underline">
                    {r.event.type_label ?? r.event.type}
                    {r.date_iso ? <span className="font-normal text-muted-foreground"> · {shortDate(r.date_iso)}</span> : null}
                  </Link>
                  <span className="shrink-0 tnum text-muted-foreground">{r.to_call ? `${r.to_call} to call` : "none to call"}</span>
                </li>
              ))}
              {node.events!.length > 4 ? (
                <li className="text-xs text-muted-foreground">and {node.events!.length - 4} more events</li>
              ) : null}
            </ul>
          ) : null}
        </>
      ) : (
        <>
          <p className="mt-1 text-[13px] text-muted-foreground">
            {[node.role, eventLabel ? tidyCompany(eventLabel) : null].filter(Boolean).join(" · ")}
          </p>
          <div className="mt-3 flex items-center justify-between gap-3">
            {node.type === "person" && node.tier ? <TierBadge tier={node.tier} /> : <span />}
            <span className={cn("tnum text-sm", node.value_cr == null ? "text-muted-foreground" : "font-semibold")}>
              {node.value_cr == null ? "Amount not disclosed" : `${node.estimate ? "≈ " : ""}${formatCr(node.value_cr)}`}
            </span>
          </div>
        </>
      )}
      {(() => {
        const rows: { label: string; value: string }[] = [
          ...links
            .map((l) => byId.get(l.source === node.id ? l.target : l.source)?.label)
            .filter((v): v is string => Boolean(v))
            .map((value) => ({ label: "Same household", value })),
          ...(node.also_in ?? []).map((company) => ({ label: "Also in", value: tidyCompany(company) })),
        ];
        const seen = new Set<string>();
        const unique = rows.filter((r) => !seen.has(r.label + r.value) && seen.add(r.label + r.value));
        return unique.length ? (
          <ul className="mt-3 space-y-1.5 border-t border-hairline pt-3">
            {unique.slice(0, 4).map((r, i) => (
              <li key={i} className="text-xs leading-snug text-muted-foreground">
                <span className="font-medium text-foreground">{r.label}: {r.value}</span>
              </li>
            ))}
          </ul>
        ) : null;
      })()}
      {href ? (
        <Link href={href} className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline">
          {node.type === "event"
            ? (node.events?.length ?? 0) > 1
              ? node.events![0].to_call
                ? "Open the event with the most calls"
                : "Open the latest event"
              : "Open the event"
            : "Open the call card"}{" "}
          <ArrowUpRight className="size-3.5" />
        </Link>
      ) : null}
    </div>
  );
}

function groupHouseholds(edges: NetEdge[], byId: Map<string, NetNode>): House[] {
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    while (parent.get(x) !== x) x = parent.get(x)!;
    return x;
  };
  const reasons = new Map<string, string>();
  for (const e of edges) {
    if (e.kind !== "household") continue;
    for (const id of [e.source, e.target]) if (!parent.has(id)) parent.set(id, id);
    parent.set(find(e.source), find(e.target));
    reasons.set(e.source, e.reason);
  }
  const groups = new Map<string, string[]>();
  for (const id of parent.keys()) groups.set(find(id), [...(groups.get(find(id)) ?? []), id]);
  return [...groups.entries()]
    .map(([root, ids]) => {
      const members = ids.map((i) => byId.get(i)).filter((n): n is NetNode => !!n);
      members.sort((a, b) => (b.value_cr ?? -1) - (a.value_cr ?? -1));
            return { id: root, members, reason: ids.map((i) => reasons.get(i)).find(Boolean) ?? "", event: tidyCompany(members[0]?.company ?? "") };
    })
    .sort((a, b) => b.members.length - a.members.length || a.event.localeCompare(b.event));
}

function GraphLoading() {
  return (
    <div className="grid place-items-center text-sm text-muted-foreground" style={{ height: GRAPH_H }}>
      Drawing the network…
    </div>
  );
}

function NetworkSkeleton() {
  return (
    <div className="space-y-10" role="status" aria-label="Loading the network">
      <StatStrip>
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
      </StatStrip>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Skeleton className="rounded-xl" style={{ height: GRAPH_H + 56 }} />
        <div className="space-y-3">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-80 rounded-xl" />
        </div>
      </div>
    </div>
  );
}
