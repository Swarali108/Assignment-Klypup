"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "@/lib/session";
import {
  chatApi,
  streamChat,
  type ChatCard,
  type ChatClarify,
  type ChatContext,
  type ChatDone,
  type ChatFocus,
  type ChatEstimate,
  type ChatEvent,
  type ChatStep,
  type Conversation,
  type MessageMeta,
  type StoredMessage,
  isConfirmMessage,
} from "@/lib/chat";
import { joinDelta } from "@/lib/chat-text";

export type UserTurn = { kind: "user"; id: string; text: string };
export type AssistantTurn = {
  kind: "assistant";
  id: string;
  steps: ChatStep[];
  clarify: ChatClarify | null;
  answered: string | null;
  estimate: ChatEstimate | null;
  estimateState: "open" | "confirmed" | "cancelled";
  text: string;
  cards: ChatCard[];
  done: ChatDone | null;
  /** v2: what the model was given this turn. */
  context: ChatContext | null;
  /** v2: stored per-message meta (reopened conversations). */
  meta: MessageMeta | null;
  error: string | null;
  streaming: boolean;
  note?: string;
};
export type Turn = UserTurn | AssistantTurn;

type SendInput = {
  message: string;
  choice?: string | null;
  confirmToken?: string | null;
  display?: string | null;
  /** Called once, when the first step of the turn arrives: the server accepted the request and started. A rejected confirm never gets here. */
  onStarted?: () => void;
};

type Ctx = {
  conversations: Conversation[] | null;
  conversationsError: boolean;
  activeId: string | null;
  title: string | null;
  turns: Turn[];
  busy: boolean;
  loading: boolean;
  send: (input: SendInput) => void;
  stop: () => void;
  open: (id: string) => Promise<void>;
  newChat: () => void;
  remove: (id: string) => Promise<void>;
  /** Mark a turn's clarify as answered / estimate as cancelled, locally. */
  patchTurn: (id: string, patch: Partial<AssistantTurn>) => void;
  refresh: () => void;
  /** v2: who the conversation is about right now. */
  focus: ChatFocus[];
  /** The RM removed someone from the focus chip: the next turn sends the edited focus. */
  dropFocus: (f: ChatFocus) => void;
  /** v2: the latest turn's context, and how many times older turns were summarised in this conversation. */
  context: ChatContext | null;
  compressions: number;
  /** v3: the model chosen for this conversation (null = the defaults). */
  model: string | null;
  setModel: (id: string | null) => void;
};
const ChatCtx = createContext<Ctx | null>(null);

let seq = 0;
const nid = () => `t${Date.now().toString(36)}${(seq++).toString(36)}`;

function blankAssistant(): AssistantTurn {
  return {
    kind: "assistant",
    id: nid(),
    steps: [],
    clarify: null,
    answered: null,
    estimate: null,
    estimateState: "open",
    text: "",
    cards: [],
    done: null,
    context: null,
    meta: null,
    error: null,
    streaming: true,
  };
}

export const sameFocus = (a: ChatFocus, b: ChatFocus) => a.kind === b.kind && a.event_id === b.event_id && (a.person_id ?? null) === (b.person_id ?? null);

function apply(turn: AssistantTurn, ev: ChatEvent): AssistantTurn {
  switch (ev.type) {
    case "step": {
      const i = turn.steps.findIndex((s) => s.id === ev.data.id);
      const steps = i === -1 ? [...turn.steps, ev.data] : turn.steps.map((s, j) => (j === i ? ev.data : s));
      return { ...turn, steps };
    }
    case "clarify":
      return { ...turn, clarify: ev.data };
    case "estimate":
      return { ...turn, estimate: ev.data, estimateState: "open" };
    case "text":
      return { ...turn, text: joinDelta(turn.text, ev.data.delta ?? "") };
    case "context":
      return { ...turn, context: ev.data };
    case "cards":
      return { ...turn, cards: [...turn.cards, ev.data] };
    case "done":
      return { ...turn, done: ev.data };
    case "error":
      return { ...turn, error: ev.data.message };
    default:
      return turn;
  }
}

