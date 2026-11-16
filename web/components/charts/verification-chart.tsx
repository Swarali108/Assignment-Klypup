"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export type VerificationRow = { id: string; name: string; kept: number; rejected: number };

/** Kept vs rejected values per event, horizontal stacked bars. Click a bar to select its event. */
export function VerificationChart({
  rows,
  selected,
  onSelect,
}: {
  rows: VerificationRow[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const height = rows.length * 34 + 36;
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }} barCategoryGap={9}>
          <CartesianGrid horizontal={false} stroke="var(--border)" strokeOpacity={0.7} />
          <XAxis
            type="number"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
            className="tnum"
          />
          <YAxis
            type="category"
            dataKey="name"
            width={168}
            tickLine={false}
            axisLine={false}
            interval={0}
            tick={(props: { x?: number | string; y?: number | string; payload?: { value?: unknown; index?: number } }) => {
              const row = rows[props.payload?.index ?? -1];
              const label = String(props.payload?.value ?? "");
              const on = row?.id === selected;
              return (
                <text
                  x={Number(props.x) - 6}
                  y={props.y}
                  dy={4}
                  textAnchor="end"
                  fontSize={12}
                  fontWeight={on ? 600 : 400}
                  fill={on ? "var(--foreground)" : "var(--muted-foreground)"}
                  style={{ cursor: "pointer" }}
                  onClick={() => row && onSelect(row.id)}
                >
                  {label.length > 21 ? `${label.slice(0, 20).trim()}…` : label}
                </text>
              );
            }}
          />
          <Tooltip
            cursor={{ fill: "var(--accent)", opacity: 0.6 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as VerificationRow;
              const total = r.kept + r.rejected;
              return (
                <div className="rounded-lg border bg-surface px-3 py-2 text-xs shadow-(--shadow-raised)">
                  <p className="mb-1 font-semibold text-foreground">{r.name}</p>
                  <p className="tnum text-muted-foreground">
                    <span className="mr-1.5 inline-block size-2 rounded-sm bg-brand" />
                    {r.kept} kept ({total ? Math.round((r.kept / total) * 100) : 0}%)
                  </p>
                  <p className="tnum text-muted-foreground">
                    <span className="mr-1.5 inline-block size-2 rounded-sm bg-negative/70" />
                    {r.rejected} rejected
                  </p>
                </div>
              );
            }}
          />
          <Bar
            dataKey="kept"
            stackId="v"
            fill="var(--brand)"
            radius={[3, 0, 0, 3]}
            cursor="pointer"
            onClick={(d: { payload?: VerificationRow }) => d.payload && onSelect(d.payload.id)}
            isAnimationActive={false}
          />
          <Bar
            dataKey="rejected"
            stackId="v"
            fill="var(--negative)"
            fillOpacity={0.7}
            radius={[0, 3, 3, 0]}
            cursor="pointer"
            onClick={(d: { payload?: VerificationRow }) => d.payload && onSelect(d.payload.id)}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
