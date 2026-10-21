// Mirrors backend Pydantic schemas (app/schemas/*.py).

export interface Freshness { status: "fresh" | "stale" | "unknown"; age_days: number | null; stale_after_days: number }

export interface Provenance {
  source_id: number;
  snapshot_id: string;
  dataset_name: string;
  publisher: string;
  source_url: string;
  landing_page: string | null;
  license: string;
  release_version: string;
  imported_at: string;
  reference_date: string | null;
  value_kind: string;
  uncertainty_note: string;
  freshness: Freshness;
  is_synthetic: boolean;
  data_label: string;
}

export interface YearValue { year: number; value: number }
export interface RankedCountry { iso3: string; name: string; value: number; year: number }

export interface WorldSummary {
  estimate: { value: number; reference_date: string; value_kind: string; method: string; lower: number | null; upper: number | null; uncertainty_note: string };
  previous: YearValue | null;
  annual_change: number | null;
  annual_change_percent: number | null;
  growth_rate_percent: YearValue | null;
  history: YearValue[];
  top_countries: RankedCountry[];
  fastest_growing: RankedCountry[];
  country_count: number;
  coverage: Record<string, unknown>;
  illustrative_counter: { label: string; base_value: number; base_date: string; annual_growth_percent: number; value_kind: string; assumptions: string[] } | null;
  provenance: Provenance;
}

export interface CountryListItem {
  iso3: string; iso2: string | null; name: string; region: string | null; region_code: string | null; income_level: string | null;
  population: number | null; population_year: number | null; growth_percent: number | null; growth_year: number | null;
  share_of_world_percent: number | null;
}
export interface CountryPage { items: CountryListItem[]; total: number; limit: number; offset: number; provenance: Provenance }

export interface HistoryResponse {
  iso3: string; name: string; metric: string; unit: string; value_kind: string;
  points: { year: number; value: number; reference_date: string }[];
  change: { start_year: number; end_year: number; absolute: number; percent: number; cagr_percent: number | null } | null;
  provenance: Provenance;
}

export interface RegionStat {
  code: string; name: string; year: number | null; population: number | null; growth_percent: number | null;
  age_0_14_pct: number | null; age_15_64_pct: number | null; age_65_plus_pct: number | null; urban_pct: number | null;
  fertility_rate: number | null; life_expectancy_years: number | null;
}
export interface RegionsResponse { regions: RegionStat[]; world: RegionStat | null; provenance: Provenance }

export interface Health { status: string; database: string; dataset_loaded: boolean; llm_mode: "claude" | "demo"; llm_model: string | null; version: string }

export interface Fact { id: string; label: string; value: number; display: string; unit: string; year: number | null; scope: string; metric: string; kind: string; source: string }
export interface Citation { label: string; kind: "dataset" | "document"; title: string | null; publisher: string | null; url: string | null; published: string | null; reference_date?: string | null; license?: string | null; section?: string | null }
export interface TraceStep { node: string; agent: string; status: "ok" | "skipped" | "degraded" | "failed"; latency_ms: number; detail: string }
export interface ChartSpec {
  type: "line" | "bar"; title: string; unit: string; years?: number[];
  series: ({ name: string; points: YearValue[] } | { name: string; value: number })[];
}
export interface ChatResponse {
  run_id: string; answer: string; mode: "claude" | "demo" | "fallback"; model: string | null; refused: boolean;
  plan: { intent: string; countries: string[]; planner: string; start_year: number | null; end_year: number | null } | null;
  key_findings: string[]; facts: Fact[]; citations: Citation[]; limitations: string[];
  validation: { evidence?: { sufficient: boolean; checks: { name: string; passed: boolean; detail: string; severity: string }[] } | null; output?: { passed: boolean; unsupported_numbers?: string[] } | null };
  chart: ChartSpec | null; trace: TraceStep[]; latency_ms: number; disclaimer: string;
}

export interface Architecture {
  graph: { nodes: { id: string; agent: string; kind: string; does: string }[]; edges: [string, string][] };
  tools: Record<string, string>; mode: "claude" | "demo"; model: string | null; documents: string[];
}

export type ReportStatus = "queued" | "running" | "completed" | "failed" | "blocked";
export interface ReportCountry { iso3: string; iso2: string | null; name: string; region: string | null; income_level: string | null; flag: string; latest_population_year: number | null }
export interface ReportOptions {
  sections: { id: string; title: string; required: boolean }[];
  groups: Record<string, { label: string; sections: string[] }>;
  periods: Record<string, { label: string; years: number | null }>;
  required: string[];
}
export interface ReportSummary {
  id: string; country_code: string; country_name: string; period: string; sections: string[]; status: ReportStatus;
  progress: number; current_step: string | null; error: string | null; validation_status: string | null; mode: string | null;
  created_at: string; generated_at: string | null; downloads: Record<string, string>;
}
export interface ReportMetric { label: string; value: string; year: number | null; fact_id: string | null; kind: string }
export interface ReportSection {
  id: string; number: number; title: string; status: "ok" | "partial" | "unavailable"; summary_points: string[]; implications?: string[];
  metrics: ReportMetric[]; table: { columns: string[]; rows: string[][] } | null; chart: ChartSpec | null; notes: string[];
  unavailable: string[]; citations: string[]; narrative: string | null; narrative_source: string | null;
}
export interface ReportContent {
  title: string; country: { iso3: string; iso2: string | null; name: string; region: string | null; income_level: string | null; capital: string | null; flag: string };
  period: { key: string; label: string; start_year: number; end_year: number }; generated_at: string; data_reference_date: string | null;
  mode: string; model: string | null; disclaimer: string; provenance: Provenance; sections: ReportSection[]; facts: Fact[];
  sources: { label: string; kind: string; title: string; publisher: string | null; url: string | null; published: string | null; reference: string | null }[];
  validation: { status: string; checks: { name: string; passed: boolean; detail: string; severity: string }[] };
  limitations: string[];
}
export interface ReportDetail extends ReportSummary { content: ReportContent | null; sources: unknown[]; runs: { attempt: number; status: string; trace: TraceStep[]; error: string | null }[] }
export interface ReportPage { items: ReportSummary[]; total: number; limit: number; offset: number }
