import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { AgeRadar, TrendChart, UrbanSplit } from "../components/charts";
import { ProvenanceBanner } from "../components/ProvenanceBanner";
import { RegionMatrix } from "../components/RegionMatrix";
import { IllustrativeCounter, StatTile } from "../components/StatTile";
import { ErrorState, NoDataset, Skeleton } from "../components/States";
import { WorldMap } from "../components/WorldMap";
import { fmtDate, fmtExact, fmtPct, fmtPeople } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export function Overview() {
  const navigate = useNavigate();
  const summary = useAsync(() => api.summary());
  const regions = useAsync(() => api.regions());
  const countries = useAsync(() => api.countries({ limit: 300 }));

  if (summary.error) {
    return summary.error instanceof ApiError && summary.error.status === 503
      ? <div className="card"><NoDataset /></div>
      : <div className="card"><ErrorState error={summary.error} onRetry={summary.reload} /></div>;
  }
  const s = summary.data;
  return (
    <>
      {s ? <ProvenanceBanner p={s.provenance} /> : <Skeleton height={42} />}

      <div className="grid kpis">
        {s ? (
          <>
            <StatTile title="World population" value={fmtPeople(s.estimate.value)} label={`Midyear estimate · ${fmtDate(s.estimate.reference_date)}`}
              delta={<span title={fmtExact(s.estimate.value)}>{fmtExact(s.estimate.value)} people [S1]</span>} />
            <StatTile title="Annual change" value={s.annual_change !== null ? `+${fmtPeople(s.annual_change)}` : "Data unavailable"}
              label={s.previous ? `${s.previous.year} → ${s.estimate.reference_date.slice(0, 4)} · derived` : "Derived"}
              delta={s.annual_change_percent !== null ? `${fmtPct(s.annual_change_percent, 2, true)} year on year` : undefined} />
            <StatTile title="Growth rate" value={fmtPct(s.growth_rate_percent?.value, 2)}
              label={`Source exponential rate · ${s.growth_rate_percent?.year ?? ""}`}
              delta={`${s.country_count} economies covered`} />
            {s.illustrative_counter
              ? <IllustrativeCounter c={s.illustrative_counter} />
              : <StatTile title="Illustrative counter" value="Data unavailable" label="No growth rate in the source" />}
          </>
        ) : Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={140} />)}
      </div>

      <div className="grid main-map">
        <div className="grid" style={{ gridTemplateRows: "auto auto" }}>
          <div className="grid two">
            <section className="card" aria-labelledby="urban-title">
              <div className="card-head">
                <div><h3 className="card-title" id="urban-title">Urban vs rural</h3><div className="card-sub">World, latest year</div></div>
                <span className="badge-count">2</span>
              </div>
              {regions.data ? <UrbanSplit urban={regions.data.world?.urban_pct ?? null} year={regions.data.world?.year ?? null} /> : <Skeleton height={230} />}
            </section>
            <section className="card" aria-labelledby="age-title">
              <div className="card-head">
                <div><h3 className="card-title" id="age-title">Age structure by region</h3><div className="card-sub">Share aged 0-14 vs 65+</div></div>
                <span className="badge-count">2</span>
              </div>
              {regions.data ? <AgeRadar regions={regions.data.regions} /> : <Skeleton height={230} />}
            </section>
          </div>
          <section className="card" aria-labelledby="trend-title">
            <div className="card-head">
              <div><h3 className="card-title" id="trend-title">World population trend</h3>
                <div className="card-sub">Annual midyear estimates, {s?.history[0]?.year}–{s?.history.at(-1)?.year} · hover for values</div></div>
            </div>
            {s ? <TrendChart data={s.history} /> : <Skeleton height={230} />}
          </section>
        </div>
        <section className="card">
          {countries.data ? <WorldMap items={countries.data.items} onSelect={(iso3) => navigate(`/countries?c=${iso3}`)} />
            : countries.error ? <ErrorState error={countries.error} onRetry={countries.reload} /> : <Skeleton height={460} />}
        </section>
      </div>

      <div className="grid main-map">
        <section className="card" aria-labelledby="matrix-title">
          <div className="card-head">
            <div><h3 className="card-title" id="matrix-title">Regional indicators vs world</h3>
              <div className="card-sub">World Bank regional aggregates · latest year per indicator</div></div>
            <span className="badge-count">7</span>
          </div>
          {regions.data ? <RegionMatrix regions={regions.data.regions} world={regions.data.world} />
            : regions.error ? <ErrorState error={regions.error} onRetry={regions.reload} /> : <Skeleton height={300} />}
        </section>
        <section className="card" aria-labelledby="top-title">
          <div className="card-head">
            <div><h3 className="card-title" id="top-title">Most populous & fastest growing</h3>
              <div className="card-sub">Fastest growing excludes countries under 1M people</div></div>
          </div>
          {s ? (
            <div className="grid two">
              <table className="data">
                <caption className="sr-only">Most populous countries</caption>
                <thead><tr><th>Country</th><th className="num">Population ({s.top_countries[0]?.year})</th></tr></thead>
                <tbody>{s.top_countries.map((c) => (
                  <tr key={c.iso3} className="clickable" onClick={() => navigate(`/countries?c=${c.iso3}`)}>
                    <td>{c.name}</td><td className="num">{fmtPeople(c.value)}</td></tr>))}</tbody>
              </table>
              <table className="data">
                <caption className="sr-only">Fastest growing countries</caption>
                <thead><tr><th>Country</th><th className="num">Growth ({s.fastest_growing[0]?.year})</th></tr></thead>
                <tbody>{s.fastest_growing.map((c) => (
                  <tr key={c.iso3} className="clickable" onClick={() => navigate(`/countries?c=${c.iso3}`)}>
                    <td>{c.name}</td><td className="num pos">{fmtPct(c.value, 2, true)}</td></tr>))}</tbody>
              </table>
            </div>
          ) : <Skeleton height={300} />}
        </section>
      </div>
    </>
  );
}
