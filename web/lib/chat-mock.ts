/**
 * Local stand-in for POST /api/chat (NEXT_PUBLIC_CHAT_MOCK=1, default off).
 *
 * It answers from the real data service (/api/today, /api/events, /api/people, /api/calendar, /api/ask) and
 * emits the exact SSE bytes the backend sends (CHAT_CONTRACT v1 + v2), cut into uneven chunks so the stream
 * parser is exercised. v2 behaviour mirrored here: conversation memory with focus entities (a follow-up with no
 * name binds to the focus), clarify options that are the candidates, time windows on money dates, sentence-by-
 * sentence text, a `context` event per turn (stable prefix → prompt caching, compression past a threshold),
 * `focus` events, call-script cards and token totals on `done`.
 *
 * Model names, step timings, token counts and prices are representative, not measured: the real agent reports
 * its own. Conversations persist in localStorage so the history and print pages (new tabs) see them.
 */
import { api, apiFetch } from "@/lib/api";
import { buildCallScript, properName, shortCompany } from "@/lib/call-script";
import { sentences } from "@/lib/chat-text";
import type { CallItem, PersonCard } from "@/lib/types";
import type { ChatCard, ChatClarify, ChatContext, ChatEstimate, ChatFocus, ChatRequest, ChatStep, Conversation, MessageMeta, ModelUse, StoredMessage } from "@/lib/chat";

const LUNA = "openai/gpt-6-luna";
const TERRA = "openai/gpt-6.1-terra";
const HAIKU = "anthropic/claude-haiku-5.5";

/** $ per 1M tokens: input, cached input, output (representative). */
const PRICE: Record<string, [number, number, number]> = {
  [LUNA]: [0.1, 0.025, 0.4],
  [TERRA]: [0.4, 0.1, 1.6],
  [HAIKU]: [0.1, 0.01, 0.5],
};
/** The stable system prefix (byte-identical every turn) and the compression threshold, as in config/chat.py. */
const PREFIX_TOKENS = 1_184;
const COMPRESS_AT = 3_000;
const SUMMARY_TOKENS = 380;
const KEEP_TURNS = 2;

type Pending = "script" | null;
type Stored = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: StoredMessage[];
  /** memory */
  focus: ChatFocus[];
  turnTokens: number[];
  summarised: number;
  pending: Pending;
};

const KEY = "finsight.chat-mock.v2";
const SEEDED = "finsight.chat-mock.v2.seeded";
const store = new Map<string, Stored>();
let loaded = false;

function load() {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) for (const c of JSON.parse(raw) as Stored[]) store.set(c.id, c);
  } catch {}
}
function persist() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify([...store.values()]));
  } catch {}
}

const costOf = (c: Stored) => c.messages.reduce((s, m) => s + (m.meta?.cost_usd ?? 0), 0);

export async function mockConversations(q?: string): Promise<Conversation[]> {
  load();
  await ensureSeed();
  const needle = q?.trim().toLowerCase();
  return [...store.values()]
    .filter((c) => !needle || c.title.toLowerCase().includes(needle) || c.messages.some((m) => m.text.toLowerCase().includes(needle)))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .map((c) => ({ id: c.id, title: c.title, updated_at: c.updated_at, created_at: c.created_at, messages: c.messages.length, cost_usd: Number(costOf(c).toFixed(5)) }));
}

export async function mockConversation(id: string) {
  load();
  await ensureSeed();
  const c = store.get(id);
  if (!c) throw new Error("No such conversation");
  return { id: c.id, title: c.title, created_at: c.created_at, updated_at: c.updated_at, messages: c.messages };
}

export function mockDelete(id: string) {
  load();
  store.delete(id);
  persist();
}

/** GET /api/ops/tokens, computed from the stored conversations. */
export async function mockOpsTokens() {
  load();
  await ensureSeed();
  const by = new Map<string, { model: string; calls: number; input_tokens: number; cached_tokens: number; output_tokens: number; cost_usd: number; saved_usd: number }>();
  let questions = 0;
  let cost = 0;
  let input = 0;
  let cached = 0;
  let compressions = 0;
  let savedTokens = 0;
  for (const c of store.values())
    for (const m of c.messages) {
      const meta = m.meta as (MessageMeta & { usage?: Usage[]; compression_saved?: number }) | null | undefined;
      if (m.role !== "assistant" || !meta) continue;
      questions += 1;
      cost += meta.cost_usd ?? 0;
      input += meta.tokens_in ?? 0;
      cached += meta.cached_in ?? 0;
      if (meta.compressed) compressions += 1;
      savedTokens += meta.compression_saved ?? 0;
      for (const u of meta.usage ?? []) {
        const row = by.get(u.model) ?? { model: u.model, calls: 0, input_tokens: 0, cached_tokens: 0, output_tokens: 0, cost_usd: 0, saved_usd: 0 };
        const [pin, pcached] = PRICE[u.model] ?? [0, 0, 0];
        row.calls += 1;
        row.input_tokens += u.input;
        row.cached_tokens += u.cached;
        row.output_tokens += u.output;
        row.cost_usd += u.cost;
        row.saved_usd += (u.cached * (pin - pcached)) / 1e6;
        by.set(u.model, row);
      }
    }
  const by_model = [...by.values()].map((r) => ({ ...r, cost_usd: Number(r.cost_usd.toFixed(6)), saved_usd: Number(r.saved_usd.toFixed(6)) })).sort((a, b) => b.input_tokens - a.input_tokens);
  return {
    questions,
    avg_cost_usd: questions ? Number((cost / questions).toFixed(6)) : 0,
    cache_hit_rate: input ? Number((cached / input).toFixed(4)) : 0,
    cached_tokens: cached,
    input_tokens: input,
    saved_usd_by_cache: Number(by_model.reduce((s, r) => s + r.saved_usd, 0).toFixed(6)),
    compressions,
    tokens_saved_by_compression: savedTokens,
    total_cost_usd: Number(cost.toFixed(6)),
    by_model,
  };
}

