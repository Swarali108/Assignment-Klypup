"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Printer } from "lucide-react";
import { Wordmark } from "@/components/ds";
import { Button } from "@/components/ui/button";
import { properName, shortCompany } from "@/lib/call-script";
import { formatCr } from "@/lib/format";
import type { ChatCard, ChatScriptCard } from "@/lib/chat";
import type { CallItem, Evidence, EventSummary, PersonCard } from "@/lib/types";

/**
 * A4 print page: screen toolbar (back, print) that disappears on paper, a letterhead, and the body.
 * `?print=1` opens the browser's print dialog (Save as PDF) once the content is ready.
 */
export function PrintFrame({ title, subtitle, backHref, backLabel, ready, children }: { title: string; subtitle?: React.ReactNode; backHref: string; backLabel: string; ready: boolean; children: React.ReactNode }) {
  const params = useSearchParams();
  const auto = params.get("print") === "1";
  const fired = useRef(false);
  useEffect(() => {
    if (!ready || !auto || fired.current) return;
    fired.current = true;
    const t = setTimeout(() => window.print(), 450);
    return () => clearTimeout(t);
  }, [ready, auto]);
  useEffect(() => {
    if (ready) document.title = `${title} · AURELIA`;
  }, [ready, title]);

  return (
    <div className="min-h-dvh bg-surface-sunken print:bg-white">
      <div className="no-print sticky top-0 z-10 border-b bg-background/95">
        <div className="mx-auto flex h-14 max-w-[52rem] items-center justify-between gap-3 px-4">
          <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
            <Link href={backHref}>
              <ArrowLeft /> {backLabel}
            </Link>
          </Button>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-muted-foreground sm:inline">A4 · choose “Save as PDF” in the print dialog</span>
            <Button size="sm" onClick={() => window.print()} disabled={!ready}>
              <Printer /> Print or save as PDF
            </Button>
          </div>
        </div>
      </div>
      <article className="mx-auto my-8 max-w-[52rem] bg-white px-6 py-10 text-[oklch(0.18_0.02_255)] shadow-(--shadow-raised) sm:px-14 print:my-0 print:max-w-none print:px-0 print:py-0 print:shadow-none">
        <header className="flex items-start justify-between gap-6 border-b border-[oklch(0.86_0.008_85)] pb-5">
          <div className="min-w-0">
            <h1 className="text-[22px] leading-tight font-semibold tracking-[-0.02em] text-balance">{title}</h1>
            {subtitle ? <div className="tnum mt-1.5 text-[12.5px] text-[oklch(0.42_0.018_255)]">{subtitle}</div> : null}
          </div>
          <div className="shrink-0 pt-1 text-[oklch(0.18_0.02_255)]">
            <Wordmark />
          </div>
        </header>
        <div className="pt-6">{children}</div>
        <footer className="mt-10 border-t border-[oklch(0.9_0.006_85)] pt-3 text-[11px] text-[oklch(0.5_0.014_255)]">
          Every number in this document was checked against the filing it came from. Page references point to the source filing.
        </footer>
      </article>
    </div>
  );
}

const TH = "border-b border-[oklch(0.86_0.008_85)] py-1.5 pr-3 text-left text-[11px] font-medium text-[oklch(0.42_0.018_255)]";
const TD = "border-b border-[oklch(0.93_0.006_85)] py-1.5 pr-3 align-top";

export function evidenceRef(e: Evidence) {
  if (e.pdf_index == null) return `${e.doc_label}, ${e.printed_page ?? "exchange row"}`;
  return `${e.doc_label}, ${e.printed_page ? `p. ${e.printed_page}` : `PDF p. ${e.pdf_index}`}`;
}

