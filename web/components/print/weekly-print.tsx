"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { properName, shortCompany } from "@/lib/call-script";
import { daysBetween, formatCr, formatDate, formatDateShort } from "@/lib/format";
import { ROLE_LABEL, useSession } from "@/lib/session";
import { rmText } from "@/components/today/use-load";
import type { CallItem, TodayResponse } from "@/lib/types";
import { PrintFrame } from "./print-kit";

const MUTED = "text-[oklch(0.42_0.018_255)]";
const TH = "border-b border-[oklch(0.78_0.01_85)] py-1.5 pr-3 text-left text-[11px] font-medium text-[oklch(0.42_0.018_255)]";
const TD = "border-b border-[oklch(0.93_0.006_85)] py-2 pr-3 align-top";
const LIMIT = 15;
const WINDOW_DAYS = 7;

/** Distance in days between the money date and the as-of date (null when the money has no date). */
function distance(item: CallItem, asOf: string): number | null {
  const d = item.timing.date_iso ? daysBetween(asOf, item.timing.date_iso) : null;
  return d === null ? null : Math.abs(d);
}

/**
 * The 15 people to put in front of the Head of RMs: money dated within a week of the as-of date first (in call
 * order), then, only if fewer than 15 qualify, the people whose money date is nearest to this week.
 */
export function weeklyPicks(items: CallItem[], asOf: string): { picks: CallItem[]; nearest: boolean } {
  const scored = items.map((item, order) => ({ item, order, d: distance(item, asOf) }));
  const inWeek = scored.filter((s) => s.d !== null && s.d <= WINDOW_DAYS);
  if (inWeek.length >= LIMIT) return { picks: inWeek.slice(0, LIMIT).map((s) => s.item), nearest: false };
  const rest = scored
    .filter((s) => !inWeek.includes(s))
    .sort((a, b) => (a.d ?? 1e9) - (b.d ?? 1e9) || a.order - b.order);
  return { picks: [...inWeek, ...rest].slice(0, LIMIT).map((s) => s.item), nearest: inWeek.length < LIMIT };
}

/** "₹6.08 Cr", or "₹4.10 Cr to ₹6.08 Cr" when the filing gives a range; the stored text when not disclosed. */
function range(item: CallItem): string {
  const a = item.amount;
  if (a.value_cr === null) return a.display;
  const high = formatCr(a.value_cr);
  const low = a.low_cr !== null && a.low_cr !== undefined && a.low_cr !== a.value_cr ? formatCr(a.low_cr) : null;
  const text = low ? `${low} to ${high}` : (high ?? a.display);
  return `${a.estimate ? "≈ " : ""}${text}`;
}

/** /weekly: the weekly short list, A4, firm-ready. `?print=1` opens the print dialog (Save as PDF) when it is ready. */
export function WeeklyPrint() {
  const { user, loading } = useSession();
  const [today, setToday] = useState<TodayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .today()
      .then(setToday)
      .catch((e) => setError((e as Error).message || "The short list could not be loaded."));
  }, []);

  if (error)
    return (
      <PrintFrame title="Weekly short list not available" backHref="/today" backLabel="Today" ready={false}>
        <p className="text-sm">{error}</p>
      </PrintFrame>
    );
  if (!today)
    return (
      <PrintFrame title="Preparing the weekly short list…" backHref="/today" backLabel="Today" ready={false}>
        <p className={`text-sm ${MUTED}`}>Loading the call list.</p>
      </PrintFrame>
    );

  const { picks, nearest } = weeklyPicks(today.items, today.as_of);
  const from = new Date(new Date(`${today.as_of}T00:00:00Z`).getTime() - WINDOW_DAYS * 864e5).toISOString().slice(0, 10);
  const prepared = user ? `Prepared for ${user.name}, ${ROLE_LABEL[user.role]}` : null;
  return (
    <PrintFrame
      title="Weekly short list: who just came into money"
      backHref="/today"
      backLabel="Today"
      ready={!loading}
      subtitle={
        <>
          Week of {formatDateShort(from)} to {formatDate(today.as_of)} · {picks.length} people{prepared ? ` · ${prepared}` : ""}
        </>
      }
    >
      {nearest ? (
        <p className={`mb-3 text-[12px] ${MUTED}`}>Fewer than {LIMIT} people have money dated this week, so the nearest dates are added.</p>
      ) : null}
      {picks.length === 0 ? (
        <p className="text-sm">No one is on the call list yet.</p>
      ) : (
        <table className="tnum w-full border-collapse text-[12px]">
          <thead>
            <tr>
              <th className={TH}>#</th>
              <th className={TH}>Person</th>
              <th className={`${TH} text-right`}>Roughly how much</th>
              <th className={TH}>When</th>
              <th className={TH}>How sure</th>
              <th className={TH}>Why call now</th>
            </tr>
          </thead>
          <tbody>
            {picks.map((i, n) => (
              <tr key={i.id ?? `${i.event.id}/${i.person.id}`} className="print-avoid-break">
                <td className={`${TD} text-[oklch(0.5_0.014_255)]`}>{n + 1}</td>
                <td className={TD}>
                  <span className="font-semibold">{properName(i.person.name)}</span>
                  <span className={`block text-[11px] ${MUTED}`}>{i.person.role ?? "Named in the filing"}</span>
                  <span className={`block text-[11px] ${MUTED}`}>
                    {shortCompany(i.event.company)} · {i.event.type_label ?? i.event.type}
                  </span>
                </td>
                <td className={`${TD} text-right font-semibold whitespace-nowrap`}>
                  {range(i)}
                  <span className={`block text-[10.5px] font-normal ${MUTED}`}>{i.amount.kind === "shares" ? "in shares held" : "cash"}</span>
                </td>
                <td className={`${TD} text-[11.5px]`}>{rmText(i.timing.label)}</td>
                <td className={`${TD} text-[11.5px]`}>
                  <span className="font-medium capitalize">{i.confidence.level}</span>
                </td>
                <td className={`${TD} pr-0 text-[11.5px] leading-snug`}>{rmText(i.why || i.brief_first_line)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </PrintFrame>
  );
}