export function fromStored(messages: StoredMessage[]): Turn[] {
  // A confirm click is not something the RM typed: it shows no bubble live, so it shows none on reopen either.
  return messages.flatMap((m, i): Turn[] =>
    m.role === "user"
      ? isConfirmMessage(m)
        ? []
        : [{ kind: "user", id: nid(), text: m.text }]
      : [{
          ...blankAssistant(),
          steps: (m.steps ?? []).map((s) => (s.status === "running" ? { ...s, status: "done" } : s)),
          estimate: m.estimate ?? null,
          estimateState: m.estimate ? (isConfirmMessage(messages[i + 1]) ? "confirmed" : "cancelled") : "open",
          clarify: m.clarify ?? null,
          answered: m.clarify ? "stored" : null,
          text: m.clarify ? "" : m.text,
          cards: m.cards ?? [],
          streaming: false,
          meta: m.meta ?? null,
          done: m.meta ? doneFromMeta(m.meta) : null,
        }],
  );
}

/** A footer for a reopened answer, from its stored meta (v1 messages have none: no footer, never zeros). */
function doneFromMeta(m: MessageMeta): ChatDone | null {
  if (m.cost_usd === undefined && !m.models) return null;
  return {
    total_cost_usd: m.cost_usd ?? 0,
    models: m.models ?? [],
    seconds: m.seconds ?? 0,
    tokens: m.tokens_in !== undefined ? { input: m.tokens_in, output: m.tokens_out ?? 0, cached_input: m.cached_in ?? 0 } : undefined,
  };
}

/** The focus and compression count a reopened conversation ends on. */
function stateFromStored(messages: StoredMessage[]): { focus: ChatFocus[]; compressions: number; context: ChatContext | null } {
  let focus: ChatFocus[] = [];
  let compressions = 0;
  let context: ChatContext | null = null;
  for (const m of messages) {
    if (!m.meta) continue;
    if (m.meta.focus) focus = m.meta.focus;
    if (m.meta.compressed) compressions += 1;
    if (m.meta.context) context = m.meta.context;
    else if (m.meta.tokens_in !== undefined && m.meta.context_tokens !== undefined)
      // Older threads: the provider figures the turn stored (never an estimate presented as usage).
      context = {
        prompt_tokens: m.meta.tokens_in,
        cached_tokens: m.meta.cached_in ?? 0,
        history_tokens_before: m.meta.context_tokens,
        history_tokens_after: m.meta.context_tokens,
        compressed: false,
        turns_kept: 0,
        focus: m.meta.focus ?? [],
      };
  }
  return { focus, compressions, context };
}

