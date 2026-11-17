/**
 * Downloads: a conversation as Markdown, a person's call pack as Markdown (PDFs come from the print routes).
 *
 * The data service builds both files (CHAT_CONTRACT v2: export.md, callpack.md). Until it does, and in preview
 * mode, the same report is built here from data already on screen, so the button always gives the RM a file.
 */
import { api, apiUrl } from "@/lib/api";
import { buildCallScript, properName, shortCompany } from "@/lib/call-script";
import { CHAT_MOCK, chatApi, formatCost, formatTokens, modelLabel, percent, type ChatCard, type ChatScriptCard, type StoredConversation, type StoredMessage } from "@/lib/chat";
import type { CallItem, Evidence, EventSummary, PersonCard } from "@/lib/types";

export function conversationPrintHref(id: string, auto = true) {
  return `/history/${encodeURIComponent(id)}/print${auto ? "?print=1" : ""}`;
}
export function callPackPrintHref(eventId: string, personId: string, auto = true) {
  return `/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}/print${auto ? "?print=1" : ""}`;
}

function slug(s: string) {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "finsight"
  );
}

function save(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** The server's Markdown when it has the endpoint; null when it does not (404) so the caller builds its own. */
async function serverMarkdown(path: string): Promise<string | null> {
  if (CHAT_MOCK) return null;
  try {
    const res = await fetch(apiUrl(path), { headers: { Accept: "text/markdown" }, cache: "no-store" });
    if (res.ok) return await res.text();
    if (res.status === 404 || res.status === 405) return null;
    throw new Error(`Download failed (${res.status})`);
  } catch (err) {
    if (err instanceof TypeError) throw new Error("The data service is not reachable. Start it and try again.");
    throw err;
  }
}

const esc = (s: unknown) => String(s ?? "").replace(/\|/g, "\\|").replace(/\n+/g, " ");
const evLink = (e: Evidence) => {
  const page = e.printed_page ? `p. ${e.printed_page}` : `PDF p. ${e.pdf_index}`;
  const href = e.source_url ?? e.url;
  return href ? `[${e.doc_label}, ${page}](${href})` : `${e.doc_label}, ${page}`;
};

function cardMarkdown(card: ChatCard): string[] {
  if (card.kind === "script" && card.sections) return scriptMarkdown(card as ChatScriptCard, "###");
  const items = Array.isArray(card.items) ? card.items : [];
  if (!items.length) return [];
  const out = [`### ${card.title}`, ""];
  if (card.kind === "people") {
    out.push("| # | Person | Event | Money | Timing | How sure |", "|---|---|---|---:|---|---|");
    (items as CallItem[]).forEach((i, n) =>
      out.push(`| ${n + 1} | ${esc(properName(i.person.name))}${i.person.role ? ` (${esc(i.person.role)})` : ""} | ${esc(shortCompany(i.event.company))} | ${esc(i.amount.display)} | ${esc(i.timing.label)} | ${esc(i.confidence?.level)} |`),
    );
  } else if (card.kind === "events") {
    out.push("| Event | Type | Money date | Cash in hand | People |", "|---|---|---|---:|---:|");
    (items as EventSummary[]).forEach((e) =>
      out.push(`| ${esc(shortCompany(e.company))} | ${esc(e.type_label ?? e.type)} | ${esc(e.money_date?.display ?? "—")} | ${e.cash_cr != null ? `₹${e.cash_cr.toFixed(2)} Cr` : "Not disclosed"} | ${e.people_count} |`),
    );
  } else if (card.kind === "person") {
    const p = items[0] as PersonCard;
    out.push(`**${properName(p.person.name)}**${p.person.role ? `, ${p.person.role}` : ""} · ${shortCompany(p.event.company)}`, "");
    out.push(`- Money: ${p.amount.display}${p.amount.estimate ? " (estimate)" : ""}`, `- When: ${p.timing.label}`, `- How sure: ${p.confidence.level}. ${p.confidence.reason}`);
    for (const a of p.amounts ?? []) {
      const ev = a.inputs.flatMap((x) => x.evidence.slice(0, 1));
      out.push(`- ${a.label}: ${a.short ?? a.display}${a.working ? ` (${a.working})` : ""}${ev.length ? ` · ${ev.map(evLink).join(", ")}` : ""}`);
    }
  } else if (card.kind === "calendar") {
    out.push("| Date | Event | What | Total |", "|---|---|---|---:|");
    (items as { display: string; label: string; event: { company: string }; total_cr?: number | null }[]).forEach((r) =>
      out.push(`| ${esc(r.display)} | ${esc(shortCompany(r.event.company))} | ${esc(r.label)} | ${r.total_cr != null ? `₹${r.total_cr.toFixed(2)} Cr` : "Not disclosed"} |`),
    );
  } else if (card.kind === "lineage") {
    type N = { label: string; detail?: string | null; children?: N[] };
    const walk = (nodes: N[], depth: number) => {
      for (const n of nodes) {
        out.push(`${"  ".repeat(depth)}- ${n.label}${n.detail ? ` · ${n.detail}` : ""}`);
        if (n.children?.length) walk(n.children, depth + 1);
      }
    };
    walk(items as N[], 0);
  }
  out.push("");
  return out;
}

function scriptMarkdown(card: Pick<ChatScriptCard, "title" | "sections">, h: string): string[] {
  return [`${h} ${card.title}`, "", ...card.sections.flatMap((s) => [`**${s.heading}**`, "", ...s.lines.map((l) => `- ${l}`), ""])];
}

function metaLine(m: StoredMessage): string | null {
  const meta = m.meta;
  if (!meta) return null;
  const cached = percent(meta.cached_in, meta.tokens_in);
  const models = (meta.models ?? []).map((x) => `${modelLabel(x.model)} × ${x.calls}`).join(", ") || "code only";
  return `_${models} · ${formatTokens(meta.tokens_in)} in / ${formatTokens(meta.tokens_out)} out${cached !== null ? ` · ${cached}% cached` : ""} · ${formatCost(meta.cost_usd)}${meta.compressed ? " · earlier turns summarised here" : ""}_`;
}

/** The whole thread as a clean report: questions, answers, cards as tables, sources as links, cost per turn. */
export function conversationMarkdown(c: StoredConversation): string {
  const cost = c.messages.reduce((s, m) => s + (m.meta?.cost_usd ?? 0), 0);
  const asked = c.messages.filter((m) => m.role === "user").length;
  const out = [`# ${c.title}`, "", `FinSight conversation · ${asked} ${asked === 1 ? "question" : "questions"} · total cost ${formatCost(cost)}`, ""];
  for (const m of c.messages) {
    if (m.role === "user") {
      out.push(`## ${m.text.trim() || "(picked an option)"}`, "");
      continue;
    }
    if (m.clarify) {
      out.push(`> ${m.clarify.question}`, "", ...m.clarify.options.map((o) => `> - ${o.label}`), "");
    } else if (m.text) out.push(m.text.trim(), "");
    if (m.estimate) out.push(`> Cost preview: ${m.estimate.action.title}, ${formatCost(m.estimate.cost_usd_low)}–${formatCost(m.estimate.cost_usd_high)}`, "");
    for (const card of m.cards ?? []) out.push(...cardMarkdown(card));
    const line = metaLine(m);
    if (line) out.push(line, "");
  }
  out.push("---", "Every number above was checked against the filing it came from.");
  return out.join("\n");
}

/** Call card + brief + call script + evidence links. */
export function callPackMarkdown(card: PersonCard, script: Pick<ChatScriptCard, "title" | "sections"> = buildCallScript(card)): string {
  const name = properName(card.person.name);
  const out = [
    `# Call pack: ${name}`,
    "",
    `${card.person.role ?? "Named in the filing"} · ${shortCompany(card.event.company)} ${card.event.type_label ?? card.event.type}`,
    "",
    `- **Money:** ${card.amount.display}${card.amount.estimate ? " (estimate)" : ""} · ${card.tier_label}`,
    `- **When:** ${card.timing.label}`,
    `- **How sure:** ${card.confidence.level}. ${(card.confidence.reasons ?? [card.confidence.reason]).join("; ")}`,
    "",
    "## Brief",
    "",
    ...(card.brief?.lines ?? [card.brief_first_line]).map((l, i) => `${i + 1}. ${l}`),
    "",
    "## Why now",
    "",
    card.why_now || card.why,
    "",
    "## The numbers and where they come from",
    "",
  ];
  for (const a of card.amounts ?? []) {
    out.push(`**${a.label}: ${a.short ?? a.display}**${a.working ? `  \n${a.working}` : ""}`, "");
    for (const input of a.inputs) for (const e of input.evidence.slice(0, 1)) out.push(`- ${input.label}: ${input.value} · ${evLink(e)}  \n  > “${e.quote.slice(0, 240)}”`);
    out.push("");
  }
  if (card.household && card.household.members.length > 1) {
    out.push(`## ${card.household.label}`, "", ...card.household.members.map((m) => `- ${properName(m.name)}${m.role ? ` (${m.role})` : ""}: ${m.amount.display}`), "");
  }
  out.push(...scriptMarkdown(script, "##"), "---", "Every number above was checked against the filing it came from.");
  return out.join("\n");
}

export async function downloadConversationMarkdown(id: string, title?: string) {
  const text = (await serverMarkdown(`/chat/conversations/${encodeURIComponent(id)}/export.md`)) ?? conversationMarkdown(await chatApi.conversation(id));
  save(`${slug(title ?? "conversation")}.md`, text);
}

export async function downloadCallPackMarkdown(eventId: string, personId: string, name?: string) {
  let text = await serverMarkdown(`/people/${encodeURIComponent(eventId)}/${encodeURIComponent(personId)}/callpack.md`);
  let label = name;
  if (text === null) {
    const card = await api.person(eventId, personId);
    label = label ?? card.person.name;
    text = callPackMarkdown(card);
  }
  save(`call-pack-${slug(properName(label ?? personId))}.md`, text);
}
