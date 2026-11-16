// Tier-1 check for the chat UI's pure logic (no network, no browser).
// Run: node --experimental-strip-types scripts/check-chat.mjs
import assert from "node:assert/strict";
const t = await import("../lib/chat-text.ts");
const cs = await import("../lib/call-script.ts");
const th = await import("../components/history/thread.ts");

// Streaming: sentence cuts keep every character, and never split inside a number.
const prose = "Dr. Rao has ₹468.85 Cr in hand. Timing: listed 21 Oct.\n\nHow sure: medium. 1,731.52 Cr together!";
const parts = t.sentences(prose);
assert.equal(parts.join(""), prose);
assert.ok(parts.slice(0, -1).every((p) => /\s$/.test(p)), "every cut is at whitespace, never inside a number");
assert.ok(parts.some((p) => p.includes("₹468.85 Cr")));
// Rebuilding from deltas never changes a number, with or without the deltas' own spaces.
assert.equal(t.joinDelta("₹468.", "85 Cr"), "₹468.85 Cr");
assert.equal(t.joinDelta("at 10:", "30"), "at 10:30");
assert.equal(t.joinDelta("in hand.", "Timing"), "in hand. Timing");
assert.equal(t.joinDelta("in hand. ", "Timing"), "in hand. Timing");
assert.equal(parts.reduce((s, p) => t.joinDelta(s, p), ""), prose);

// Names and the call script: every number comes from the card.
assert.equal(cs.properName("ASHA RAO MENON"), "Asha Rao Menon");
assert.equal(cs.properName("Asha McRao"), "Asha McRao");
assert.equal(cs.shortCompany("ACME POLYMERS LIMITED"), "Acme Polymers");
const card = {
  event: { id: "e1", company: "Acme Polymers Limited", type: "ipo", type_label: "IPO" },
  person: { id: "p1", name: "ASHA RAO MENON", role: "Promoter Selling Shareholder", holder_type: "person" },
  tier: "cash_now",
  tier_label: "Cash in hand",
  amount: { value_cr: 12.34, display: "₹12.34 Cr", kind: "cash", estimate: false },
  amounts: [{ key: "retained", label: "Value of shares kept", value_cr: 5.6, display: "₹5.60 crore", short: "₹5.60 Cr", working: null, inputs: [] }],
  timing: { label: "Listed 3 Nov 2026 (12 days ago)", status: "past", date_iso: "2026-11-03" },
  confidence: { level: "high", reason: "Checked" },
  why: "",
  why_now: "Sells 1,000 shares in the offer for sale",
  brief: { lines: [] },
  brief_first_line: "",
  household: null,
};
const script = cs.buildCallScript(card);
assert.equal(script.kind, "script");
assert.deepEqual(script.person, { event_id: "e1", person_id: "p1", name: "Asha Rao Menon" });
assert.deepEqual(script.sections.map((s) => s.heading), ["Opening", "Why now", "Three questions", "Likely objections", "Next step"]);
assert.equal(script.sections[2].lines.length, 3);
const digits = (s) => s.match(/\d[\d,.]*/g) ?? [];
const allowed = new Set([...digits(JSON.stringify(card)), "30", "2"]);
for (const line of script.sections.flatMap((s) => s.lines)) for (const d of digits(line)) assert.ok(allowed.has(d.replace(/[.,]$/, "")), `number not from the card: ${d} in “${line}”`);
assert.ok(cs.scriptText(script).startsWith("Call script for Asha Rao Menon"));

// History: exchanges pair questions with answers; unmeasured answers are not counted as $0.
const msgs = [
  { role: "user", text: "q1" },
  { role: "assistant", text: "a1", meta: { cost_usd: 0.002, tokens_in: 1000, tokens_out: 100, cached_in: 600, compressed: false, models: [{ model: "m", calls: 1, cost_usd: 0.002 }] } },
  { role: "user", text: "q2" },
  { role: "assistant", text: "a2" },
  { role: "assistant", text: "confirmed run", meta: { cost_usd: 0.001, tokens_in: 500, tokens_out: 50, cached_in: 0, compressed: true, models: [{ model: "m", calls: 2, cost_usd: 0.001 }] } },
];
const xs = th.exchanges(msgs);
assert.deepEqual(xs.map((x) => [x.question?.text ?? null, x.answer?.text ?? null]), [["q1", "a1"], ["q2", "a2"], [null, "confirmed run"]]);
const tot = th.totals({ messages: msgs });
assert.equal(tot.measured, 2);
assert.equal(tot.answers, 3);
assert.equal(tot.compressions, 1);
assert.equal(tot.tokensIn, 1500);
assert.deepEqual(tot.models, [{ model: "m", calls: 3, cost_usd: 0.003 }]);
console.log("chat checks passed");
