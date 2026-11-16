/**
 * A call script built by code from the call card (no model, no new numbers): opening, why now, three questions,
 * likely objections with answers, next step. The chat backend sends its own `script` card (CHAT_CONTRACT v2); this
 * builder is the same shape, used by the preview mock, the printable call pack and the Markdown call pack.
 */
import type { ChatScriptCard, ScriptSection } from "@/lib/chat";
import type { PersonCard } from "@/lib/types";

/** "ASHA RAO MENON" → "Asha Rao Menon"; mixed-case names pass through. */
export function properName(name: string): string {
  if (name !== name.toUpperCase()) return name;
  return name.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/\b(Huf|Llp)\b/g, (m) => m.toUpperCase());
}

/** "Acme Polymers Limited" → "Acme Polymers". */
export function shortCompany(name: string): string {
  return properName(name).replace(/\s+(limited|ltd\.?)$/i, "");
}

const kind = (c: PersonCard) => c.event.type_label ?? (c.event.type === "ipo" ? "IPO" : c.event.type === "buyback" ? "buyback" : "offer for sale");

export function buildCallScript(card: PersonCard): ChatScriptCard {
  const name = properName(card.person.name);
  const first = name.split(" ")[0];
  const company = shortCompany(card.event.company);
  const cash = card.tier === "cash_now";
  const unlock = card.tier === "unlock";
  const amount = card.amount.value_cr !== null ? `${card.amount.estimate ? "about " : ""}${card.amount.display}` : null;
  const retained = card.amounts.find((a) => a.key === "retained" && a.value_cr !== null);
  const household = card.household && card.household.members.length > 1 ? card.household : null;
  const others = household ? household.members.filter((m) => !m.id.endsWith(`/${card.person.id}`)).map((m) => properName(m.name)) : [];

  const sections: ScriptSection[] = [
    {
      heading: "Opening",
      lines: [
        `Good morning ${first}, this is [your name] from the private bank. Is this a good moment for two minutes?`,
        `I am calling about the ${company} ${kind(card)}${card.person.role ? `, where you are named as ${card.person.role.toLowerCase()}` : ""}. Congratulations on the milestone.`,
      ],
    },
    {
      heading: "Why now",
      lines: [
        cash && amount ? `The filing shows ${amount} coming to you from the sale.` : unlock && amount ? `Shares worth ${amount} are now free to sell.` : amount ? `The filing shows holdings worth ${amount}.` : "The filing names you; the amount is not disclosed, so ask rather than assume.",
        card.timing.label ? `Timing: ${card.timing.label}.` : "",
        card.why_now ? `${card.why_now}.` : "",
      ].filter(Boolean),
    },
    {
      heading: "Three questions",
      lines: [
        cash ? "Has the money from the sale reached your account yet, and where is it sitting today?" : "Are you planning to sell any of the shares as they become free?",
        retained ? `You still hold shares worth about ${retained.short ?? retained.display}. How are you thinking about that concentration in one company?` : "How much of your wealth is now tied to this one company?",
        household ? `Would it help to plan this together with ${others.slice(0, 2).join(" and ") || "the family"}?` : "Is anyone else in the family involved in these decisions?",
      ],
    },
    {
      heading: "Likely objections",
      lines: [
        "“I already have a bank.” — Most families keep two: we only need a slice to show what we do differently.",
        "“It is too early to decide.” — Agreed; a short plan now keeps the money from sitting idle in a current account.",
        cash ? "“The money is earmarked for the business.” — Then let us park it safely and liquid until it is needed." : "“I will not sell.” — Fine; we can lend against the shares instead of selling them.",
      ],
    },
    {
      heading: "Next step",
      lines: [
        "Offer a short meeting this week, at their office or ours.",
        "Send a one-page summary of what we discussed the same day.",
      ],
    },
  ];
  return { kind: "script", title: `Call script for ${name}`, person: { event_id: card.event.id, person_id: card.person.id, name }, sections };
}

/** Plain text of a script (for copy-all). */
export function scriptText(card: Pick<ChatScriptCard, "title" | "sections">): string {
  return [card.title, "", ...card.sections.flatMap((s) => [s.heading, ...s.lines.map((l) => `- ${l}`), ""])].join("\n").trim();
}
