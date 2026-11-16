"use client";

/**
 * Canvas half of the Network screen. Loaded only in the browser (next/dynamic, ssr: false) because
 * the force layout needs `window`. Colours come from the design tokens, re-read on theme change.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from "react-force-graph-2d";
import { useTheme } from "next-themes";
import type { NetEdge, NetNode } from "@/lib/insights";

export type GNode = NetNode & { r: number };
type GLink = { source: string | GNode; target: string | GNode; kind: string; reason: string };

function readTokens() {
  const s = getComputedStyle(document.documentElement);
  const v = (n: string) => s.getPropertyValue(n).trim() || "#888";
  return {
    fg: v("--foreground"),
    muted: v("--muted-foreground"),
    faint: v("--faint"),
    surface: v("--surface"),
    hairline: v("--border"),
    brand: v("--brand"),
    caution: v("--caution"),
    holding: v("--chart-4"),
    entity: v("--chart-5"),
    bg: v("--surface-sunken"),
  };
}

/** Pull every node gently toward the centre so separate events sit close together. */
function gravity(strength: number) {
  let list: { x?: number; y?: number; vx?: number; vy?: number }[] = [];
  const force = (alpha: number) => {
    for (const n of list) {
      n.vx = (n.vx ?? 0) - (n.x ?? 0) * strength * alpha;
      n.vy = (n.vy ?? 0) - (n.y ?? 0) * strength * alpha;
    }
  };
  force.initialize = (nodes: typeof list) => {
    list = nodes;
  };
  return force;
}

function titleCase(s: string) {
  return s === s.toUpperCase() ? s.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()) : s;
}

type Box = { x0: number; y0: number; x1: number; y1: number };

/** Font, text and the label's box (graph coordinates) for a node; shared by drawing and collision checks. */
function labelGeom(ctx: CanvasRenderingContext2D, n: NodeObject<GNode>, scale: number, pill: boolean) {
  const x = n.x ?? 0;
  const y = n.y ?? 0;
  const size = (pill ? 11.5 : 10) / scale;
  ctx.font = `${pill ? 600 : 500} ${size}px "Inter Variable", Inter, system-ui, sans-serif`;
  const text = pill ? titleCase(n.label).replace(/\s+(limited|ltd\.?)$/i, "") : n.label;
  const ty = y + n.r + (pill ? 10 : 7) / scale;
  const w = ctx.measureText(text).width + (pill ? 12 : 4) / scale;
  const h = size + (pill ? 8 : 4) / scale;
  const pad = 2 / scale;
  const box: Box = { x0: x - w / 2 - pad, y0: ty - h / 2 - pad, x1: x + w / 2 + pad, y1: ty + h / 2 + pad };
  return { x, ty, text, w, h, box };
}

const overlaps = (a: Box, placed: Box[]) => placed.some((p) => !(a.x1 < p.x0 || a.x0 > p.x1 || a.y1 < p.y0 || a.y0 > p.y1));

function drawLabel(
  ctx: CanvasRenderingContext2D,
  n: NodeObject<GNode>,
  scale: number,
  t: ReturnType<typeof readTokens>,
  pill: boolean,
) {
  const { x, ty, text, w, h } = labelGeom(ctx, n, scale, pill);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  if (pill) {
    ctx.fillStyle = t.surface;
    ctx.strokeStyle = t.hairline;
    ctx.lineWidth = 1 / scale;
    ctx.beginPath();
    ctx.roundRect(x - w / 2, ty - h / 2, w, h, 5 / scale);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = t.fg;
  } else {
    ctx.lineWidth = 3 / scale;
    ctx.strokeStyle = t.bg;
    ctx.strokeText(text, x, ty);
    ctx.fillStyle = t.muted;
  }
  ctx.fillText(text, x, ty);
}

const endId = (e: string | GNode) => (typeof e === "string" ? e : e.id);

