import type { Provenance } from "../api/types";
import { fmtDate } from "../lib/format";

/** Shown above every view that displays figures: source, version, reference date, freshness, uncertainty. */
export function ProvenanceBanner({ p }: { p: Provenance }) {
  const fresh = p.freshness.status;
  return (
    <section className="provenance" aria-label="Data provenance">
      {p.is_synthetic && <span className="tag demo">Demo data · synthetic</span>}
      <span className="tag estimate">Estimates · not live counts</span>
      <span>
        Source <strong>{p.publisher}</strong> — {p.dataset_name}{" "}
        {p.landing_page && <a href={p.landing_page} target="_blank" rel="noreferrer noopener">(link)</a>}
      </span>
      <span>Release <strong>{p.release_version}</strong></span>
      <span>Reference date <strong>{fmtDate(p.reference_date)}</strong></span>
      <span>
        Freshness <span className={`tag ${fresh === "stale" ? "stale" : "fresh"}`}>{fresh}</span>
        {p.freshness.age_days !== null && <> · {p.freshness.age_days} days old</>}
      </span>
      <span>Licence <strong>{p.license}</strong></span>
      <span title={p.uncertainty_note}>Uncertainty: {p.uncertainty_note.replace(/\.$/, "")}</span>
    </section>
  );
}