/** The control tower's conversation state: shared by the left rail and the home page. */
export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { user } = useSession();
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [conversationsError, setConversationsError] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [focus, setFocus] = useState<ChatFocus[]>([]);
  const [context, setContext] = useState<ChatContext | null>(null);
  const [compressions, setCompressions] = useState(0);
  const [model, setModelState] = useState<string | null>(null);
  const modelRef = useRef<string | null>(null);
  /** The RM's pick, sent with the next turn: "" means the defaults; null means "keep what the server has". */
  const setModel = useCallback((id: string | null) => {
    modelRef.current = id ?? "";
    setModelState(id);
  }, []);
  const restoreModel = useCallback((id: string | null) => {
    modelRef.current = null;
    setModelState(id);
  }, []);
  /** Set when the RM edited the focus chip; sent with the next turn, then cleared. */
  const focusOverride = useRef<ChatFocus[] | null>(null);
  const abort = useRef<AbortController | null>(null);
  const activeRef = useRef<string | null>(null);

  const refresh = useCallback(() => {
    chatApi
      .conversations()
      .then((c) => {
        setConversations(c);
        setConversationsError(false);
      })
      .catch(() => {
        setConversations([]);
        setConversationsError(true);
      });
  }, []);

  useEffect(() => {
    if (user) refresh();
  }, [user, refresh]);

  const patchTurn = useCallback((id: string, patch: Partial<AssistantTurn>) => {
    setTurns((ts) => ts.map((t) => (t.id === id && t.kind === "assistant" ? { ...t, ...patch } : t)));
  }, []);

  const send = useCallback(
    ({ message, choice = null, confirmToken = null, display, onStarted }: SendInput) => {
      if (busy) return;
      const shown = display === undefined ? message : display;
      const assistant = blankAssistant();
      setTurns((ts) => [...ts, ...(shown ? [{ kind: "user", id: nid(), text: shown } as UserTurn] : []), assistant]);
      setBusy(true);
      const ctrl = new AbortController();
      abort.current = ctrl;
      const override = focusOverride.current;
      focusOverride.current = null;
      (async () => {
        try {
          const req = { conversation_id: activeRef.current, message, choice, confirm_token: confirmToken, ...(override ? { focus: override } : {}), ...(modelRef.current !== null ? { model: modelRef.current } : {}) };
          let started = false;
          for await (const ev of streamChat(req, ctrl.signal)) {
            if (ev.type === "step" && !started) {
              started = true;
              onStarted?.();
            }
            if (ev.type === "meta") {
              setActiveId(ev.data.conversation_id);
              activeRef.current = ev.data.conversation_id;
              setTitle((t) => t ?? ev.data.title);
              continue;
            }
            if (ev.type === "focus") {
              setFocus(ev.data.focus ?? []);
              continue;
            }
            if (ev.type === "context") {
              // A turn answered without a model sends no prompt; keep the last meter reading rather than dropping it to 0.
              setContext((prev) => (ev.data.prompt_tokens > 0 || !prev ? ev.data : { ...prev, focus: ev.data.focus }));
              if (ev.data.focus) setFocus(ev.data.focus);
              if (ev.data.compressed) setCompressions((n) => n + 1);
            }
            setTurns((ts) => ts.map((t) => (t.id === assistant.id && t.kind === "assistant" ? apply(t, ev) : t)));
          }
        } finally {
          setTurns((ts) =>
            ts.map((t) =>
              t.id === assistant.id && t.kind === "assistant"
                ? {
                    ...t,
                    streaming: false,
                    steps: t.steps.map((s) => (s.status === "running" ? { ...s, status: ctrl.signal.aborted ? "skipped" : "failed" } : s)),
                    note: ctrl.signal.aborted ? "Stopped." : t.note,
                  }
                : t,
            ),
          );
          setBusy(false);
          abort.current = null;
          refresh();
        }
      })();
    },
    [busy, refresh],
  );

  const stop = useCallback(() => abort.current?.abort(), []);

  const newChat = useCallback(() => {
    abort.current?.abort();
    setActiveId(null);
    activeRef.current = null;
    setTitle(null);
    setTurns([]);
    setFocus([]);
    setContext(null);
    setCompressions(0);
    restoreModel(null);
    focusOverride.current = null;
  }, [restoreModel]);

  const dropFocus = useCallback((f: ChatFocus) => {
    setFocus((cur) => {
      const next = cur.filter((x) => !sameFocus(x, f));
      focusOverride.current = next;
      return next;
    });
  }, []);

  const open = useCallback(async (id: string) => {
    abort.current?.abort();
    setActiveId(id);
    activeRef.current = id;
    setLoading(true);
    setTurns([]);
    setFocus([]);
    setContext(null);
    setCompressions(0);
    focusOverride.current = null;
    try {
      const c = await chatApi.conversation(id);
      if (activeRef.current !== id) return;
      setTitle(c.title);
      setTurns(fromStored(c.messages));
      const st = stateFromStored(c.messages);
      setFocus(st.focus);
      setCompressions(st.compressions);
      setContext(st.context);
      restoreModel([...c.messages].reverse().find((m) => m.meta)?.meta?.chat_model ?? null);
    } catch {
      setTurns([{ ...blankAssistant(), streaming: false, error: "This conversation could not be opened. It may have been deleted." }]);
    } finally {
      setLoading(false);
    }
  }, [restoreModel]);

  const remove = useCallback(
    async (id: string) => {
      await chatApi.remove(id);
      if (activeRef.current === id) newChat();
      refresh();
    },
    [newChat, refresh],
  );

  const value = useMemo<Ctx>(
    () => ({ conversations, conversationsError, activeId, title, turns, busy, loading, send, stop, open, newChat, remove, patchTurn, refresh, focus, dropFocus, context, compressions, model, setModel }),
    [conversations, conversationsError, activeId, title, turns, busy, loading, send, stop, open, newChat, remove, patchTurn, refresh, focus, dropFocus, context, compressions, model, setModel],
  );
  return <ChatCtx.Provider value={value}>{children}</ChatCtx.Provider>;
}

export function useChat() {
  const c = useContext(ChatCtx);
  if (!c) throw new Error("useChat must be used inside <ChatProvider>");
  return c;
}
