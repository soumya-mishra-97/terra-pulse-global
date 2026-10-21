import { geoNaturalEarth1, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import countries from "i18n-iso-countries";
import { useMemo, useState } from "react";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import world from "world-atlas/countries-110m.json";
import type { CountryListItem } from "../api/types";
import { fmtPct, fmtPeople } from "../lib/format";

type Metric = "population" | "growth" | "share";
const W = 960, H = 430;

// Theme tokens (styles.css). Sequential: one blue hue, low -> high contrast against the surface.
// Diverging: orange (decline) <- grey (~0) -> blue (growth).
const SEQ = [1, 2, 3, 4, 5, 6].map((i) => `var(--seq-${i})`);
const DIV_NEG = [1, 2, 3].map((i) => `var(--div-neg-${i})`);
const DIV_MID = "var(--div-mid)";
const DIV_POS = [1, 2, 3].map((i) => `var(--div-pos-${i})`);
const EMPTY = "var(--empty)";

function seqColor(t: number) {
  const i = Math.max(0, Math.min(SEQ.length - 1, Math.floor(t * SEQ.length)));
  return SEQ[i];
}
function divColor(v: number) {
  if (Math.abs(v) < 0.1) return DIV_MID;
  if (v < 0) return v < -1 ? DIV_NEG[0] : v < -0.5 ? DIV_NEG[1] : DIV_NEG[2];
  return v > 2 ? DIV_POS[2] : v > 1 ? DIV_POS[1] : DIV_POS[0];
}

export function WorldMap({ items, onSelect }: { items: CountryListItem[]; onSelect?: (iso3: string) => void }) {
  const [metric, setMetric] = useState<Metric>("population");
  const [hover, setHover] = useState<{ x: number; y: number; item: CountryListItem | null; name: string } | null>(null);

  const geo = useMemo(() => {
    const topo = world as unknown as Topology<{ countries: GeometryCollection<{ name: string }> }>;
    const fc = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry, { name: string }>;
    // Antarctica (ISO 010) has no population data and would take a fifth of the canvas.
    return { ...fc, features: fc.features.filter((f) => String(f.id) !== "010") };
  }, []);
  const path = useMemo(() => geoPath(geoNaturalEarth1().fitSize([W, H], geo)), [geo]);
  const byIso = useMemo(() => new Map(items.map((i) => [i.iso3, i])), [items]);
  const logRange = useMemo(() => {
    const vals = items.map((i) => i.population).filter((v): v is number => !!v).map(Math.log10);
    return [Math.min(...vals), Math.max(...vals)] as const;
  }, [items]);

  function color(item: CountryListItem | undefined) {
    if (!item) return EMPTY;
    if (metric === "growth") return item.growth_percent === null ? EMPTY : divColor(item.growth_percent);
    const v = metric === "population" ? item.population : item.share_of_world_percent;
    if (!v) return EMPTY;
    if (metric === "share") return seqColor(Math.min(1, Math.log10(v * 100 + 1) / 3.3));
    return seqColor((Math.log10(v) - logRange[0]) / (logRange[1] - logRange[0] || 1));
  }

  const iso3Of = (f: Feature<Geometry, { name: string }>) => {
    const id = String(f.id ?? "");
    return id ? countries.numericToAlpha3(id) : undefined;
  };

  return (
    <div className="map-wrap" onMouseLeave={() => setHover(null)}>
      <div className="card-head">
        <div>
          <h3 className="card-title">World map</h3>
          <div className="card-sub">Latest source year per country · grey = data unavailable · click a country for details</div>
        </div>
        <div className="seg" role="group" aria-label="Map metric">
          {(["population", "growth", "share"] as Metric[]).map((m) => (
            <button key={m} aria-pressed={metric === m} onClick={() => setMetric(m)}>
              {m === "population" ? "Population" : m === "growth" ? "Growth %" : "World share"}
            </button>
          ))}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Choropleth world map of ${metric}`}>
        {geo.features.map((f, idx) => {
          const iso3 = iso3Of(f);
          const item = iso3 ? byIso.get(iso3) : undefined;
          return (
            <path key={`${f.id ?? "x"}-${idx}`} className="country" d={path(f) ?? ""} fill={color(item)}
              style={{ cursor: item ? "pointer" : "default" }}
              onMouseMove={(e) => {
                const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                setHover({ x: e.clientX - box.left + 12, y: e.clientY - box.top + 12, item: item ?? null, name: f.properties?.name ?? "" });
              }}
              onClick={() => item && onSelect?.(item.iso3)}>
              <title>{item ? `${item.name}: ${fmtPeople(item.population)}` : `${f.properties?.name ?? ""}: data unavailable`}</title>
            </path>
          );
        })}
      </svg>
      {hover && (
        <div className="tooltip" style={{ left: hover.x, top: hover.y }}>
          <b>{hover.item?.name ?? hover.name}</b>
          {hover.item ? (
            <>
              <div>Population: {fmtPeople(hover.item.population)} <span className="muted">({hover.item.population_year})</span></div>
              <div>Growth: {fmtPct(hover.item.growth_percent, 2, true)} <span className="muted">({hover.item.growth_year})</span></div>
              <div>World share: {fmtPct(hover.item.share_of_world_percent, 2)}</div>
              <div className="muted">Midyear estimates · source [S1]</div>
            </>
          ) : <div className="muted">Data unavailable</div>}
        </div>
      )}
      <div className="card map-legend">
        <div className="card-sub" style={{ marginBottom: 6 }}>Legend · {metric === "growth" ? "annual growth (%)" : metric === "share" ? "share of world (%)" : "population (log scale)"}</div>
        {metric === "growth" ? (
          <>
            <div className="ramp" style={{ background: `linear-gradient(90deg, ${DIV_NEG[0]}, ${DIV_NEG[2]}, ${DIV_MID}, ${DIV_POS[0]}, ${DIV_POS[2]})` }} />
            <div className="ramp-labels"><span>&lt; −1%</span><span>0</span><span>&gt; 2%</span></div>
          </>
        ) : (
          <>
            <div className="ramp" style={{ background: `linear-gradient(90deg, ${SEQ.join(",")})` }} />
            <div className="ramp-labels">
              {metric === "population" ? <><span>{fmtPeople(10 ** logRange[0])}</span><span>{fmtPeople(10 ** logRange[1])}</span></> : <><span>0%</span><span>~20%</span></>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
