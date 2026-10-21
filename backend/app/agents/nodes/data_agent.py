"""Data Agent: fetches series and provenance through deterministic tools (PostgreSQL-backed)."""

from __future__ import annotations

from app.agents.nodes.common import AgentDeps, traced
from app.domain.errors import DataUnavailableError, NotFoundError

FIRST_YEAR = 2000


def make_data_agent(deps: AgentDeps):
    @traced("data_agent", "Data Agent")
    def data_agent(state: dict) -> dict:
        plan = state["plan"]
        start, end = plan.get("start_year"), plan.get("end_year")
        issues = []
        if start is not None and start < FIRST_YEAR:
            issues.append(f"The imported snapshot starts in {FIRST_YEAR}; earlier years are not available.")
            start = FIRST_YEAR
        try:
            provenance = deps.tools.get_provenance(end)
            if plan["intent"] == "ranking":
                data = {"ranking": deps.tools.get_ranking_inputs(start, end), "start": start, "end": end}
            else:
                scopes = [deps.tools.get_country_series(iso3, plan["metrics"], start, end) for iso3 in plan["countries"]]
                data = {"scopes": scopes, "start": start, "end": end}
        except (DataUnavailableError, NotFoundError) as exc:
            return {"data": {"error": str(exc)}, "_status": "degraded", "_detail": str(exc)}
        data["issues"] = issues
        n = len(data.get("scopes", [])) or len(data.get("ranking", {}).get("end", {}))
        return {"data": data, "provenance": provenance, "_detail": f"loaded {n} scope(s), {start}-{end}"}

    return data_agent
