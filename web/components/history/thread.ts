import { isConfirmMessage, type ModelUse, type StoredConversation, type StoredMessage } from "@/lib/chat";

/** One question and its answer (a confirm or a clicked option can be an answer with no typed question). */
export type Exchange = { key: string; n: number; question: StoredMessage | null; answer: StoredMessage | null };

export function exchanges(messages: StoredMessage[]): Exchange[] {
  const out: Exchange[] = [];
  let q: StoredMessage | null = null;
  messages.forEach((m, i) => {
    if (m.role === "user") {
      if (isConfirmMessage(m)) return;
      if (q) out.push({ key: `x${i}q`, n: out.length + 1, question: q, answer: null });
      q = m;
    } else {
      out.push({ key: `x${i}`, n: out.length + 1, question: q, answer: m });
      q = null;
    }
  });
  if (q) out.push({ key: "xlast", n: out.length + 1, question: q, answer: null });
  return out;
}

export type ThreadTotals = {
  questions: number;
  answers: number;
  /** answers that carry v2 meta; 0 means "not recorded" (never shown as zero cost) */
  measured: number;
  cost: number;
  tokensIn: number;
  tokensOut: number;
  cachedIn: number;
  compressions: number;
  models: ModelUse[];
  seconds: number;
};

export function totals(c: Pick<StoredConversation, "messages">): ThreadTotals {
  const models = new Map<string, ModelUse>();
  const t: ThreadTotals = { questions: 0, answers: 0, measured: 0, cost: 0, tokensIn: 0, tokensOut: 0, cachedIn: 0, compressions: 0, models: [], seconds: 0 };
  for (const m of c.messages) {
    if (m.role === "user") {
      if (!isConfirmMessage(m)) t.questions += 1;
      continue;
    }
    t.answers += 1;
    const meta = m.meta;
    if (!meta) continue;
    t.measured += 1;
    t.cost += meta.cost_usd ?? 0;
    t.tokensIn += meta.tokens_in ?? 0;
    t.tokensOut += meta.tokens_out ?? 0;
    t.cachedIn += meta.cached_in ?? 0;
    t.seconds += meta.seconds ?? 0;
    if (meta.compressed) t.compressions += 1;
    for (const u of meta.models ?? []) {
      const cur = models.get(u.model) ?? { model: u.model, calls: 0, cost_usd: 0 };
      cur.calls += u.calls;
      cur.cost_usd += u.cost_usd;
      models.set(u.model, cur);
    }
  }
  t.models = [...models.values()].sort((a, b) => b.cost_usd - a.cost_usd);
  return t;
}

/** "3 min ago", "yesterday, 14:05", "12 Nov, 09:40" against the viewer's clock. */
export function when(iso: string | null | undefined, now: number): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const mins = Math.round((now - t) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const d = new Date(t);
  const hm = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (mins < 60 * 12) return `${Math.round(mins / 60)} h ago`;
  const days = Math.floor((now - t) / 864e5);
  if (days < 1) return `today, ${hm}`;
  if (days < 2) return `yesterday, ${hm}`;
  return `${d.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${hm}`;
}
