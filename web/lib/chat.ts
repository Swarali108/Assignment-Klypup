/**
 * Control tower chat client (api/CHAT_CONTRACT.md).
 *
 * POST /api/chat answers with Server-Sent Events. We read it with fetch + ReadableStream (EventSource
 * cannot POST), parse `event:` / `data:` frames, and hand each typed event to the caller.
 * NEXT_PUBLIC_CHAT_MOCK=1 swaps the network for lib/chat-mock.ts, which produces the same bytes.
 */
import { ApiError, apiFetch } from "@/lib/api";

// APP_ENV=production forces the mock off, whatever NEXT_PUBLIC_CHAT_MOCK says (next.config.ts passes APP_ENV through).
export const CHAT_MOCK = process.env.NEXT_PUBLIC_CHAT_MOCK === "1" && !/^prod(uction)?$/i.test(process.env.NEXT_PUBLIC_APP_ENV ?? "");

export type StepStatus = "running" | "done" | "failed" | "skipped";
export type ChatStep = { id: string; label: string; status: StepStatus; model: string | null; cost_usd: number; ms: number; detail: string | null };
export type ClarifyOption = { label: string; value: string };
export type ChatClarify = { question: string; options: ClarifyOption[]; allow_free_text: boolean };
export type EstimateLine = { step: string; model: string | null; calls: number; cost_usd: number; /** Bright Data lookups: worst-case request count (counted, not dollars). */ brightdata_requests?: number };
export type ChatEstimate = {
  action: { kind: "process_event" | "deep_dive" | "research"; title: string; target: string };
  cost_usd_low: number;
  cost_usd_high: number;
  cost_inr_low?: number | null;
  cost_inr_high?: number | null;
  seconds_low: number;
  seconds_high: number;
  breakdown: EstimateLine[];
  basis: string;
  confirm_token: string;
  /** unix seconds from the API (null when this role cannot confirm); the mock sends an ISO string */
  expires_at: number | string | null;
  can_confirm?: boolean;
  blocked_reason?: string | null;
};
export type CardKind = "people" | "events" | "person" | "calendar" | "lineage" | "script";
export type ScriptSection = { heading: string; lines: string[] };
export type ScriptPerson = { event_id: string; person_id: string; name: string };
/** v2 call script card: no `items`; sections carry the script, every number filled by code from the call card. */
export type ChatScriptCard = { kind: "script"; title: string; person: ScriptPerson; sections: ScriptSection[]; items?: unknown[] };
export type ChatCard = { kind: CardKind; title: string; items: unknown[]; total?: number; person?: ScriptPerson; sections?: ScriptSection[] };
export type ModelUse = { model: string; calls: number; cost_usd: number };
export type ChatTokens = { input: number; output: number; cached_input: number };
export type ChatDone = {
  total_cost_usd: number;
  models: ModelUse[];
  seconds: number;
  /** v2 */
  tokens?: ChatTokens;
  saved_usd_by_cache?: number;
};
/** v2: a person or event the conversation is about. */
export type ChatFocus = { kind: "person" | "event"; event_id: string; person_id: string | null; label: string };
/** v2: what the model was given this turn (sent once per turn, before `done`). */
export type ChatContext = {
  prompt_tokens: number;
  cached_tokens: number;
  history_tokens_before: number;
  history_tokens_after: number;
  compressed: boolean;
  turns_kept: number;
  focus: ChatFocus[];
};
/** v2: per-message meta on a stored conversation. */
export type MessageMeta = {
  models?: ModelUse[];
  tokens_in?: number;
  tokens_out?: number;
  cached_in?: number;
  cost_usd?: number;
  context_tokens?: number;
  /** The `context` event exactly as it was streamed (provider figures), when stored. */
  context?: ChatContext;
  /** The model that answered this turn (v3 switcher), when it was not the default. */
  chat_model?: string;
  compressed?: boolean;
  focus?: ChatFocus[];
  seconds?: number;
};

export type ChatEvent =
  | { type: "meta"; data: { conversation_id: string; title: string } }
  | { type: "step"; data: ChatStep }
  | { type: "clarify"; data: ChatClarify }
  | { type: "estimate"; data: ChatEstimate }
  | { type: "text"; data: { delta: string; final?: boolean } }
  | { type: "context"; data: ChatContext }
  | { type: "focus"; data: { focus: ChatFocus[] } }
  | { type: "cards"; data: ChatCard }
  | { type: "done"; data: ChatDone }
  | { type: "error"; data: { message: string } };

export type ChatRequest = {
  conversation_id: string | null;
  message: string;
  confirm_token: string | null;
  choice: string | null;
  /**
   * Client addition to v2 (sent only after the RM edits the focus chip): the focus the RM wants for this turn.
   * `[]` means "talk about no one in particular"; omitted means "keep the server's focus".
   */
  focus?: ChatFocus[];
  /** v3: a model id from GET /api/chat/models, kept by the server for the conversation. */
  model?: string | null;
};

/** v1 sends {id, title, updated_at}; v2 adds the message count and the conversation's total cost. */
export type Conversation = { id: string; title: string; updated_at: string; messages?: number; cost_usd?: number; created_at?: string };
export type StoredMessage = {
  role: "user" | "assistant";
  text: string;
  cards?: ChatCard[];
  steps?: ChatStep[];
  estimate?: ChatEstimate | null;
  created_at?: string;
  /** v2 */
  meta?: MessageMeta | null;
  clarify?: ChatClarify | null;
  /** The server marks the user message a confirm click stored (older threads: only its fixed wording). */
  confirmed?: boolean;
};

