import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { SpecChart } from "../components/charts";
import { ProvenanceBanner } from "../components/ProvenanceBanner";
import { EmptyState, ErrorState, NoDataset, Skeleton } from "../components/States";
import { flagEmoji, fmtPct, fmtPeople } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const METRICS: [string, string][] = [
  ["population_total", "Total population"], ["population_growth_pct", "Growth rate (%)"], ["fertility_rate", "Fertility rate"],
  ["life_expectancy_years", "Life expectancy"], ["age_65_plus_pct", "Aged 65+ (%)"], ["urban_pct", "Urban (%)"],
  ["net_migration", "Net migration"],
];

export function Countries({ search }: { search: string }) {
  const [params, setParams] = useSearchParams();
  const selected = params.get("c");
  const [sort, setSort] = useState("population");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [region, setRegion] = useState("");
  const [metric, setMetric] = useState("population_total");
  const list = useAsync(() => api.countries({ q: search, sort, order, region, limit: 300 }), [search, sort, order, region]);
  const regions = useAsync(() => api.regions());
  const history = useAsync(() => (selected ? api.history(selected, metric) : Promise.resolve(null)), [selected, metric]);
  useEffect(() => { if (!selected && list.data?.items[0]) setParams({ c: list.data.items[0].iso3 }, { replace: true }); },
    [list.data, selected, setParams]);
  const current = useMemo(() => list.data?.items.find((i) => i.iso3 === selected), [list.data, selected]);

  function toggleSort(key: string) {
    if (sort === key) setOrder(order === "desc" ? "asc" : "desc");
    else { setSort(key); setOrder(key === "name" ? "asc" : "desc"); }
  }
  const sortMark = (k: string) => (sort === k ? (order === "desc" ? " ↓" : " ↑") : "");

  if (list.error instanceof ApiError && list.error.status === 503) return <div className="card"><NoDataset /></div>;
  return (
    <>
      {list.data && <ProvenanceBanner p={list.data.provenance} />}
      <div className="grid two">
        <section className="card" aria-labelledby="clist">
          <div className="card-head">
            <div><h3 className="card-title" id="clist">Countries</h3>
              <div className="card-sub">{list.data ? `${list.data.total} economies` : "Loading…"} · search in the top bar</div></div>
            <select className="select" style={{ width: 210 }} value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Filter by region">
              <option value="">All regions</option>
              {regions.data?.regions.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
            </select>
          </div>
          {list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : !list.data ? <Skeleton height={480} /> :
            list.data.items.length === 0 ? <EmptyState title="No countries match your search" /> : (
              <div className="table-scroll">
                <table className="data">
                  <thead><tr>
                    <th><button className="sort-btn" onClick={() => toggleSort("name")}>Country{sortMark("name")}</button></th>
                    <th className="num"><button className="sort-btn" onClick={() => toggleSort("population")}>Population{sortMark("population")}</button></th>
                    <th className="num"><button className="sort-btn" onClick={() => toggleSort("growth")}>Growth{sortMark("growth")}</button></th>
                    <th className="num"><button className="sort-btn" onClick={() => toggleSort("share")}>World share{sortMark("share")}</button></th>
                  </tr></thead>
                  <tbody>
                    {list.data.items.map((c) => (
                      <tr key={c.iso3} className="clickable" aria-selected={c.iso3 === selected}
                        onClick={() => setParams({ c: c.iso3 })} tabIndex={0}
                        onKeyDown={(e) => e.key === "Enter" && setParams({ c: c.iso3 })}>
                        <td><span aria-hidden="true">{flagEmoji(c.iso2)}</span> {c.name}</td>
                        <td className="num">{fmtPeople(c.population)}</td>
                        <td className={`num ${c.growth_percent !== null && c.growth_percent < 0 ? "neg" : "pos"}`}>{fmtPct(c.growth_percent, 2, true)}</td>
                        <td className="num">{fmtPct(c.share_of_world_percent, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </section>
        <section className="card" aria-labelledby="cdetail">
          <div className="card-head">
            <div>
              <h3 className="card-title" id="cdetail">
                {current ? <><span aria-hidden="true">{flagEmoji(current.iso2)}</span> {current.name}</> : "Country detail"}
              </h3>
              <div className="card-sub">{current ? `${current.region ?? ""} · ${current.income_level ?? ""}` : ""}</div>
            </div>
            {selected && <Link className="pill-btn primary" to={`/reports?c=${selected}`}>Generate report</Link>}
          </div>
          <div className="seg" role="group" aria-label="Indicator" style={{ flexWrap: "wrap", borderRadius: 12 }}>
            {METRICS.map(([k, l]) => <button key={k} aria-pressed={metric === k} onClick={() => setMetric(k)}>{l}</button>)}
          </div>
          <div style={{ marginTop: 12 }}>
            {history.error ? <ErrorState error={history.error} onRetry={history.reload} /> : !history.data ? <Skeleton height={260} /> :
              history.data.points.length === 0 ? <EmptyState title="Data unavailable">The source has no values for this indicator.</EmptyState> : (
                <>
                  <SpecChart height={260} spec={{
                    type: "line", title: `${history.data.name}: ${METRICS.find(([k]) => k === metric)?.[1]} (${history.data.unit})`,
                    unit: metric === "population_total" ? "persons" : metric.endsWith("_pct") ? "%" : "",
                    series: [{ name: history.data.name, points: history.data.points.map((p) => ({ year: p.year, value: p.value })) }],
                  }} />
                  {history.data.change && (
                    <dl className="grid two" style={{ margin: "10px 0 0", fontSize: 13 }}>
                      <div><dt className="card-sub">Change {history.data.change.start_year}–{history.data.change.end_year}</dt>
                        <dd style={{ margin: 0 }}>{metric === "population_total" ? fmtPeople(history.data.change.absolute) : history.data.change.absolute.toFixed(2)} ({fmtPct(history.data.change.percent, 1, true)})</dd></div>
                      {metric === "population_total" && history.data.change.cagr_percent !== null && (
                        <div><dt className="card-sub">Compound annual growth (derived)</dt><dd style={{ margin: 0 }}>{fmtPct(history.data.change.cagr_percent, 2)}</dd></div>
                      )}
                    </dl>
                  )}
                  <p className="note">Values are {history.data.value_kind}s from {history.data.provenance.publisher} ({history.data.provenance.release_version}); derived figures are calculated deterministically.</p>
                </>
              )}
          </div>
        </section>
      </div>
    </>
  );
}
