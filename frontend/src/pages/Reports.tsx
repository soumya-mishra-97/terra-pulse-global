import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError, downloadReport } from "../api/client";
import type { ReportCountry, ReportDetail, ReportOptions, ReportSection, ReportSummary } from "../api/types";
import { SpecChart } from "../components/charts";
import { Icon } from "../components/Icon";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { fmtDate, fmtDateTime } from "../lib/format";
import { useAsync } from "../lib/useAsync";

const DEFAULT_GROUPS = ["population_trends", "demographic_indicators", "research_sources", "charts_comparisons"];

function CountryPicker({ countries, value, onChange }: { countries: ReportCountry[]; value: string; onChange: (iso3: string) => void }) {
  const selected = countries.find((c) => c.iso3 === value);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (q ? countries.filter((c) => c.name.toLowerCase().includes(q) || c.iso3.toLowerCase() === q) : countries).slice(0, 60);
  }, [countries, query]);
  function pick(c: ReportCountry) { onChange(c.iso3); setQuery(""); setOpen(false); }
  return (
    <div className="combo">
      <input id="country" className="input" role="combobox" aria-expanded={open} aria-controls="country-list" aria-autocomplete="list"
        placeholder={selected ? `${selected.flag} ${selected.name}` : "Search a country…"} value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }} onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { setActive((a) => Math.min(a + 1, matches.length - 1)); e.preventDefault(); }
          if (e.key === "ArrowUp") { setActive((a) => Math.max(a - 1, 0)); e.preventDefault(); }
          if (e.key === "Enter" && matches[active]) { pick(matches[active]); e.preventDefault(); }
          if (e.key === "Escape") setOpen(false);
        }} />
      {open && (
        <ul id="country-list" className="combo-list" role="listbox">
          {matches.length === 0 && <li aria-disabled="true">No matching country</li>}
          {matches.map((c, i) => (
            <li key={c.iso3} role="option" aria-selected={i === active} onMouseDown={() => pick(c)}>
              <span aria-hidden="true">{c.flag}</span> {c.name} <span className="note">{c.iso3}</span>
            </li>
          ))}
        </ul>
      )}
      {selected && <div className="note" style={{ marginTop: 4 }}>Selected: {selected.flag} {selected.name} ({selected.iso3}) · population data to {selected.latest_population_year ?? "n/a"}</div>}
    </div>
  );
}

