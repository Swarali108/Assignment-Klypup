/** Small formatters shared by the live agent tree and the "How this list was built" view. */

/** "anthropic/claude-haiku-5.5" -> "Claude Haiku 5.5"; "code + x/y" -> "Code + Y"; "code" -> "Code". */
export function runsOnLabel(runsOn: string | null | undefined): string {
  const text = (runsOn ?? "").trim();
  if (!text || text === "code") return "Code";
  // "model" is a stand-in when the run's logs do not name the model; "skipped" only says one call did not run.
  const parts = text.split(/\s*\+\s*|\s*,\s*/).filter(Boolean);
  const named = parts.filter((p) => p !== "model" && p !== "skipped");
  if (!named.length) return parts.includes("model") ? "A model" : "Skipped";
  return named.map((part) => (part === "code" ? "Code" : modelName(part))).join(" + ");
}

function modelName(id: string): string {
  const tail = id.includes("/") ? id.split("/").pop()! : id;
  return tail
    .split("-")
    .map((w) => (/^gpt$/i.test(w) ? "GPT" : /^\d/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

/** True when a model (not only code) answered or was asked. */
export function usesModel(runsOn: string | null | undefined): boolean {
  const t = (runsOn ?? "").trim();
  return !!t && t !== "code" && t !== "skipped";
}

/** Dollars with enough digits to show sub-cent model spend ($0.0004), always 4 decimals under $1. */
export function usd4(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return Math.abs(n) < 1 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

/** 840 -> "840 ms"; 12400 -> "12.4 s"; 83000 -> "1 m 23 s". */
export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`;
  const s = ms / 1000;
  if (s < 59.5) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  const whole = Math.round(s);
  return `${Math.floor(whole / 60)} m ${whole % 60} s`;
}

const SINGULAR: Record<string, string> = {
  rows: "row",
  quotes: "quote",
  pages: "page",
  people: "person",
  sellers: "seller",
  briefs: "brief",
  families: "family",
  "sections found": "section found",
  "candidate pages": "candidate page",
  "offer facts": "offer fact",
  "people rows": "people row",
  "firms and funds": "firm or fund",
  "page refs fixed": "page ref fixed",
};

/** {rows: 5, quotes: 15} -> "5 rows · 15 quotes" (booleans and nulls dropped, keys in plain words). */
export function returnsText(returns: Record<string, number | boolean | null> | null | undefined): string {
  if (!returns) return "";
  const words: Record<string, string> = {
    rows: "rows",
    quotes: "quotes",
    proposed: "proposed",
    kept: "kept",
    rejected: "rejected",
    citations_corrected: "page refs fixed",
    sections_found: "sections found",
    candidate_pages: "candidate pages",
    pages: "pages",
    printed_page_numbers: "numbered",
    bytes: "",
    people: "people",
    merges: "merged",
    model_asks: "asked the model",
    families: "families",
    sellers: "sellers",
    matches: "seen elsewhere",
    callable: "to call",
    entities: "firms and funds",
    briefs: "briefs",
    model: "by model",
    template: "by template",
    rows_in: "rows in",
    people_rows: "people rows",
    offer_facts: "offer facts",
    people_in_report: "in the list",
  };
  const parts: string[] = [];
  for (const [k, v] of Object.entries(returns)) {
    if (k === "sections") continue;
    if (k === "bytes" && typeof v === "number") {
      parts.push(v > 1024 * 1024 ? `${(v / 1024 / 1024).toFixed(1)} MB` : `${Math.round(v / 1024)} KB`);
      continue;
    }
    if (k === "reused_copy") {
      parts.push(v ? "copy on disk reused" : "downloaded now");
      continue;
    }
    if (typeof v !== "number") continue;
    const w0 = words[k] ?? k.replace(/_/g, " ");
    const w = v === 1 ? (SINGULAR[w0] ?? w0) : w0;
    parts.push(`${v.toLocaleString("en-IN")} ${w}`);
  }
  return parts.join(" · ");
}
