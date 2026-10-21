import { useEffect, useState } from "react";
import type { WorldSummary } from "../api/types";
import { fmtDate, fmtExact, illustrativeValue } from "../lib/format";

export function StatTile({ title, value, label, delta, badge }: {
  title: string; value: string; label: string; delta?: React.ReactNode; badge?: React.ReactNode;
}) {
  return (
    <article className="card stat" aria-label={title}>
      <div className="card-head">
        <h3 className="card-title">{title}</h3>
        {badge}
      </div>
      <div className="value">{value}</div>
      <div className="label">{label}</div>
      {delta && <div className="delta">{delta}</div>}
    </article>
  );
}

/** Animated counter. Clearly labelled as an illustrative projection with its assumptions. */
export function IllustrativeCounter({ c }: { c: NonNullable<WorldSummary["illustrative_counter"]> }) {
  const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, [reduce]);
  const v = illustrativeValue(c.base_value, c.base_date, c.annual_growth_percent, now);
  return (
    <article className="card stat" aria-label="Illustrative projection counter">
      <div className="card-head">
        <h3 className="card-title">Illustrative counter</h3>
        <span className="tag pill-tag illustrative">Not official</span>
      </div>
      <div className="counter-value" aria-live="off">{fmtExact(v)}</div>
      <div className="label">{c.label}</div>
      <details className="assumptions">
        <summary>Assumptions (from {fmtDate(c.base_date)} estimate)</summary>
        <ul>{c.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      </details>
    </article>
  );
}
