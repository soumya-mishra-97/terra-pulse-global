"""Deterministic data tools the agents may call. Each wraps PopulationService; none uses an LLM.

TOOL_REGISTRY documents the tool surface (it is shown on the "How the Agent Works" page).
"""

from __future__ import annotations

from app.domain.models import DataSource
from app.services.population import PopulationService

TOOL_REGISTRY = {
    "get_country_series": "Population and demographic indicator series for one country or aggregate, by year range.",
    "get_ranking_inputs": "Population at two reference years plus latest growth rate for every country (no aggregates).",
    "get_provenance": "Active dataset name, publisher, release, licence, checksum and freshness.",
    "retrieve_methodology": "BM25 search over approved methodology documents (untrusted text, sanitised).",
    "calculate_change": "Absolute change, percent change and CAGR between two years (pure Python).",
    "rank_countries": "Deterministic ranking by a metric with tie-breaking by ISO3 code.",
}


class DataTools:
    def __init__(self, service: PopulationService) -> None:
        self.svc = service

    def get_provenance(self, reference_year: int | None) -> dict:
        src: DataSource = self.svc.source()
        p = self.svc.provenance(src, reference_year)
        return {"label": "S1", **p.model_dump(mode="json")}

    def get_country_series(self, iso3: str, metrics: list[str], start: int | None, end: int | None) -> dict:
        c = self.svc.country(iso3)
        out = {m: self.svc.series(c.iso3, m, start, end) for m in metrics}
        return {"iso3": c.iso3, "name": c.name, "is_aggregate": c.is_aggregate, "region_code": c.region_code,
                "series": out}

    def get_ranking_inputs(self, start: int, end: int) -> dict:
        countries = {c.iso3: c.name for c in self.svc.all_countries()}
        v0 = self.svc.values_for_year("population_total", start)
        v1 = self.svc.values_for_year("population_total", end)
        both = [k for k in countries if k in v0 and k in v1]  # same reference years only
        pop_start = {k: v0[k] for k in both}
        pop_end = {k: v1[k] for k in both}
        return {"names": countries, "start": pop_start, "end": pop_end,
                "world": self.svc.series("WLD", "population_total", start, end)}
