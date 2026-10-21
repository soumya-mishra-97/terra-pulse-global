import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, PolarAngleAxis,
  PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { ChartSpec, RegionStat, YearValue } from "../api/types";
import { fmtPct, fmtPeople } from "../lib/format";

// Theme tokens (styles.css), so charts follow the light/dark switch without re-rendering.
export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
const GRID = "var(--border)";
const SURFACE = "var(--surface-1)";
const AXIS = { stroke: "var(--border-strong)", tick: { fill: "var(--text-muted)", fontSize: 11 } };
const TOOLTIP = {
  contentStyle: { background: "var(--tooltip-bg)", border: "1px solid var(--border-strong)", borderRadius: 10, fontSize: 12 },
  labelStyle: { color: "var(--text-primary)", fontWeight: 600 },
  itemStyle: { color: "var(--text-secondary)" },
};

function fmtByUnit(unit: string) {
  return (v: number) => (unit === "persons" ? fmtPeople(v) : unit === "%" ? fmtPct(v, 2) : v.toLocaleString("en-US"));
}

export function TrendChart({ data, height = 230, label = "World population" }: { data: YearValue[]; height?: number; label?: string }) {
  return (
    <div role="img" aria-label={`${label}, ${data[0]?.year}–${data.at(-1)?.year}`}>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
          <defs>
            <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={SERIES[0]} stopOpacity={0.35} />
              <stop offset="100%" stopColor={SERIES[0]} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="year" {...AXIS} tickLine={false} />
          <YAxis {...AXIS} tickLine={false} axisLine={false} width={52} tickFormatter={(v) => fmtPeople(v)} domain={["auto", "auto"]} />
          <Tooltip {...TOOLTIP} formatter={(v) => [fmtPeople(Number(v)), label]} labelFormatter={(y) => `1 Jul ${y} (estimate)`} />
          <Area isAnimationActive={false} type="monotone" dataKey="value" stroke={SERIES[0]} strokeWidth={2} fill="url(#trendFill)" dot={false}
            activeDot={{ r: 5, stroke: SURFACE, strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Renders the chart spec emitted by the agents / report builder. */
export function SpecChart({ spec, height = 200 }: { spec: ChartSpec; height?: number }) {
  const fmt = fmtByUnit(spec.unit);
  if (spec.type === "bar") {
    const rows = spec.series.filter((s): s is { name: string; value: number } => "value" in s);
    return (
      <div role="img" aria-label={spec.title}>
        <div className="card-sub">{spec.title}</div>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="name" {...AXIS} tickLine={false} interval={0} tick={{ ...AXIS.tick, fontSize: 10 }} />
            <YAxis {...AXIS} tickLine={false} axisLine={false} width={50} tickFormatter={fmt} />
            <Tooltip {...TOOLTIP} cursor={{ fill: "var(--accent-soft)" }} formatter={(v) => [fmt(Number(v)), spec.title]} />
            <Bar isAnimationActive={false} dataKey="value" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={36} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }
  const series = spec.series.filter((s): s is { name: string; points: YearValue[] } => "points" in s).slice(0, 3);
  const years = [...new Set(series.flatMap((s) => s.points.map((p) => p.year)))].sort();
  const rows = years.map((y) => Object.fromEntries([["year", y], ...series.map((s) => [s.name, s.points.find((p) => p.year === y)?.value ?? null])]));
  return (
    <div role="img" aria-label={spec.title}>
      <div className="card-sub">{spec.title}</div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="year" {...AXIS} tickLine={false} />
          <YAxis {...AXIS} tickLine={false} axisLine={false} width={50} tickFormatter={fmt} domain={["auto", "auto"]} />
          <Tooltip {...TOOLTIP} formatter={(v, n) => [fmt(Number(v)), String(n)]} />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }} iconType="circle" />}
          {series.map((s, i) => (
            <Line isAnimationActive={false} key={s.name} type="monotone" dataKey={s.name} stroke={SERIES[i]} strokeWidth={2} dot={false}
              activeDot={{ r: 5, stroke: SURFACE, strokeWidth: 2 }} connectNulls={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Radar: share of population aged 0-14 vs 65+ by World Bank region. */
export function AgeRadar({ regions }: { regions: RegionStat[] }) {
  const short = (n: string) => n.replace("Middle East, North Africa, Afghanistan & Pakistan", "MENA + AF/PK")
    .replace("Latin America & Caribbean", "Latin Am.").replace("East Asia & Pacific", "East Asia")
    .replace("Europe & Central Asia", "Europe/C. Asia").replace("Sub-Saharan Africa", "Sub-Sah. Africa");
  const data = regions.map((r) => ({ region: short(r.name), "Aged 0-14": r.age_0_14_pct, "Aged 65+": r.age_65_plus_pct }));
  return (
    <div role="img" aria-label="Radar chart of the share of population aged 0-14 and 65 and over, by region">
      <ResponsiveContainer width="100%" height={270}>
        <RadarChart data={data} outerRadius="60%" margin={{ top: 10, right: 44, bottom: 10, left: 44 }}>
          <PolarGrid stroke={GRID} />
          <PolarAngleAxis dataKey="region" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
          <PolarRadiusAxis tick={false} axisLine={false} domain={[0, "dataMax"]} />
          <Tooltip {...TOOLTIP} formatter={(v, n) => [fmtPct(Number(v), 1), String(n)]} />
          <Radar isAnimationActive={false} name="Aged 0-14" dataKey="Aged 0-14" stroke={SERIES[0]} fill={SERIES[0]} fillOpacity={0.25} strokeWidth={2}
            dot={{ r: 3, fill: SERIES[0] }} />
          <Radar isAnimationActive={false} name="Aged 65+" dataKey="Aged 65+" stroke={SERIES[1]} fill={SERIES[1]} fillOpacity={0.25} strokeWidth={2}
            dot={{ r: 3, fill: SERIES[1] }} />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Half-split donut: urban vs rural share (world). Direct labels carry identity, not colour alone. */
export function UrbanSplit({ urban, year }: { urban: number | null; year: number | null }) {
  if (urban === null) return <div className="state">Data unavailable</div>;
  const data = [{ name: "Urban", value: urban }, { name: "Rural", value: 100 - urban }];
  return (
    <div role="img" aria-label={`World urban population ${fmtPct(urban, 1)} and rural ${fmtPct(100 - urban, 1)} in ${year}`}>
      <ResponsiveContainer width="100%" height={225}>
        <PieChart>
          <Pie isAnimationActive={false} data={data} dataKey="value" innerRadius={62} outerRadius={92} startAngle={90} endAngle={-270}
            stroke={SURFACE} strokeWidth={2} paddingAngle={1}>
            {data.map((d, i) => <Cell key={d.name} fill={SERIES[i]} />)}
          </Pie>
          <Tooltip {...TOOLTIP} formatter={(v, n) => [fmtPct(Number(v), 1), String(n)]} />
        </PieChart>
      </ResponsiveContainer>
      <div className="legend" style={{ justifyContent: "center" }}>
        <span><i style={{ background: SERIES[0] }} />Urban <b>{fmtPct(urban, 1)}</b></span>
        <span><i style={{ background: SERIES[1] }} />Rural <b>{fmtPct(100 - urban, 1)}</b></span>
      </div>
    </div>
  );
}