/** A script card as print sections. */
export function PrintScript({ card }: { card: Pick<ChatScriptCard, "title" | "sections"> }) {
  return (
    <section className="print-avoid-break mt-4">
      <h3 className="text-[14px] font-semibold">{card.title}</h3>
      <dl className="mt-2 space-y-2.5">
        {card.sections.map((s) => (
          <div key={s.heading} className="print-avoid-break grid grid-cols-[8rem_minmax(0,1fr)] gap-4 border-t border-[oklch(0.93_0.006_85)] pt-2.5 max-sm:grid-cols-1 max-sm:gap-1">
            <dt className="text-[12.5px] font-semibold">{s.heading}</dt>
            <dd>
              <ul className="space-y-1">
                {s.lines.map((l, i) => (
                  <li key={i} className="tnum text-[13px] leading-relaxed">
                    {/question/i.test(s.heading) ? `${i + 1}. ` : "– "}
                    {l}
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** One chat card as a print table (no interactive pieces). */
export function PrintCard({ card }: { card: ChatCard }) {
  if (card.kind === "script" && card.sections) return <PrintScript card={card as ChatScriptCard} />;
  const items = Array.isArray(card.items) ? card.items : [];
  if (!items.length) return null;
  let body: React.ReactNode = null;
  if (card.kind === "people") {
    body = (
      <table className="tnum w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <th className={TH}>#</th>
            <th className={TH}>Person</th>
            <th className={TH}>Event</th>
            <th className={`${TH} max-sm:hidden`}>When</th>
            <th className={`${TH} text-right`}>Money</th>
          </tr>
        </thead>
        <tbody>
          {(items as CallItem[]).map((i, n) => (
            <tr key={i.id ?? `${i.event.id}/${i.person.id}`} className="print-avoid-break">
              <td className={`${TD} text-[oklch(0.5_0.014_255)]`}>{n + 1}</td>
              <td className={TD}>
                <span className="font-medium">{properName(i.person.name)}</span>
                {i.person.role ? <span className="block text-[11.5px] text-[oklch(0.42_0.018_255)]">{i.person.role}</span> : null}
              </td>
              <td className={TD}>{shortCompany(i.event.company)}</td>
              <td className={`${TD} text-[11.5px] max-sm:hidden`}>{i.timing.label}</td>
              <td className={`${TD} pr-0 text-right font-semibold whitespace-nowrap`}>
                {i.amount.estimate && i.amount.value_cr !== null ? "≈ " : ""}
                {i.amount.display}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  } else if (card.kind === "events") {
    body = (
      <table className="tnum w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <th className={TH}>Event</th>
            <th className={TH}>Money date</th>
            <th className={`${TH} text-right`}>People</th>
            <th className={`${TH} text-right`}>Cash in hand</th>
          </tr>
        </thead>
        <tbody>
          {(items as EventSummary[]).map((e) => (
            <tr key={e.id}>
              <td className={TD}>
                {shortCompany(e.company)} <span className="text-[oklch(0.42_0.018_255)]">{e.type_label ?? e.type}</span>
              </td>
              <td className={TD}>{e.money_date?.display ?? "—"}</td>
              <td className={`${TD} text-right`}>{e.people_count}</td>
              <td className={`${TD} pr-0 text-right font-semibold`}>{formatCr(e.cash_cr) ?? "Not disclosed"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  } else if (card.kind === "person") {
    const p = items[0] as PersonCard;
    body = (
      <div className="tnum rounded-md border border-[oklch(0.9_0.006_85)] p-3.5 text-[12.5px]">
        <p>
          <span className="font-semibold">{properName(p.person.name)}</span>
          {p.person.role ? `, ${p.person.role}` : ""} · {shortCompany(p.event.company)} · <span className="font-semibold">{p.amount.display}</span>
        </p>
        <p className="mt-1 text-[oklch(0.42_0.018_255)]">
          {p.timing.label} · How sure: {p.confidence.level}
        </p>
        <ul className="mt-2 space-y-1">
          {(p.amounts ?? []).map((a) => (
            <li key={a.key}>
              {a.label}: <span className="font-medium">{a.short ?? a.display}</span>
              {a.working ? <span className="text-[oklch(0.42_0.018_255)]"> ({a.working})</span> : null}
              {a.inputs[0]?.evidence[0] ? <span className="text-[oklch(0.42_0.018_255)]"> · {evidenceRef(a.inputs[0].evidence[0])}</span> : null}
            </li>
          ))}
        </ul>
      </div>
    );
  } else if (card.kind === "calendar") {
    type Row = { date_iso: string; display: string; label: string; event: { id: string; company: string }; total_cr?: number | null };
    body = (
      <table className="tnum w-full border-collapse text-[12.5px]">
        <tbody>
          {(items as Row[]).map((r) => (
            <tr key={`${r.date_iso}-${r.event.id}-${r.label}`}>
              <td className={`${TD} font-medium whitespace-nowrap`}>{r.display}</td>
              <td className={TD}>
                {shortCompany(r.event.company)} · {r.label}
              </td>
              <td className={`${TD} pr-0 text-right font-semibold`}>{formatCr(r.total_cr) ?? "Not disclosed"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  } else if (card.kind === "lineage") {
    type N = { id: string; label: string; detail?: string | null; children?: N[] };
    const walk = (nodes: N[], depth: number): React.ReactNode => (
      <ul className={depth ? "ml-4 border-l border-[oklch(0.9_0.006_85)] pl-3" : ""}>
        {nodes.map((n) => (
          <li key={n.id} className="py-0.5 text-[12px]">
            <span className={depth < 3 ? "font-medium" : ""}>{n.label}</span>
            {n.detail ? <span className="text-[oklch(0.42_0.018_255)]"> · {n.detail}</span> : null}
            {n.children?.length ? walk(n.children, depth + 1) : null}
          </li>
        ))}
      </ul>
    );
    body = walk(items as N[], 0);
  }
  if (!body) return null;
  return (
    <section className="print-avoid-break mt-4">
      <h3 className="mb-1.5 text-[12.5px] font-semibold">{card.title}</h3>
      <div className="overflow-x-auto print:overflow-visible">{body}</div>
    </section>
  );
}
