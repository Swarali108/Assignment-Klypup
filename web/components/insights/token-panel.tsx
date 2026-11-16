"use client";

import { CircleDollarSign, DatabaseZap, Gauge, Minimize2 } from "lucide-react";
import { ErrorState, SectionHeader, SkeletonStat, StatCard, StatStrip } from "@/components/ds";
import { Skeleton } from "@/components/ui/skeleton";
import { TokenLegend, TokenSplitBars } from "@/components/charts/token-charts";
import { formatCost, formatTokens, modelLabel } from "@/lib/chat";
import { insightsApi, useLoad, type OpsTokens } from "@/lib/insights";

const DESCRIPTION =
  "How the control tower keeps answers cheap. The fixed instructions are sent first and byte-identical on every turn, so the provider serves them from its cache at a fraction of the price; long conversations are summarised so each answer carries less.";

/** Trust & Ops: token optimisation for chat answers, from GET /api/ops/tokens. */
export function TokenPanel() {
  const [res, retry] = useLoad(insightsApi.opsTokens);
  return (
    <section className="space-y-4" aria-labelledby="token-optimization">
      <SectionHeader title={<span id="token-optimization">Token optimization</span>} description={DESCRIPTION} />
      {res.state === "loading" ? (
        <div className="space-y-4" role="status" aria-label="Loading token use">
          <StatStrip>
            <SkeletonStat />
            <SkeletonStat />
            <SkeletonStat />
            <SkeletonStat />
          </StatStrip>
          <Skeleton className="h-48 rounded-xl" />
        </div>
      ) : res.state === "error" ? (
        <ErrorState title="Token use could not load" reason={res.reason} onRetry={retry} />
      ) : res.data === null ? (
        <div className="rounded-xl border border-dashed bg-surface px-5 py-8 text-center">
          <p className="text-sm font-medium text-foreground">Not recorded by this data service yet</p>
          <p className="mx-auto mt-1 max-w-[52ch] text-[13px] text-muted-foreground">
            Once the assistant records tokens per answer, cache hits, savings and cost per question appear here. Nothing else on this page depends on it.
          </p>
        </div>
      ) : res.data.questions === 0 ? (
        <div className="rounded-xl border border-dashed bg-surface px-5 py-8 text-center">
          <p className="text-sm font-medium text-foreground">No questions answered yet</p>
          <p className="mx-auto mt-1 max-w-[52ch] text-[13px] text-muted-foreground">Ask the control tower anything; its token use and savings are counted from the first answer.</p>
        </div>
      ) : (
        <Tokens data={res.data} />
      )}
    </section>
  );
}

function Tokens({ data }: { data: OpsTokens }) {
  const rate = Math.round((data.cache_hit_rate ?? 0) * 100);
  const rows = (data.by_model ?? [])
    .filter((m) => m?.model)
    .map((m) => ({
      key: m.model,
      label: modelLabel(m.model),
      sub: `${m.calls ?? 0} ${m.calls === 1 ? "call" : "calls"} · ${formatTokens(m.output_tokens)} out`,
      total: m.input_tokens ?? 0,
      cached: Math.min(m.cached_tokens ?? 0, m.input_tokens ?? 0),
      display: formatCost(m.cost_usd),
      aside: m.input_tokens ? `${Math.round(((m.cached_tokens ?? 0) / m.input_tokens) * 100)}% cached` : "—",
    }));
  const withoutCache = (data.total_cost_usd ?? data.avg_cost_usd * data.questions) + data.saved_usd_by_cache;
  return (
    <div className="space-y-4">
      <StatStrip>
        <StatCard label="Cache hit rate" icon={DatabaseZap} value={`${rate}%`} sub={`${formatTokens(data.cached_tokens)} of ${data.input_tokens ? formatTokens(data.input_tokens) : "all"} input tokens reused`} />
        <StatCard
          label="Saved by caching"
          icon={CircleDollarSign}
          value={formatCost(data.saved_usd_by_cache)}
          sub={withoutCache > 0 ? `${Math.round((data.saved_usd_by_cache / withoutCache) * 100)}% off what the same answers would cost uncached` : "Against full-price input"}
        />
        <StatCard label="Saved by summarising" icon={Minimize2} value={`${formatTokens(data.tokens_saved_by_compression)} tokens`} sub={`Older turns summarised ${data.compressions}× across all conversations`} />
        <StatCard label="Average cost per question" icon={Gauge} value={formatCost(data.avg_cost_usd)} sub={`Across ${data.questions} ${data.questions === 1 ? "answer" : "answers"}; lookups run on code at $0`} />
      </StatStrip>
      {rows.length ? (
        <div className="overflow-hidden rounded-xl border bg-surface shadow-(--shadow-card)">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-4 py-3 sm:px-5">
            <p className="text-sm font-medium">Input tokens by model</p>
            <TokenLegend />
          </div>
          <div className="hidden grid-cols-[minmax(0,12rem)_minmax(0,1fr)_6rem_5.5rem] gap-x-4 border-b border-hairline bg-surface-sunken/50 px-5 py-2 text-xs font-medium text-muted-foreground sm:grid">
            <span>Model</span>
            <span>Input tokens, cached and fresh</span>
            <span className="text-right">Cost</span>
            <span className="text-right">Reused</span>
          </div>
          <TokenSplitBars rows={rows} />
          <div className="sr-only">
          <table>
            <caption>Input tokens by model</caption>
            <thead>
              <tr>
                <th>Model</th>
                <th>Calls</th>
                <th>Input tokens</th>
                <th>Cached tokens</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td>{r.label}</td>
                  <td>{r.sub}</td>
                  <td>{r.total}</td>
                  <td>{r.cached}</td>
                  <td>{r.display}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