let fast = false;
const sleep = (ms: number, signal?: AbortSignal) =>
  fast
    ? Promise.resolve()
    : new Promise<void>((resolve, reject) => {
        const t = setTimeout(resolve, ms);
        signal?.addEventListener("abort", () => {
          clearTimeout(t);
          reject(new DOMException("Aborted", "AbortError"));
        });
      });

const STOP = new Set(
  "what which who whom whose how much many does do did have has had the a an of in on for to is are was were money cash shares worth get got about tell me show find person people this that with and or from its it only ready script call make write prepare deep dive into more him her them they their please give".split(
    " ",
  ),
);

function nameTokens(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length >= 3 && !STOP.has(t));
}

/** Items whose names share the most tokens with the question (one per person). */
function matchPeople(items: CallItem[], q: string): CallItem[] {
  const tokens = nameTokens(q);
  if (!tokens.length) return [];
  let best = 0;
  let hits: CallItem[] = [];
  for (const item of items) {
    const name = new Set(nameTokens(item.person.name));
    const score = tokens.filter((t) => name.has(t)).length;
    if (score === 0) continue;
    if (score > best) {
      best = score;
      hits = [item];
    } else if (score === best) hits.push(item);
  }
  return hits;
}

function crText(v: number | null | undefined) {
  return v === null || v === undefined ? null : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 })} Cr`;
}

const itemId = (i: CallItem) => i.id ?? `${i.event.id}/${i.person.id}`;
const personFocus = (i: { event: { id: string }; person: { id: string; name: string } }): ChatFocus => ({ kind: "person", event_id: i.event.id, person_id: i.person.id, label: properName(i.person.name) });
const sameFocus = (a: ChatFocus, b: ChatFocus) => a.kind === b.kind && a.event_id === b.event_id && (a.person_id ?? null) === (b.person_id ?? null);

type Emit = (type: string, data: unknown) => Promise<void>;
type Usage = { model: string; input: number; cached: number; output: number; cost: number };

/** Token and cost accounting for one turn. */
class Meter {
  usage: Usage[] = [];
  constructor(public ctx: ChatContext) {}
  call(model: string, extraIn: number, out: number): number {
    const input = this.ctx.prompt_tokens + extraIn;
    const cached = Math.min(input, this.ctx.cached_tokens);
    const [pin, pcached, pout] = PRICE[model] ?? [0, 0, 0];
    const cost = ((input - cached) * pin + cached * pcached + out * pout) / 1e6;
    this.usage.push({ model, input, cached, output: out, cost });
    return Number(cost.toFixed(6));
  }
  get tokens() {
    return {
      input: this.usage.reduce((s, u) => s + u.input, 0),
      output: this.usage.reduce((s, u) => s + u.output, 0),
      cached_input: this.usage.reduce((s, u) => s + u.cached, 0),
    };
  }
  get saved() {
    return this.usage.reduce((s, u) => s + (u.cached * ((PRICE[u.model]?.[0] ?? 0) - (PRICE[u.model]?.[1] ?? 0))) / 1e6, 0);
  }
}

async function runSteps(emit: Emit, signal: AbortSignal | undefined, steps: Omit<ChatStep, "status">[], costs: Map<string, { calls: number; cost: number }>, clock: { ms: number }) {
  for (const s of steps) {
    await emit("step", { ...s, status: "running", ms: 0, cost_usd: 0 });
    await sleep(Math.min(1400, 240 + s.ms * 0.35), signal);
    await emit("step", { ...s, status: "done" });
    clock.ms += s.ms;
    if (s.model) {
      const c = costs.get(s.model) ?? { calls: 0, cost: 0 };
      costs.set(s.model, { calls: c.calls + 1, cost: c.cost + s.cost_usd });
    }
  }
}

/** v2: one sentence at a time (each one passed the number check before it is sent). */
async function streamText(emit: Emit, signal: AbortSignal | undefined, text: string) {
  const parts = sentences(text);
  for (let i = 0; i < parts.length; i++) {
    await sleep(i === 0 ? 120 : 260 + Math.min(420, parts[i].length * 4), signal);
    await emit("text", { delta: parts[i], final: i === parts.length - 1 });
  }
}

function eventKind(e: { type: string; type_label?: string }) {
  return e.type_label ?? (e.type === "ipo" ? "IPO" : e.type === "buyback" ? "buyback" : "offer for sale");
}

function lineageFor(card: PersonCard) {
  const figures = (card.amounts ?? []).map((a) => ({
    id: `fig-${a.key}`,
    kind: "figure",
    label: a.label,
    detail: a.short ?? a.display,
    children: a.inputs.map((input, i) => {
      const ev = input.evidence[0];
      return {
        id: `in-${a.key}-${i}`,
        kind: "filing",
        label: `${input.label}: ${input.value}`,
        detail: ev ? `${ev.doc_label}${ev.printed_page ? ` · p. ${ev.printed_page}` : ` · PDF p. ${ev.pdf_index}`}` : "No page on file",
        evidence: ev ?? null,
      };
    }),
  }));
  const household = (card.household?.members ?? [])
    .filter((m) => !m.id.endsWith(`/${card.person.id}`))
    .map((m) => ({ id: `hh-${m.id}`, kind: "person", label: m.name, detail: m.role ?? "Household", href: `/people/${m.id}` }));
  return [
    {
      id: "root",
      kind: "person",
      label: card.person.name,
      detail: card.person.role ?? undefined,
      children: [
        {
          id: `ev-${card.event.id}`,
          kind: "event",
          label: `${card.event.company} ${eventKind(card.event)}`,
          href: `/events/${encodeURIComponent(card.event.id)}`,
          children: figures,
        },
        ...(household.length ? [{ id: "household", kind: "household", label: card.household?.label ?? "Household", children: household }] : []),
      ],
    },
  ];
}

/** "today / this week / this month / last N days / upcoming", by money date, against the data's as-of date. */
function timeWindow(lower: string, asOf: string): { label: string; from: string; to: string; upcoming: boolean } | null {
  const day = (offset: number) => new Date(new Date(`${asOf}T00:00:00Z`).getTime() + offset * 864e5).toISOString().slice(0, 10);
  const n = lower.match(/(?:last|past)\s+(\d{1,3})\s+days?/);
  if (n) return { label: `in the last ${n[1]} days`, from: day(-Number(n[1])), to: asOf, upcoming: false };
  if (/\btoday\b/.test(lower)) return { label: "today", from: asOf, to: asOf, upcoming: false };
  if (/this week|past week|last week|\bweek\b/.test(lower)) return { label: "this week", from: day(-7), to: asOf, upcoming: false };
  if (/this month|past month|last month|\bmonth\b/.test(lower)) return { label: "this month", from: day(-30), to: asOf, upcoming: false };
  if (/upcoming|coming up|next (?:week|month)|soon/.test(lower)) return { label: "coming up", from: day(1), to: day(45), upcoming: true };
  return null;
}

const daysAgo = (iso: string, asOf: string) => Math.round((Date.parse(`${asOf}T00:00:00Z`) - Date.parse(`${iso}T00:00:00Z`)) / 864e5);

/** Rough token count of a stored turn (text + cards), for the context meter. */
function tokensOf(text: string, cards: number) {
  return Math.ceil(text.length / 3.6) + cards * 360 + 24;
}

/** Build this turn's context: stable prefix + state (summary + focus) + last turns + the new message. */
function contextFor(conv: Stored, message: string): { ctx: ChatContext; savedByCompression: number } {
  const before = conv.turnTokens.reduce((s, t) => s + t, 0) + (conv.summarised ? SUMMARY_TOKENS : 0);
  let compressed = false;
  let saved = 0;
  if (conv.turnTokens.length > KEEP_TURNS && before > COMPRESS_AT) {
    const older = conv.turnTokens.slice(0, conv.turnTokens.length - KEEP_TURNS);
    conv.turnTokens = conv.turnTokens.slice(-KEEP_TURNS);
    conv.summarised += 1;
    compressed = true;
    saved = older.reduce((s, t) => s + t, 0) - (conv.summarised > 1 ? 0 : SUMMARY_TOKENS);
  }
  const after = conv.turnTokens.reduce((s, t) => s + t, 0) + (conv.summarised ? SUMMARY_TOKENS : 0);
  const state = 36 + conv.focus.length * 22;
  const prompt = PREFIX_TOKENS + state + after + Math.ceil(message.length / 3.6) + 8;
  const first = conv.messages.length === 0;
  // The prefix is cached after the first turn; when nothing above the new message changed, the history is too.
  const reuse = first ? 0 : compressed ? PREFIX_TOKENS : PREFIX_TOKENS + state + Math.max(0, after - (conv.turnTokens.at(-1) ?? 0));
  const cached = Math.floor(Math.min(reuse, prompt) / 128) * 128;
  return {
    ctx: { prompt_tokens: prompt, cached_tokens: cached, history_tokens_before: before, history_tokens_after: after, compressed, turns_kept: Math.min(conv.turnTokens.length, KEEP_TURNS), focus: conv.focus },
    savedByCompression: Math.max(0, saved),
  };
}

type Turn = { title: string; clarify?: ChatClarify };

async function scenario(req: ChatRequest, conv: Stored, emit: Emit, signal: AbortSignal | undefined, meter: Meter, clock: { ms: number }): Promise<Turn> {
  const costs = new Map<string, { calls: number; cost: number }>();
  const started = performance.now();
  const q = req.message.trim();
  const lower = q.toLowerCase();
  let title = q.slice(0, 60) || "New conversation";

  const setFocus = async (next: ChatFocus[]) => {
    const changed = next.length !== conv.focus.length || next.some((f, i) => !sameFocus(f, conv.focus[i]));
    conv.focus = next;
    if (changed) await emit("focus", { focus: next });
  };
  const finish = async () => {
    const models: ModelUse[] = [...costs.entries()].map(([model, c]) => ({ model, calls: c.calls, cost_usd: Number(c.cost.toFixed(6)) }));
    await emit("context", { ...meter.ctx, focus: conv.focus } satisfies ChatContext);
    await emit("done", {
      total_cost_usd: Number(models.reduce((s, m) => s + m.cost_usd, 0).toFixed(6)),
      models,
      seconds: fast ? Number((clock.ms / 1000).toFixed(1)) : Number(((performance.now() - started) / 1000).toFixed(1)),
      tokens: meter.tokens,
      saved_usd_by_cache: Number(meter.saved.toFixed(6)),
    });
  };
  const understand = (detail: string, model: string | null = LUNA): Omit<ChatStep, "status"> => ({
    id: "understand",
    label: "Understanding your question",
    model,
    cost_usd: model ? meter.call(model, 0, 48) : 0,
    ms: model ? 620 : 40,
    detail,
  });
  const verify = (n: number): Omit<ChatStep, "status"> => ({ id: "verify", label: "Checking every number", model: null, cost_usd: 0, ms: 85, detail: `${n} figures matched to the data; nothing removed` });
  const write = (out = 150): Omit<ChatStep, "status"> => ({ id: "write", label: "Writing the answer", model: TERRA, cost_usd: meter.call(TERRA, 420, out), ms: 1850, detail: null });
  const memory = (detail: string): Omit<ChatStep, "status"> => ({ id: "memory", label: "Remembering the conversation", model: null, cost_usd: 0, ms: 30, detail });

  // Compression is a cheap-model call of its own, recorded as a step.
  if (meter.ctx.compressed) {
    await runSteps(
      emit,
      signal,
      [
        {
          id: "compress",
          label: "Summarising earlier turns",
          model: LUNA,
          cost_usd: meter.call(LUNA, meter.ctx.history_tokens_before - meter.ctx.prompt_tokens + 200, 260),
          ms: 540,
          detail: `${meter.ctx.history_tokens_before.toLocaleString("en-IN")} → ${meter.ctx.history_tokens_after.toLocaleString("en-IN")} tokens; no new numbers`,
        },
      ],
      costs,
      clock,
    );
  }

  const [today, events] = await Promise.all([api.today(), api.events()]);
  const asOf = today.as_of;
  const byId = (id: string) => today.items.find((i) => itemId(i) === id) ?? null;
  const focusItems = conv.focus.filter((f) => f.kind === "person").map((f) => byId(`${f.event_id}/${f.person_id}`)).filter((x): x is CallItem => !!x);

  /** One person's call card answer (also the end of a confirmed deep dive). */
  const personAnswer = async (item: CallItem, deep = false) => {
    const card = await api.person(item.event.id, item.person.id);
    const figures = card.amounts.reduce((n, a) => n + a.inputs.length, 0);
    await runSteps(
      emit,
      signal,
      deep
        ? [
            { id: "read", label: `Reading ${shortCompany(card.event.company)} filings again`, model: HAIKU, cost_usd: meter.call(HAIKU, 2600, 420), ms: 2300, detail: `Seller table, holdings and lock-in pages for ${properName(card.person.name)}` },
            { id: "links", label: "Looking for family and related holdings", model: null, cost_usd: 0, ms: 380, detail: card.household ? `${card.household.members.length} in the ${card.household.label}` : "No family link found" },
            verify(figures),
            write(220),
          ]
        : [{ id: "read", label: `Reading ${shortCompany(card.event.company)} filings`, model: null, cost_usd: 0, ms: 260, detail: `${card.amounts.length} figures with their pages` }, verify(figures), write()],
      costs,
      clock,
    );
    await setFocus([personFocus(card)]);
    const lines = [
      `**${properName(card.person.name)}** (${card.person.role ?? "named in the filing"}, ${shortCompany(card.event.company)} ${eventKind(card.event)}): ${card.amount.display}${card.amount.estimate ? " (estimate)" : ""}, ${card.tier_label.toLowerCase()}.`,
      card.timing.label ? `Timing: ${card.timing.label}.` : "",
      card.confidence?.reason ? `How sure: ${card.confidence.level}. ${card.confidence.reason}.` : "",
      deep && card.household && card.household.members.length > 1 ? `Family: the ${card.household.label} has ${card.household.members.length} people on the register; plan the call with them in mind.` : "",
    ];
    await streamText(emit, signal, lines.filter(Boolean).join("\n\n"));
    await emit("cards", { kind: "person", title: "Call card", items: [card] } satisfies ChatCard);
    await emit("cards", { kind: "lineage", title: "Where every number comes from", items: lineageFor(card) } satisfies ChatCard);
    return properName(card.person.name);
  };

  /** A call script for one person, every number from the call card. */
  const scriptAnswer = async (item: CallItem) => {
    const card = await api.person(item.event.id, item.person.id);
    await runSteps(
      emit,
      signal,
      [
        { id: "card", label: `Opening ${properName(card.person.name)}’s call card`, model: null, cost_usd: 0, ms: 140, detail: `${card.amounts.length} figures, timing and family links` },
        { id: "script", label: "Writing the call script", model: TERRA, cost_usd: meter.call(TERRA, 900, 380), ms: 2100, detail: "Opening, why now, three questions, objections, next step" },
        verify(card.amounts.reduce((n, a) => n + a.inputs.length, 0)),
      ],
      costs,
      clock,
    );
    await setFocus([personFocus(card)]);
    conv.pending = null;
    const name = properName(card.person.name);
    await streamText(emit, signal, `Here is a call script for **${name}**. Every number in it is filled from the call card, not written by the model. Read the "why now" line first: it is the reason for calling today.`);
    await emit("cards", buildCallScript(card) as unknown as ChatCard);
    return `Call script: ${name}`;
  };

  // ---- a confirmed, paid action ----
  if (req.confirm_token) {
    const cut = req.confirm_token.indexOf(":");
    const kind = req.confirm_token.slice(0, cut);
    const target = req.confirm_token.slice(cut + 1);
    if (kind === "deep") {
      const item = byId(target);
      if (item) {
        const name = await personAnswer(item, true);
        await finish();
        return { title: `Deep dive: ${name}` };
      }
    }
    const event = events.events.find((e) => e.id === target);
    if (!event) {
      await runSteps(emit, signal, [{ id: "fetch", label: "Fetching the filing", model: null, cost_usd: 0, ms: 900, detail: null }], costs, clock);
      await emit("step", { id: "fetch", label: "Fetching the filing", status: "failed", model: null, cost_usd: 0, ms: 900, detail: "Links are not fetched in this preview" });
      await emit("error", { message: "This preview cannot fetch new links. Pick one of the listed filings to see a full run." });
      await finish();
      return { title: "Process a new filing" };
    }
    title = `Re-check ${shortCompany(event.company)}`;
    await runSteps(
      emit,
      signal,
      [
        { id: "fetch", label: `Fetching ${shortCompany(event.company)} filings`, model: null, cost_usd: 0, ms: 420, detail: `${event.docs.length} documents, already on file` },
        { id: "locate", label: "Finding the pages that matter", model: null, cost_usd: 0, ms: 610, detail: "Seller table, holdings, lock-in, prices" },
        { id: "read", label: "Reading the seller and holding tables", model: HAIKU, cost_usd: 0, ms: 380, detail: "Every page was read before: answers reused at no cost" },
        { id: "verify", label: "Checking every number on its page", model: null, cost_usd: 0, ms: 540, detail: "Quotes found on the cited pages" },
        { id: "rank", label: "Ranking who to call", model: null, cost_usd: 0, ms: 120, detail: null },
      ],
      costs,
      clock,
    );
    const people = today.items.filter((i) => i.event.id === event.id);
    const cash = crText(event.cash_cr);
    await setFocus([{ kind: "event", event_id: event.id, person_id: null, label: event.company }]);
    await streamText(
      emit,
      signal,
      `Done. **${shortCompany(event.company)}** has ${event.people_count} ${event.people_count === 1 ? "person" : "people"} to call${cash ? `, with ${cash} cash in hand` : ""}. ` +
        `This repeat run reused every page already read, so it cost nothing extra.`,
    );
    await emit("cards", { kind: "events", title: "Event", items: [event] } satisfies ChatCard);
    if (people.length) await emit("cards", { kind: "people", title: `Who to call at ${shortCompany(event.company)}`, items: people.slice(0, 5) } satisfies ChatCard);
    await finish();
    return { title };
  }

  // ---- process a filing: clarify which, then estimate ----
  const link = q.match(/https?:\/\/\S+/)?.[0];
  if (req.choice?.startsWith("process:") || link || /process|new ipo|from a link|run .*filing/.test(lower)) {
    await runSteps(emit, signal, [understand("You want a new event processed: that reads filings and costs money")], costs, clock);
    const target = req.choice?.startsWith("process:") ? req.choice.slice(8) : null;
    const event = target ? events.events.find((e) => e.id === target) : null;
    if (!link && !event) {
      await runSteps(emit, signal, [{ id: "clarify", label: "Asking a quick question", model: null, cost_usd: 0, ms: 30, detail: null }], costs, clock);
      const ipos = events.events.filter((e) => e.type === "ipo" && e.status === "ready").slice(0, 3);
      const clarify: ChatClarify = {
        question: "Which filing should I process? Paste the prospectus link, or pick a recent one to re-check.",
        options: ipos.map((e) => ({ label: `Re-check ${shortCompany(e.company)}`, value: `process:${e.id}` })),
        allow_free_text: true,
      };
      await emit("clarify", clarify);
      await finish();
      return { title: "Process a new IPO", clarify };
    }
    const estimate: ChatEstimate = event
      ? {
          action: { kind: "process_event", title: `Re-check ${shortCompany(event.company)} ${eventKind(event)}`, target: event.id },
          cost_usd_low: 0,
          cost_usd_high: 0.002,
          seconds_low: 4,
          seconds_high: 20,
          breakdown: [
            { step: "Fetch the filings", model: null, calls: 0, cost_usd: 0 },
            { step: "Find the pages that matter", model: null, calls: 0, cost_usd: 0 },
            { step: "Read the seller and holding tables", model: HAIKU, calls: 12, cost_usd: 0.0015 },
            { step: "Check every number on its page", model: null, calls: 0, cost_usd: 0 },
            { step: "Write the call briefs", model: HAIKU, calls: 6, cost_usd: 0.0005 },
          ],
          basis: "Pages already read are reused, so a repeat run costs close to nothing.",
          confirm_token: `confirm:${event.id}`,
          expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
        }
      : {
          action: { kind: "process_event", title: "Process a new filing", target: link ?? "" },
          cost_usd_low: 0.012,
          cost_usd_high: 0.034,
          seconds_low: 70,
          seconds_high: 150,
          breakdown: [
            { step: "Fetch the filings", model: null, calls: 0, cost_usd: 0 },
            { step: "Find the pages that matter", model: null, calls: 0, cost_usd: 0 },
            { step: "Read the seller and holding tables", model: HAIKU, calls: 14, cost_usd: 0.024 },
            { step: "Check every number on its page", model: null, calls: 0, cost_usd: 0 },
            { step: "Write the call briefs", model: HAIKU, calls: 8, cost_usd: 0.007 },
          ],
          basis: "Measured from earlier first runs of the same steps on other IPO prospectuses.",
          confirm_token: `confirm:link`,
          expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
        };
    await runSteps(emit, signal, [{ id: "estimate", label: "Estimating the cost", model: null, cost_usd: 0, ms: 60, detail: "From measured history per step" }], costs, clock);
    await emit("estimate", estimate);
    await finish();
    return { title: estimate.action.title };
  }

  // ---- who: a clicked candidate, a name in the message, or the conversation's focus ----
  const chosen = req.choice?.startsWith("person:") ? byId(req.choice.slice(7)) : null;
  const named = chosen ? [chosen] : matchPeople(today.items, q);
  const lastAnswer = [...conv.messages].reverse().find((m) => m.role === "assistant");
  const lastWasScript = !!lastAnswer?.cards?.some((c) => c.kind === "script");
  const wantsScript = conv.pending === "script" || (lastWasScript && named.length === 1 && !/money|how much|deep/.test(lower)) || /script|talking points|what (?:should|do) i say|prep(?:are)? (?:me )?for the call|ready me/.test(lower);
  const wantsDeep = /deep dive|dig (?:in|into)|research|look deeper/.test(lower);
  const pronoun = /\b(him|her|them|they|their|this person|that person|the same|again)\b/.test(lower);
  const wantsPerson = named.length > 0 && (!!chosen || /money does|how much|who is|tell me about|have\??$|about|only|^[a-z\s.]+$/.test(lower));

  // Resolve against the focus when the message names no one.
  const resolve = async (why: string): Promise<CallItem | "asked"> => {
    if (named.length === 1) return named[0];
    const candidates = named.length > 1 ? named : focusItems;
    if (candidates.length === 1) {
      await runSteps(emit, signal, [memory(`“${why}” has no name: using the person this conversation is about, ${properName(candidates[0].person.name)}`)], costs, clock);
      return candidates[0];
    }
    // Two or more fit, or no one yet: ask, offering the candidates themselves.
    const pool = candidates.length ? candidates : today.items.filter((i) => i.tier === "cash_now").slice(0, 4);
    await runSteps(emit, signal, [{ id: "clarify", label: "Asking a quick question", model: null, cost_usd: 0, ms: 25, detail: candidates.length ? `${candidates.length} people fit` : "No one named yet in this conversation" }], costs, clock);
    const clarify: ChatClarify = {
      question: candidates.length ? `Which of these ${candidates.length} is the call for?` : wantsScript ? "Who is the call for? Here are the people with cash in hand right now." : "Who do you mean?",
      options: pool.slice(0, 6).map((m) => ({ label: `${properName(m.person.name)} · ${shortCompany(m.event.company)}`, value: `person:${itemId(m)}` })),
      allow_free_text: true,
    };
    await emit("clarify", clarify);
    lastClarify = clarify;
    return "asked";
  };
  let lastClarify: ChatClarify | undefined;

  if (wantsScript && (named.length || conv.focus.length || /script|call/.test(lower) || conv.pending === "script")) {
    await runSteps(emit, signal, [understand("A call script for one person", named.length === 1 || chosen ? null : LUNA)], costs, clock);
    const who = await resolve(q);
    if (who === "asked") {
      conv.pending = "script";
      await finish();
      return { title: "Call script", clarify: lastClarify };
    }
    const t = await scriptAnswer(who);
    await finish();
    return { title: t };
  }

  if (wantsDeep && (named.length || conv.focus.length)) {
    await runSteps(emit, signal, [understand("A deeper read of one person’s filings: that costs money")], costs, clock);
    const who = await resolve(q);
    if (who === "asked") {
      await finish();
      return { title: "Deep dive", clarify: lastClarify };
    }
    await setFocus([personFocus(who)]);
    const estimate: ChatEstimate = {
      action: { kind: "deep_dive", title: `Deep dive on ${properName(who.person.name)}`, target: itemId(who) },
      cost_usd_low: 0.004,
      cost_usd_high: 0.009,
      seconds_low: 8,
      seconds_high: 25,
      breakdown: [
        { step: "Re-read the seller, holding and lock-in pages", model: HAIKU, calls: 3, cost_usd: 0.0042 },
        { step: "Look for family and related holdings", model: null, calls: 0, cost_usd: 0 },
        { step: "Check every number on its page", model: null, calls: 0, cost_usd: 0 },
        { step: "Write the deep dive", model: TERRA, calls: 1, cost_usd: 0.0021 },
      ],
      basis: "Measured from earlier deep dives on the same kind of filing.",
      confirm_token: `deep:${itemId(who)}`,
      expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    };
    await runSteps(emit, signal, [{ id: "estimate", label: "Estimating the cost", model: null, cost_usd: 0, ms: 60, detail: "From measured history per step" }], costs, clock);
    await emit("estimate", estimate);
    await finish();
    return { title: `Deep dive on ${properName(who.person.name)}` };
  }

  if (wantsPerson || (pronoun && focusItems.length)) {
    await runSteps(
      emit,
      signal,
      [
        understand("A question about one person", chosen ? null : LUNA),
        { id: "search", label: `Checking ${events.count} events`, model: null, cost_usd: 0, ms: 140, detail: named.length ? `${named.length} ${named.length === 1 ? "person matches" : "people match"}` : "Following up on the person in focus" },
      ],
      costs,
      clock,
    );
    if (named.length > 1) {
      const surname = nameTokens(q).find((t) => named.every((m) => nameTokens(m.person.name).includes(t))) ?? "that name";
      await runSteps(emit, signal, [{ id: "clarify", label: "Asking a quick question", model: null, cost_usd: 0, ms: 25, detail: `${named.length} people fit` }], costs, clock);
      const clarify: ChatClarify = {
        question: `${named.length} people match “${surname[0].toUpperCase()}${surname.slice(1)}”. Which one do you mean?`,
        options: named.slice(0, 6).map((m) => ({ label: `${properName(m.person.name)} · ${shortCompany(m.event.company)}`, value: `person:${itemId(m)}` })),
        allow_free_text: false,
      };
      await emit("clarify", clarify);
      await finish();
      return { title: `Who is ${surname}?`, clarify };
    }
    const item = named[0] ?? focusItems[0];
    const name = await personAnswer(item);
    await finish();
    return { title: name };
  }

  // ---- a time window: by money date ----
  const win = timeWindow(lower, asOf);
  if (win && /money|paid|cash|who|event|listing|unlock/.test(lower)) {
    const withPeople = events.events.filter((e) => e.status === "ready" && e.people_count > 0 && e.money_date?.date_iso);
    const inWindow = withPeople.filter((e) => e.money_date!.date_iso! >= win.from && e.money_date!.date_iso! <= win.to);
    const ids = new Set(inWindow.map((e) => e.id));
    const people = today.items.filter((i) => ids.has(i.event.id));
    await runSteps(
      emit,
      signal,
      [
        understand(`Money dated ${win.label} (${win.from === win.to ? win.from : `${win.from} to ${win.to}`}), by the date the money arrives`, null),
        { id: "search", label: `Checking ${events.count} events`, model: null, cost_usd: 0, ms: 160, detail: `${inWindow.length} with money dated ${win.label}` },
        verify(people.length + inWindow.length),
        write(),
      ],
      costs,
      clock,
    );
    if (inWindow.length) {
      const total = inWindow.reduce((s, e) => s + (e.cash_cr ?? 0), 0);
      await streamText(
        emit,
        signal,
        `${inWindow.length} ${inWindow.length === 1 ? "event has" : "events have"} money dated ${win.label}: ${inWindow.map((e) => shortCompany(e.company)).join(", ")}. ` +
          `${people.length} ${people.length === 1 ? "person is" : "people are"} worth a call${total ? `, with ${crText(total)} in known cash between them` : ""}. The list is ranked by cash in hand.`,
      );
      if (people.length) await emit("cards", { kind: "people", title: `Money ${win.label}`, items: people.slice(0, 6) } satisfies ChatCard);
      await emit("cards", { kind: "events", title: `Events ${win.label}`, items: inWindow.slice(0, 4) } satisfies ChatCard);
    } else if (!win.upcoming) {
      // Nothing in the window: say so plainly, then the nearest earlier results.
      const nearest = withPeople.filter((e) => e.money_date!.date_iso! < win.from).sort((a, b) => b.money_date!.date_iso!.localeCompare(a.money_date!.date_iso!)).slice(0, 3);
      const ages = nearest.map((e) => daysAgo(e.money_date!.date_iso!, asOf));
      const nIds = new Set(nearest.map((e) => e.id));
      const nPeople = today.items.filter((i) => nIds.has(i.event.id));
      await streamText(
        emit,
        signal,
        nearest.length
          ? `No one came into money ${win.label}. The latest were ${Math.min(...ages)}–${Math.max(...ages)} days ago: ${nearest.map((e) => shortCompany(e.company)).join(", ")}. ` +
              `${nPeople.length} ${nPeople.length === 1 ? "person" : "people"} from those are below, ranked by cash in hand.`
          : `No one came into money ${win.label}, and nothing earlier is on file.`,
      );
      if (nPeople.length) await emit("cards", { kind: "people", title: "Nearest: the latest money dates", items: nPeople.slice(0, 6) } satisfies ChatCard);
    } else {
      const cal = await apiFetch<{ items: unknown[] }>("/calendar", { query: { from: win.from } });
      await streamText(emit, signal, `Nothing is dated ${win.label} yet. The next money dates on file are on the calendar below.`);
      await emit("cards", { kind: "calendar", title: "Coming up", items: cal.items.slice(0, 6) } satisfies ChatCard);
    }
    await finish();
    return { title: `Who came into money ${win.label}` };
  }

  // ---- a cash threshold ----
  const threshold = lower.match(/(?:above|over|more than|>)\s*₹?\s*(\d+(?:\.\d+)?)\s*(?:cr|crore)?/);
  if (threshold || /cash in hand/.test(lower)) {
    const min = threshold ? Number(threshold[1]) : 0;
    const people = today.items.filter((i) => i.tier === "cash_now" && (i.amount.value_cr ?? 0) >= min);
    await runSteps(
      emit,
      signal,
      [
        understand(`Cash in hand${min ? ` of at least ₹${min} Cr` : ""}: read by rules, no model needed`, null),
        { id: "search", label: `Checking ${today.count} people`, model: null, cost_usd: 0, ms: 90, detail: `${people.length} match` },
        verify(people.length),
        write(),
      ],
      costs,
      clock,
    );
    const total = people.reduce((s, i) => s + (i.amount.value_cr ?? 0), 0);
    await streamText(
      emit,
      signal,
      people.length
        ? `${people.length} ${people.length === 1 ? "person has" : "people have"} cash in hand${min ? ` above ₹${min} Cr` : ""}, ${crText(total)} together. ` +
            `The largest is **${properName(people[0].person.name)}** (${shortCompany(people[0].event.company)}) with ${people[0].amount.display}.`
        : `No one has cash in hand above ₹${min} Cr right now. Try a lower amount.`,
    );
    if (people.length) await emit("cards", { kind: "people", title: `Cash in hand${min ? ` above ₹${min} Cr` : ""}`, items: people.slice(0, 8) } satisfies ChatCard);
    await finish();
    return { title: `Cash in hand${min ? ` above ₹${min} Cr` : ""}` };
  }

  // ---- anything else: the existing $0 search ----
  await runSteps(emit, signal, [understand("A search across the call list")], costs, clock);
  let people: CallItem[] = [];
  let explanation = "";
  try {
    const answer = await api.ask(q);
    people = answer.people;
    explanation = answer.explanation;
  } catch {
    people = matchPeople(today.items, q);
  }
  await runSteps(emit, signal, [{ id: "search", label: `Checking ${today.count} people`, model: null, cost_usd: 0, ms: 120, detail: `${people.length} match` }, verify(people.length), write()], costs, clock);
  await streamText(
    emit,
    signal,
    people.length
      ? `${explanation ? `${explanation}. ` : ""}${people.length} ${people.length === 1 ? "person matches" : "people match"}; the list is ranked by money in hand.`
      : "I could not find anyone for that. Try a name, a company, or an amount such as “cash in hand above ₹50 Cr”.",
  );
  if (people.length) await emit("cards", { kind: "people", title: "Matches", items: people.slice(0, 8) } satisfies ChatCard);
  await finish();
  return { title };
}

/** Run one turn against the store; `emit` receives every SSE event. */
async function runTurn(req: ChatRequest, emit: Emit, signal?: AbortSignal, at?: string) {
  load();
  const now = at ?? new Date().toISOString();
  const id = req.conversation_id && store.has(req.conversation_id) ? req.conversation_id : (req.conversation_id ?? `mock-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`);
  const existing = store.get(id);
  const conv: Stored = existing ?? { id, title: "", created_at: now, updated_at: now, messages: [], focus: [], turnTokens: [], summarised: 0, pending: null };
  if (req.focus) conv.focus = req.focus;
  const userText = req.message.trim();
  const { ctx, savedByCompression } = contextFor(conv, userText);
  const meter = new Meter(ctx);
  const clock = { ms: 0 };
  const assistant: StoredMessage = { role: "assistant", text: "", cards: [], steps: [], estimate: null, created_at: now };
  let done: { total_cost_usd: number; models: ModelUse[]; seconds: number } | null = null;

  const record: Emit = async (type, data) => {
    if (type === "text") assistant.text += (data as { delta: string }).delta;
    if (type === "cards") assistant.cards!.push(data as ChatCard);
    if (type === "estimate") assistant.estimate = data as ChatEstimate;
    if (type === "clarify") assistant.clarify = data as ChatClarify;
    if (type === "done") done = data as typeof done;
    if (type === "step") {
      const s = data as ChatStep;
      const i = assistant.steps!.findIndex((x) => x.id === s.id);
      if (i === -1) assistant.steps!.push(s);
      else assistant.steps![i] = s;
    }
    await emit(type, data);
  };

  const title0 = userText.slice(0, 60) || (req.choice ? "Follow-up" : "New conversation");
  await emit("meta", { conversation_id: id, title: existing?.title || title0 });
  const turn = await scenario(req, conv, record, signal, meter, clock);
  if (!existing) conv.title = turn.title;
  if (assistant.clarify) assistant.text = assistant.clarify.question;
  const shown = userText || (req.confirm_token ? "Confirmed" : req.choice ? "Picked an option" : "");
  if (shown) conv.messages.push({ role: "user", text: shown, created_at: now });
  const d = done as { total_cost_usd: number; models: ModelUse[]; seconds: number } | null;
  assistant.meta = {
    models: d?.models ?? [],
    tokens_in: meter.tokens.input,
    tokens_out: meter.tokens.output,
    cached_in: meter.tokens.cached_input,
    cost_usd: d?.total_cost_usd ?? 0,
    context_tokens: ctx.prompt_tokens,
    compressed: ctx.compressed,
    focus: conv.focus,
    seconds: d?.seconds ?? 0,
    // mock-only bookkeeping for /api/ops/tokens
    ...({ usage: meter.usage, compression_saved: savedByCompression } as object),
  };
  conv.messages.push(assistant);
  conv.turnTokens.push(tokensOf(`${shown} ${assistant.text}`, assistant.cards?.length ?? 0));
  conv.updated_at = now;
  store.set(id, conv);
  persist();
  return id;
}

/** A ReadableStream of SSE bytes for one turn, cut into uneven chunks. */
export function mockChatStream(req: ChatRequest, signal?: AbortSignal): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      let carry = "";
      const flush = (all: boolean) => {
        while (carry.length > (all ? 0 : 24)) {
          const n = all ? carry.length : 7 + Math.floor(Math.random() * 40);
          controller.enqueue(enc.encode(carry.slice(0, n)));
          carry = carry.slice(n);
        }
      };
      const emit: Emit = async (type, data) => {
        if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
        carry += `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
        flush(false);
        if (type === "done" || type === "error" || type === "clarify" || type === "text") flush(true);
        await sleep(type === "step" ? 60 : 0, signal);
      };
      try {
        await ensureSeed();
        await runTurn(req, emit, signal);
        flush(true);
        controller.close();
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          controller.close();
          return;
        }
        carry += `event: error\ndata: ${JSON.stringify({ message: "The data service did not answer. Start it and ask again." })}\n\n`;
        flush(true);
        controller.close();
      }
    },
  });
}

