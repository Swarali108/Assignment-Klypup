/** Stable demo data the suite relies on (all already processed, so nothing here ever runs the pipeline). */
export const SEDEMAC = { event: "sedemac_ipo", person: "p_manish_sharma", name: "Manish Sharma", company: "SEDEMAC" };
/** Sells in an IPO with cash in hand. Read-only in this suite: the demo already holds a call note on this card. */
export const KUSUM = { event: "hd_fire_protect_limited_ipo_202610", person: "p_kusum_harish_dharamshi", name: "KUSUM HARISH DHARAMSHI" };
/** An insider sale with a single person (no call state of its own), used for the quick call log on Today. */
export const ANAND = { event: "sri_lotus_developers_and_realty_insider_sale_2026w45", person: "p_anand_kamalnayan_pandit", name: "Anand Kamalnayan Pandit" };
export const VECTRAS = { event: "vectras_ipo", company: "Vectras" };
export const WIPRO = { event: "wipro_buyback", company: "Wipro" };
/** Processed, but every holder is a company or fund: the honest empty state. */
export const JIO = { event: "jio_platforms_limited_ipo_202610", company: "Jio Platforms" };