function SectionView({ s }: { s: ReportSection }) {
  return (
    <section id={`sec-${s.id}`} className="report-section" aria-labelledby={`h-${s.id}`}>
      <h3 id={`h-${s.id}`}>{s.number}. {s.title}<span className={`status-pill ${s.status}`}>{s.status}</span></h3>
      {s.narrative && <div className="narrative">{s.narrative}<div className="note" style={{ marginTop: 4 }}>AI-generated explanation · validated against the figures below</div></div>}
      {s.summary_points.length > 0 && <ul>{s.summary_points.map((p) => <li key={p}>{p}</li>)}</ul>}
      {s.implications && s.implications.length > 0 && (
        <><b style={{ fontSize: 13 }}>Implications (rule-based)</b><ul>{s.implications.map((p) => <li key={p}>{p}</li>)}</ul></>
      )}
      {s.metrics.length > 0 && (
        <table className="data" style={{ margin: "8px 0" }}>
          <thead><tr><th>Metric</th><th>Value</th><th>Basis</th></tr></thead>
          <tbody>{s.metrics.map((m, i) => <tr key={i}><td>{m.label}</td><td>{m.value}</td><td className="note">{m.kind}{m.fact_id ? ` [${m.fact_id}]` : ""}</td></tr>)}</tbody>
        </table>
      )}
      {s.chart && <div style={{ margin: "8px 0" }}><SpecChart spec={s.chart} height={220} /></div>}
      {s.table && (
        <details>
          <summary className="note" style={{ cursor: "pointer" }}>Data table ({s.table.rows.length} rows)</summary>
          <div className="table-scroll" style={{ maxHeight: 280 }}>
            <table className="data"><thead><tr>{s.table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{s.table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table>
          </div>
        </details>
      )}
      {s.unavailable.map((u) => <div key={u} className="unavailable">Data unavailable: {u}</div>)}
      {s.notes.map((n) => <div key={n} className="note">Note: {n}</div>)}
      {s.citations.length > 0 && <div className="note">Sources: {s.citations.map((c) => `[${c}]`).join(", ")}</div>}
    </section>
  );
}

function Preview({ report, onRegenerate, onDelete }: { report: ReportDetail; onRegenerate: () => void; onDelete: () => void }) {
  const c = report.content;
  const [dl, setDl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function download(fmt: "pdf" | "md") {
    setDl(fmt); setErr(null);
    try { await downloadReport(report.id, fmt); } catch (e) { setErr((e as Error).message); } finally { setDl(null); }
  }
  if (report.status === "queued" || report.status === "running") {
    return (
      <div className="state" role="status">
        <h3>Generating report for {report.country_name}…</h3>
        <div style={{ width: "min(420px, 100%)" }}><div className="progress"><div style={{ width: `${report.progress}%` }} /></div></div>
        <div className="note">{report.progress}% · {report.current_step ?? report.status}</div>
      </div>
    );
  }
  if (report.status === "failed" || report.status === "blocked" || !c) {
    return (
      <div className="state error" role="alert">
        <h3>{report.status === "blocked" ? "Report blocked by validation" : "Report generation failed"}</h3>
        <div>{report.error ?? "No content was produced."}</div>
        {c && <ul className="note" style={{ textAlign: "left" }}>{c.validation.checks.filter((x) => !x.passed).map((x) => <li key={x.name}>{x.name}: {x.detail}</li>)}</ul>}
        <button className="pill-btn" onClick={onRegenerate}><Icon name="refresh" size={14} /> Regenerate</button>
      </div>
    );
  }
  return (
    <article aria-label={c.title}>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22 }}><span className="flag" aria-hidden="true">{c.country.flag}</span> {c.title}</h2>
          <div className="card-sub">
            {c.country.iso3} · {c.period.label} ({c.period.start_year}–{c.period.end_year}) · generated {fmtDateTime(c.generated_at)} ·
            data reference date {fmtDate(c.data_reference_date)} · narrative: {c.mode}{c.model ? ` (${c.model})` : ""} ·
            validation: {c.validation.status}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="pill-btn primary" onClick={() => download("pdf")} disabled={dl !== null}><Icon name="download" size={14} />{dl === "pdf" ? "Preparing…" : "Download PDF"}</button>
          <button className="pill-btn" onClick={() => download("md")} disabled={dl !== null}><Icon name="file" size={14} />Markdown</button>
          <button className="pill-btn" onClick={onRegenerate}><Icon name="refresh" size={14} />Regenerate</button>
          <button className="icon-btn" onClick={onDelete} aria-label="Delete report"><Icon name="trash" size={15} /></button>
        </div>
      </div>
      {err && <div className="unavailable" role="alert">{err}</div>}
      <div className="provenance" style={{ margin: "10px 0" }}>
        {c.provenance.is_synthetic && <span className="tag demo">Demo data</span>}
        <span className="tag estimate">Estimates</span>
        <span>[S1] <strong>{c.provenance.publisher}</strong> — {c.provenance.dataset_name}, release {c.provenance.release_version} · {c.provenance.license}</span>
      </div>
      <p className="note">{c.disclaimer}</p>
      <div className="report-doc">
        <nav className="toc" aria-label="Table of contents">
          <b>Contents</b>
          <ol>{c.sections.map((s) => <li key={s.id}><a href={`#sec-${s.id}`}>{s.title}</a>{s.status !== "ok" && <span className="note"> · {s.status}</span>}</li>)}</ol>
          <a href="#sec-references">References</a>
        </nav>
        <div>
          {c.sections.map((s) => <SectionView key={s.id} s={s} />)}
          <section id="sec-references" className="report-section">
            <h3>References</h3>
            <ul>{c.sources.map((s) => (
              <li key={s.label}>[{s.label}] {s.url ? <a href={s.url} target="_blank" rel="noreferrer noopener">{s.title}</a> : s.title} — {s.publisher}, {s.published}{s.reference ? ` · ${s.reference}` : ""}</li>
            ))}</ul>
            <h3>Limitations</h3>
            <ul>{c.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </section>
        </div>
      </div>
    </article>
  );
}

export function Reports() {
  const [params, setParams] = useSearchParams();
  const countries = useAsync(() => api.reportCountries());
  const options = useAsync(() => api.reportOptions());
  const [history, setHistory] = useState<ReportSummary[] | null>(null);
  const [historyErr, setHistoryErr] = useState<Error | null>(null);
  const [country, setCountry] = useState(params.get("c") ?? "IND");
  const [period, setPeriod] = useState("10y");
  const [sections, setSections] = useState<Set<string>>(new Set());
  const [current, setCurrent] = useState<ReportDetail | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    if (!options.data) return;
    const init = new Set<string>(options.data.required);
    DEFAULT_GROUPS.forEach((g) => options.data!.groups[g]?.sections.forEach((s) => init.add(s)));
    setSections(init);
  }, [options.data]);

  const loadHistory = () => api.reports(50).then((p) => { setHistory(p.items); setHistoryErr(null); }).catch(setHistoryErr);
  useEffect(() => { void loadHistory(); return () => { if (pollRef.current) clearTimeout(pollRef.current); }; }, []);
  useEffect(() => { const id = params.get("report"); if (id) void open(id); /* eslint-disable-next-line */ }, []);

  async function open(id: string) {
    if (pollRef.current) clearTimeout(pollRef.current);
    try {
      const r = await api.report(id);
      setCurrent(r);
      setParams((p) => { p.set("report", id); return p; }, { replace: true });
      if (r.status === "queued" || r.status === "running") pollRef.current = window.setTimeout(() => void open(id), 1000);
      else void loadHistory();
    } catch (e) {
      setFormErr(e instanceof ApiError && e.status === 404 ? "That report no longer exists." : (e as Error).message);
    }
  }

  async function generate() {
    setSubmitting(true); setFormErr(null);
    try {
      const key = (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`).replace(/[^A-Za-z0-9_.:-]/g, "");
      const r = await api.generateReport({ country_code: country, period, sections: [...sections] }, key);
      await open(r.id);
    } catch (e) { setFormErr((e as Error).message); } finally { setSubmitting(false); }
  }

  async function regenerate() {
    if (!current) return;
    try { const r = await api.regenerateReport(current.id); await open(r.id); } catch (e) { setFormErr((e as Error).message); }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this report and its files?")) return;
    try { await api.deleteReport(id); if (current?.id === id) setCurrent(null); void loadHistory(); }
    catch (e) { setFormErr((e as Error).message); }
  }

  const opts: ReportOptions | null = options.data;
  function toggleGroup(g: string, on: boolean) {
    const next = new Set(sections);
    opts!.groups[g].sections.forEach((s) => (on ? next.add(s) : !opts!.required.includes(s) && next.delete(s)));
    setSections(next);
  }

  return (
    <div className="report-layout">
      <div className="grid">
        <section className="card" aria-labelledby="gen-title">
          <h3 className="card-title" id="gen-title" style={{ marginBottom: 12 }}>Country Intelligence Report</h3>
          {countries.error ? <ErrorState error={countries.error} onRetry={countries.reload} /> : !countries.data || !opts ? <Skeleton height={380} /> : (
            <form onSubmit={(e) => { e.preventDefault(); void generate(); }}>
              <div className="form-row"><label htmlFor="country">Select country</label>
                <CountryPicker countries={countries.data} value={country} onChange={setCountry} /></div>
              <div className="form-row"><label htmlFor="period">Reporting period</label>
                <select id="period" className="select" value={period} onChange={(e) => setPeriod(e.target.value)}>
                  {Object.entries(opts.periods).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select></div>
              <fieldset>
                <legend>Include in report</legend>
                {Object.entries(opts.groups).map(([g, info]) => {
                  const on = info.sections.every((s) => sections.has(s));
                  return (
                    <label key={g} className="check">
                      <input type="checkbox" checked={on} onChange={(e) => toggleGroup(g, e.target.checked)} />
                      <span>{info.label}{g === "future_projections" && <small>Shown as unavailable unless an official projection dataset is loaded</small>}</span>
                    </label>
                  );
                })}
                <details style={{ marginTop: 6 }}>
                  <summary className="note" style={{ cursor: "pointer" }}>Customise sections ({sections.size}/16)</summary>
                  {opts.sections.map((s) => (
                    <label key={s.id} className="check">
                      <input type="checkbox" checked={sections.has(s.id)} disabled={s.required}
                        onChange={(e) => { const n = new Set(sections); if (e.target.checked) n.add(s.id); else n.delete(s.id); setSections(n); }} />
                      <span>{s.title}{s.required && <small>Always included</small>}</span>
                    </label>
                  ))}
                </details>
              </fieldset>
              {formErr && <div className="unavailable" role="alert" style={{ marginBottom: 10 }}>{formErr}</div>}
              <button className="pill-btn primary" type="submit" disabled={submitting || !country} style={{ width: "100%", justifyContent: "center" }}>
                <Icon name="sparkle" size={15} />{submitting ? "Submitting…" : "Generate report"}
              </button>
            </form>
          )}
        </section>
        <section className="card" aria-labelledby="hist-title">
          <h3 className="card-title" id="hist-title">Report history</h3>
          {historyErr ? <ErrorState error={historyErr} onRetry={() => void loadHistory()} /> : !history ? <Skeleton height={120} /> :
            history.length === 0 ? <EmptyState title="No reports yet">Generated reports appear here.</EmptyState> : (
              <div>{history.map((h) => (
                <div key={h.id} className="history-item">
                  <button className="tab" style={{ border: 0, textAlign: "left", padding: 0 }} onClick={() => void open(h.id)}>
                    <b style={{ color: "var(--text-primary)" }}>{h.country_name}</b>
                    <div className="note">{h.period} · {fmtDateTime(h.created_at)}</div>
                  </button>
                  <span className={`status-pill ${h.status}`}>{h.status}</span>
                </div>
              ))}</div>
            )}
        </section>
      </div>
      <section className="card" aria-label="Report preview">
        {current ? <Preview report={current} onRegenerate={() => void regenerate()} onDelete={() => void remove(current.id)} /> : (
          <EmptyState title="No report selected">
            Choose a country, period and sections, then generate. Reports use verified dataset figures; missing indicators are
            marked "Data unavailable" rather than estimated.
          </EmptyState>
        )}
      </section>
    </div>
  );
}
