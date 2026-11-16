import type { Tier } from "@/lib/types";

/**
 * The section a person is shown under. Sale money that was paid out earlier ("Cash received earlier") counts as
 * cash in hand, so a paid buyback reads as paid; the pipeline keeps its own order for ranking.
 */
export function bucketOf(i: { tier: Tier; tier_label?: string | null }): Tier {
  return i.tier === "holding" && i.tier_label === "Cash received earlier" ? "cash_now" : i.tier;
}
