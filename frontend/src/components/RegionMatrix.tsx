import type { RegionStat } from "../api/types";
import { fmtPct } from "../lib/format";
import { SERIES } from "./charts";

const COLS: { key: keyof RegionStat; label: string; fmt: (v: number) => string; short: (v: number) => string }[] = [
  { key: "growth_percent", label: "Growth %", fmt: (v) => fmtPct(v, 2), short: (v) => v.toFixed(1) },
  { key: "fertility_rate", label: "Fertility", fmt: (v) => `${v.toFixed(2)} births/woman`, short: (v) => v.toFixed(1) },
  { key: "life_expectancy_years", label: "Life exp.", fmt: (v) => `${v.toFixed(1)} years`, short: (v) => v.toFixed(0) },
  { key: "age_0_14_pct", label: "Age 0-14", fmt: (v) => fmtPct(v, 1), short: (v) => v.toFixed(0) },
  { key: "age_15_64_pct", label: "Age 15-64", fmt: (v) => fmtPct(v, 1), short: (v) => v.toFixed(0) },
  { key: "age_65_plus_pct", label: "Age 65+", fmt: (v) => fmtPct(v, 1), short: (v) => v.toFixed(0) },
  { key: "urban_pct", label: "Urban", fmt: (v) => fmtPct(v, 1), short: (v) => v.toFixed(0) },
];

/**
 * Bubble matrix (regions x indicators). Size encodes the value scaled within each column; colour encodes
 * polarity vs the world figure (blue = above world, orange = below), with values printed in each bubble.
 */
export function RegionMatrix({ regions, world }: { regions: RegionStat[]; world: RegionStat | null }) {
  const ranges = COLS.map((c) => {
    const vals = regions.map((r) => r[c.key] as number | null).filter((v): v is number => v !== null);
    return [Math.min(...vals), Math.max(...vals)] as const;
  });
  return (
    <div className="matrix">
      <table>
        <caption className="sr-only">Regional demographic indicators compared with the world</caption>
        <thead>
          <tr><th /> {COLS.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {regions.map((r) => (
            <tr key={r.code}>
              <th scope="row" className="row" title={r.name}>{r.name.length > 26 ? `${r.name.slice(0, 24)}…` : r.name}</th>
              {COLS.map((c, i) => {
                const v = r[c.key] as number | null;
                if (v === null) return <td key={c.key}><span className="note">n/a</span></td>;
                const [lo, hi] = ranges[i];
                const t = hi === lo ? 0.5 : (v - lo) / (hi - lo);
                const size = 26 + t * 20;
                const w = world?.[c.key] as number | null;
                const above = w !== null && w !== undefined && v >= w;
                const color = above ? SERIES[0] : SERIES[1];
                const label = `${r.name} — ${c.label}: ${c.fmt(v)}${w != null ? ` (world ${c.fmt(w)})` : ""}, ${r.year ?? ""}`;
                return (
                  <td key={c.key}>
                    <span className="bubble" title={label} aria-label={label}
                      style={{ width: size, height: size, background: `color-mix(in srgb, ${color} ${above ? 80 : 70}%, transparent)` }}>
                      {c.short(v)}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="legend" style={{ marginTop: 8 }}>
        <span><i style={{ background: SERIES[0] }} />At or above world value</span>
        <span><i style={{ background: SERIES[1] }} />Below world value</span>
        <span className="note">Bubble size: value within column range · hover for exact figures</span>
      </div>
    </div>
  );
}