/**
 * Preview seed, built from live data (no names in code): the owner's transcript as it should now go
 * (this week → nearest results; a confirmed deep dive on the top person; "ready me a script for the call"
 * binds to the focus), a longer thread that crosses the compression threshold, and a clarify thread.
 */
let seeding: Promise<void> | null = null;
function ensureSeed(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  load();
  if (seeding) return seeding;
  if (store.size || window.localStorage.getItem(SEEDED)) return Promise.resolve();
  seeding = (async () => {
    fast = true;
    try {
      const today = await api.today();
      const cash = today.items.filter((i) => i.tier === "cash_now");
      const top = cash[0] ?? today.items[0];
      const second = cash.find((i) => i.event.id !== top?.event.id) ?? today.items[1];
      if (!top) return;
      const nop: Emit = async () => {};
      const base = Date.now() - 3 * 864e5;
      let tick = 0;
      const at = () => new Date(base + (tick += 7 * 60_000)).toISOString();
      const say = async (id: string | null, message: string, extra: Partial<ChatRequest> = {}) => runTurn({ conversation_id: id, message, confirm_token: null, choice: null, ...extra }, nop, undefined, at());

      const first = properName(top.person.name).split(" ")[0].toLowerCase();
      let a = await say(null, "Cash in hand above ₹50 Cr");
      a = await say(a, `What money does ${properName(second.person.name)} have?`);
      await say(a, "Who came into money this month?");
      await say(a, "Cash in hand above ₹200 Cr");
      await say(a, `Tell me about ${properName(top.person.name)}`);
      await say(a, "Ready me a script for the call");
      tick += 600 * 60_000;
      const c = await say(null, "Process a new IPO from a link");
      void c;
      tick += 300 * 60_000;
      let b = await say(null, "Who came into money this week?");
      b = await say(b, `Deep dive on ${properName(top.person.name)}`);
      await say(b, "", { confirm_token: `deep:${itemId(top)}` });
      await say(b, "ready me a script for the call");
      tick += 90 * 60_000;
      const d = await say(null, "ready me a script for the call");
      await say(d, `its about the ${first} only`);
      window.localStorage.setItem(SEEDED, "1");
    } catch {
      // Data service down: no seed; the pages show their empty states.
    } finally {
      fast = false;
      persist();
    }
  })();
  return seeding;
}
