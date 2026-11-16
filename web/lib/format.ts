/**
 * Number and date formatting in Indian conventions. Pure functions: callers pass the as-of date
 * (from the API) instead of reading the clock during render, so server and client agree.
 */

const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const grouped = new Intl.NumberFormat("en-IN");

/** 92.05 -> "₹92.05 Cr"; 1234.5 -> "₹1,234.50 Cr". null -> null (caller shows "not disclosed"). */
export function formatCr(n: number | null | undefined, opts: { decimals?: number } = {}): string | null {
  if (n === null || n === undefined || Number.isNaN(n)) return null;
  const d = opts.decimals ?? 2;
  // A tiny amount would print as "₹0.00 Cr"; show it in rupees instead.
  if (n > 0 && n < 0.005) return `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.round(n * 1e7))}`;
  const f = new Intl.NumberFormat("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
  return `₹${f.format(n)}\u00a0Cr`;
}

/** Compact crore for KPI tiles: 1520.4 -> "₹1,520 Cr", 92.05 -> "₹92.05 Cr", 0.42 -> "₹0.42 Cr". */
export function formatCrCompact(n: number | null | undefined): string | null {
  if (n === null || n === undefined || Number.isNaN(n)) return null;
  return n >= 1000 ? `₹${inr0.format(n)} Cr` : `₹${inr2.format(n)} Cr`;
}

/** Rupees in full Indian grouping: 12345678 -> "₹1,23,45,678". */
export function formatINR(n: number | null | undefined, opts: { decimals?: number } = {}): string | null {
  if (n === null || n === undefined || Number.isNaN(n)) return null;
  const d = opts.decimals ?? 0;
  return `₹${new Intl.NumberFormat("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n)}`;
}

/** Share counts and plain integers: 3810000 -> "38,10,000". */
export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return grouped.format(n);
}

/** USD for cost displays: 0.00142 -> "$0.0014", 1.2 -> "$1.20". */
export function formatUSD(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  if (n !== 0 && Math.abs(n) < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parseISO(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
}

/** "2026-11-26" -> "26 Nov 2026". */
export function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = parseISO(iso);
  if (!d) return null;
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "2026-11-26" -> "26 Nov". */
export function formatDateShort(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = parseISO(iso);
  if (!d) return null;
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** Whole days from asOf to iso (positive = future). */
export function daysBetween(asOfIso: string, iso: string): number | null {
  const a = parseISO(asOfIso);
  const b = parseISO(iso);
  if (!a || !b) return null;
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

/** Relative to the as-of date: "today", "tomorrow", "in 11 days", "3 days ago", "in 2 months", "8 months ago". */
export function formatRelative(iso: string | null | undefined, asOfIso: string): string | null {
  if (!iso) return null;
  const days = daysBetween(asOfIso, iso);
  if (days === null) return null;
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  const abs = Math.abs(days);
  let span: string;
  if (abs < 45) span = `${abs} days`;
  else if (abs < 365) {
    const m = Math.round(abs / 30.4);
    span = `${m} month${m === 1 ? "" : "s"}`;
  } else {
    const y = Math.round(abs / 365);
    span = `${y} year${y === 1 ? "" : "s"}`;
  }
  return days > 0 ? `in ${span}` : `${span} ago`;
}

export function initials(name: string): string {
  const parts = name
    .replace(/\(.*?\)/g, "")
    .replace(/\b(Prof|Dr|Mr|Mrs|Ms|Shri|Smt)\.?\s+/gi, "")
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0][0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] ?? "" : "";
  return (first + last).toUpperCase();
}

export const EVENT_TYPE_LABEL: Record<string, string> = {
  ipo: "IPO",
  buyback: "Buyback",
  ofs: "Offer for sale",
};
