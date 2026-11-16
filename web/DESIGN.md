# AURELIA design system

Direction for the demo UI: a calm, trustworthy private-bank desk tool. The RM opens it in the
morning, in an office, on a laptop; business viewers watch over their shoulder. Operate mode:
scanability and trust beat expression. Brand lives in precise details (numerals, evidence, copy).

Assumptions (no design interview was possible; inferred from the spec and plan): light-first,
Inter, one accent colour, solid surfaces, Indian number formats, RM language only.

## Principles

1. **Money first, then when, then how sure.** Every row reads left to right: who → why → tier and
   confidence → timing → amount. The amount is right-aligned, tabular, and the biggest thing on a row.
2. **Every number is traceable.** Amounts carry evidence chips that open the filing page with the
   quote highlighted. Unknown amounts say "Amount not disclosed" plus the reason, never ₹0.
3. **Quiet surfaces, one accent.** Warm paper canvas, white cards with a hairline border and a
   soft offset shadow. The accent (ledger green) marks the brand, cash, focus and selection only.
4. **Plain words.** No file names, field names, "pipeline", "LLM" or "extract" on any screen.
   Labels name the thing ("Cash in hand", "Shares just unlocked", "Scanned filing: text not readable yet").

## Tokens (app/globals.css)

| Role | Light | Dark | Use |
|---|---|---|---|
| `background` | oklch(0.982 0.004 85) warm paper | oklch(0.175 0.012 255) | page canvas |
| `surface` / `card` | white | oklch(0.21 0.013 255) | cards, rows, dialogs |
| `surface-sunken` | oklch(0.962 0.006 85) | oklch(0.16 0.011 255) | wells, evidence page backdrop |
| `foreground` | oklch(0.215 0.022 255) ink navy | oklch(0.94 0.006 85) | text |
| `muted-foreground` | oklch(0.49 0.018 255) | oklch(0.72 0.012 255) | secondary text (≥4.5:1) |
| `faint` | oklch(0.6 0.014 255) | oklch(0.6 0.012 255) | rank numbers, ≈ marks, captions |
| `border` / `hairline` | oklch(0.905 …) / oklch(0.935 …) | | card edge / row dividers |
| `brand` (the one accent) | oklch(0.43 0.075 165) ledger green | oklch(0.74 0.09 165) | brand mark, cash tier, focus ring, selection |
| `positive` / `caution` / `negative` / `info` | green / ochre / brick / slate blue, each with a `-soft` tint | | status semantics only, never decoration |
| `highlight` | oklch(0.88 0.12 90) | | quote highlight (matches the page highlight) |

Semantic mapping: cash in hand = brand; shares just unlocked = caution; holds shares = neutral.
Event status: ready = positive, processing = info (spinner), failed = negative, scanned = caution,
not supported = neutral. Confidence: three-step bar glyph, high = positive, medium = caution, low = negative.

## Type

Inter Variable (self-hosted via @fontsource, no network at build), features `cv05 cv08 ss03`.
All numbers use the `tnum` utility (tabular, lining).

| Step | Size / weight | Use |
|---|---|---|
| Page title | 28px / 600, -0.02em | `PageHeader` |
| Person name | 28px / 600 | call card |
| Hero amount | 32px / 600, -0.02em | call card money |
| KPI | 26px / 600 | `StatCard` |
| Section | 16px / 600 | `SectionHeader` |
| Row name | 15px / 600 | `PersonRow` |
| Body | 14px / 400, 1.5 | default |
| Meta | 13px | row sub-lines, timing |
| Caption | 12px | labels, reasons |

## Space, radius, depth

- 4px base. Rows: 16px vertical, 20px horizontal. Cards: 20–32px padding. Sections: 40px apart;
  more space above a heading than below it.
- Content max width 1240px; sidebar 240px (sheet under 1024px).
- Radius: controls 8px, cards 14px (`rounded-xl`), call card 18px (`rounded-2xl`), badges 6px.
- Depth: `--shadow-card` (1px offset, soft) on cards; `--shadow-raised` on hover and the evidence page.
  No glows, no glass, no gradients.

## Motion

150–200ms ease-out for hover/colour; dialogs use the shadcn fade/zoom; the household chevron
rotates. `prefers-reduced-motion` collapses all motion. One authored moment: the evidence viewer
scrolls smoothly to the highlighted quote when the API sends `X-Highlight-Y`.

## Formats (lib/format.ts)

`formatCr(92.05)` → `₹92.05 Cr` · `formatINR(12345678)` → `₹1,23,45,678` · `formatDate("2026-11-26")`
→ `26 Nov 2026` · `formatRelative(iso, asOf)` → `in 11 days` / `8 months ago` (always against the
API's as-of date, never the clock during render). Estimates carry a muted `≈`.

## Components (components/ds, import from `@/components/ds`)

AppShell · CommandPalette (⌘K, search + Ask) · Money · TimingPill · ConfidenceBadge · TierBadge ·
StatusBadge · PersonRow + CallList · PersonCardHeader · EvidenceChip + EvidenceViewer · StatCard +
StatStrip · SectionHeader + PageHeader · EmptyState · ErrorState · Skeleton{Text,Row,List,Stat,Card} ·
RmStatusControl · Avatar · Wordmark. All states are on `/dev/gallery`.

## Rules for builders

- Use the tokens (`bg-surface`, `text-muted-foreground`, `bg-brand-soft`…), never raw hex.
- No eyebrow labels above headings, no coloured left borders on cards, no emoji, no gradient text.
- Every list has a designed empty, loading (skeleton) and error state.
- Charts: brand for the primary series, `chart-2…5` for the rest, hairline grid, tabular ticks.