export function GraphCanvas({
  nodes,
  edges,
  height,
  focusId,
  onHover,
  onPick,
}: {
  nodes: GNode[];
  edges: NetEdge[];
  height: number;
  focusId: string | null;
  onHover: (n: GNode | null) => void;
  onPick: (n: GNode) => void;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const fg = useRef<ForceGraphMethods<NodeObject<GNode>, LinkObject<GNode, GLink>> | undefined>(undefined);
  const [width, setWidth] = useState(0);
  const { resolvedTheme } = useTheme();
  const [tokens, setTokens] = useState<ReturnType<typeof readTokens> | null>(null);
  const fitted = useRef(false);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const id = requestAnimationFrame(() => setTokens(readTokens()));
    return () => cancelAnimationFrame(id);
  }, [resolvedTheme]);

  // The library mutates node/link objects (x, y, source → object); give it its own copies.
  const data = useMemo(
    () => ({
      nodes: nodes.map((n) => ({ ...n })),
      links: edges.map((e) => ({ source: e.source, target: e.target, kind: e.kind, reason: e.reason })) as GLink[],
    }),
    [nodes, edges],
  );

  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of edges) {
      if (!m.has(e.source)) m.set(e.source, new Set());
      if (!m.has(e.target)) m.set(e.target, new Set());
      m.get(e.source)!.add(e.target);
      m.get(e.target)!.add(e.source);
    }
    return m;
  }, [edges]);

  useEffect(() => {
    const g = fg.current;
    if (!g) return;
    g.d3Force("charge")?.strength?.(-26);
    g.d3Force("link")?.distance?.((l: GLink) => (l.kind === "household" ? 10 : 22));
    g.d3Force("gravity", gravity(0.09));
    fitted.current = false;
    g.d3ReheatSimulation();
  }, [data, width, tokens]);

  const lit = (id: string) => !focusId || id === focusId || neighbours.get(focusId)?.has(id);
  // Narrow screens: a shorter canvas, and names only for the larger events (the rest on tap).
  const narrow = width > 0 && width < 640;
  const h = narrow ? Math.min(height, 440) : height;
  const coarse = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

  return (
    <div ref={wrap} className="h-full w-full" style={{ height: h }}>
      {width > 0 && tokens ? (
        <ForceGraph2D<GNode, GLink>
          ref={fg}
          width={width}
          height={h}
          graphData={data}
          backgroundColor="rgba(0,0,0,0)"
          warmupTicks={160}
          cooldownTicks={120}
          onEngineStop={() => {
            if (!fitted.current) {
              fitted.current = true;
              fg.current?.zoomToFit(500, 36);
            }
          }}
          nodeRelSize={1}
          nodeVal={(n) => n.r * n.r}
          nodeLabel={() => ""}
          linkColor={(l) => {
            const on = !focusId || endId(l.source) === focusId || endId(l.target) === focusId;
            if (l.kind === "household") return on ? tokens.brand : tokens.hairline;
            return on && focusId ? tokens.muted : tokens.hairline;
          }}
          linkWidth={(l) => (l.kind === "household" ? 1.6 : 0.7)}
          linkLineDash={(l) => (l.kind === "same_person" ? [3, 2] : null)}
          onNodeHover={(n) => {
            if (n) onHover(n); // the card stays after the pointer leaves, so its links can be clicked
            if (wrap.current) wrap.current.style.cursor = n ? "pointer" : "";
          }}
          onNodeClick={(n) => (coarse ? onHover(n) : onPick(n))}
          onBackgroundClick={() => onHover(null)}
          nodeCanvasObject={(n, ctx, scale) => {
            const x = n.x ?? 0;
            const y = n.y ?? 0;
            const on = lit(n.id);
            ctx.globalAlpha = on ? 1 : 0.18;
            const color =
              n.type === "event"
                ? tokens.fg
                : n.type === "entity"
                  ? tokens.entity
                  : n.tier === "cash_now"
                    ? tokens.brand
                    : n.tier === "unlock"
                      ? tokens.caution
                      : tokens.holding;
            ctx.fillStyle = color;
            if (n.type === "entity") {
              const s = n.r * 1.6;
              ctx.beginPath();
              ctx.roundRect(x - s / 2, y - s / 2, s, s, 1.2);
              ctx.fill();
            } else {
              ctx.beginPath();
              ctx.arc(x, y, n.r, 0, 2 * Math.PI);
              ctx.fill();
              if (n.type === "event") {
                ctx.lineWidth = 2 / scale;
                ctx.strokeStyle = tokens.surface;
                ctx.stroke();
              }
            }
            if (n.id === focusId) {
              ctx.lineWidth = 2 / scale;
              ctx.strokeStyle = tokens.brand;
              ctx.beginPath();
              ctx.arc(x, y, n.r + 3 / scale + 1, 0, 2 * Math.PI);
              ctx.stroke();
            }
            if (n.type !== "event" && (scale > 2.6 || (focusId !== null && on && focusId !== null))) {
              drawLabel(ctx, n, scale, tokens, false);
            }
            ctx.globalAlpha = 1;
          }}
          onRenderFramePost={(ctx, scale) => {
            // Company names last, so they sit on top of the holders around them. Greedy declutter:
            // the focused node and its neighbours first, then the biggest companies; a label that would
            // overlap one already drawn is skipped (zoom in and it appears).
            const near = focusId ? neighbours.get(focusId) : undefined;
            const prio = (n: GNode) => (n.id === focusId ? 1e9 : near?.has(n.id) ? 1e8 : 0) + (n.people_count ?? 0) * 1000 + n.r;
            const events = (data.nodes as NodeObject<GNode>[]).filter((n) => n.type === "event").sort((a, b) => prio(b) - prio(a));
            const placed: Box[] = [];
            for (const n of events) {
              const must = n.id === focusId || Boolean(near?.has(n.id));
              if (narrow && (n.people_count ?? 0) < 8 && !must) continue;
              const { box } = labelGeom(ctx, n, scale, true);
              if (!must && overlaps(box, placed)) continue;
              placed.push(box);
              ctx.globalAlpha = lit(n.id) ? 1 : 0.3;
              drawLabel(ctx, n, scale, tokens, true);
            }
            ctx.globalAlpha = 1;
          }}
          nodePointerAreaPaint={(n, color, ctx) => {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x ?? 0, n.y ?? 0, Math.max(n.r, 4) + 2, 0, 2 * Math.PI);
            ctx.fill();
          }}
        />
      ) : null}
    </div>
  );
}