/** The "message" a confirm click stores. It is not a question the RM typed. */
export function isConfirmMessage(m: StoredMessage | undefined): boolean {
  return !!m && m.role === "user" && (m.confirmed === true || m.text === "Run the confirmed action");
}
export type StoredConversation = { id: string; title: string; messages: StoredMessage[]; created_at?: string; updated_at?: string };

const KNOWN = new Set(["meta", "step", "clarify", "estimate", "text", "cards", "done", "error", "context", "focus"]);

/** Split an SSE byte stream into typed events. Frames may arrive split across chunks at any byte. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const parse = (frame: string): ChatEvent | null => {
    let type = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith(":")) continue;
      const i = line.indexOf(":");
      const field = i === -1 ? line : line.slice(0, i);
      const value = i === -1 ? "" : line.slice(i + 1).replace(/^ /, "");
      if (field === "event") type = value;
      else if (field === "data") data.push(value);
    }
    if (!data.length || !KNOWN.has(type)) return null;
    try {
      return { type, data: JSON.parse(data.join("\n")) } as ChatEvent;
    } catch {
      return null;
    }
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n?/g, "\n");
      let cut = buffer.indexOf("\n\n");
      while (cut !== -1) {
        const event = parse(buffer.slice(0, cut));
        buffer = buffer.slice(cut + 2);
        if (event) yield event;
        cut = buffer.indexOf("\n\n");
      }
    }
    const tail = buffer.trim() ? parse(buffer) : null;
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

/** Send one turn and stream its events. Errors become a single `error` event in RM words. */
export async function* streamChat(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  let body: ReadableStream<Uint8Array>;
  if (CHAT_MOCK) {
    const { mockChatStream } = await import("@/lib/chat-mock");
    body = mockChatStream(req, signal);
  } else {
    let res: Response;
    try {
      res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(req),
        signal,
      });
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      yield { type: "error", data: { message: "The assistant is not reachable right now. Check the data service and try again." } };
      return;
    }
    if (!res.ok || !res.body) {
      let detail = "";
      try {
        detail = (await res.json())?.detail ?? "";
      } catch {}
      const message =
        res.status === 401
          ? "Your session ended. Sign in again to keep going."
          : res.status === 403
            ? typeof detail === "string" && detail
              ? detail
              : "Your role cannot run this. Ask an admin or a relationship manager."
            : res.status === 404
              ? "The assistant is not switched on in this environment yet."
              : typeof detail === "string" && detail
                ? detail
                : "The assistant could not answer. Please try again.";
      yield { type: "error", data: { message } };
      return;
    }
    body = res.body;
  }
  try {
    yield* readSse(body);
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    yield { type: "error", data: { message: "The answer was cut off. Please ask again." } };
  }
}

/** Token counts for people: 2,400 → "2.4k", 980 → "980", 1,250,000 → "1.25M". */
export function formatTokens(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (n < 1000) return String(Math.round(n));
  if (n < 1_000_000) return `${parseFloat((n / 1000).toFixed(n < 10_000 ? 1 : 0))}k`;
  return `${parseFloat((n / 1_000_000).toFixed(2))}M`;
}

/** Share as a whole percent, or null when there is nothing to divide by. */
export function percent(part: number | null | undefined, whole: number | null | undefined): number | null {
  if (!whole || part === null || part === undefined) return null;
  return Math.round((part / whole) * 100);
}

export const chatApi = {
  async conversations(q?: string): Promise<Conversation[]> {
    if (CHAT_MOCK) return (await import("@/lib/chat-mock")).mockConversations(q);
    try {
      return await apiFetch<Conversation[]>("/chat/conversations", { query: { q: q?.trim() || undefined } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return [];
      throw err;
    }
  },
  async conversation(id: string): Promise<StoredConversation> {
    if (CHAT_MOCK) return (await import("@/lib/chat-mock")).mockConversation(id);
    return apiFetch(`/chat/conversations/${encodeURIComponent(id)}`);
  },
  async remove(id: string): Promise<void> {
    if (CHAT_MOCK) return (await import("@/lib/chat-mock")).mockDelete(id);
    await apiFetch(`/chat/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
};

/** "$0.0031", "$0.02", "$0" — enough digits to show a tiny cost honestly. */
export function formatCost(usd: number | null | undefined): string {
  if (usd === null || usd === undefined || Number.isNaN(usd)) return "—";
  if (usd === 0) return "$0";
  if (usd < 0.01) return `$${parseFloat(usd.toFixed(4))}`;
  if (usd < 1) return `$${parseFloat(usd.toFixed(3))}`;
  return `$${usd.toFixed(2)}`;
}

export function formatSeconds(s: number): string {
  if (s < 1) return `${Math.max(0.1, s).toFixed(1)} s`;
  if (s < 90) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  return `${Math.round(s / 60)} min`;
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : formatSeconds(ms / 1000);
}

/** "openai/gpt-6-luna" → "gpt-6-luna"; null → "Code". */
export function modelLabel(model: string | null | undefined): string {
  if (!model) return "Code";
  return model.split("/").pop() ?? model;
}

/** Epoch milliseconds for an estimate's expiry, or null when there is none. */
export function expiryMs(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const ms = typeof v === "number" ? v * 1000 : Date.parse(v);
  return Number.isFinite(ms) ? ms : null;
}
