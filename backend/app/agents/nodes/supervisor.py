"""Supervisor Agent: validates the request and plans which specialist agents run."""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.nodes.common import AgentDeps, time_left, traced
from app.agents.planner import PLANNER_SYSTEM, build_name_index, parse_llm_plan, rules_plan
from app.domain.errors import DataUnavailableError
from app.integrations.llm import LLMError
from app.services.population import METRICS


def make_supervisor(deps: AgentDeps):
    @traced("supervisor", "Supervisor Agent")
    def supervisor(state: dict) -> dict:
        question = state["question"].strip()
        countries = deps.service.all_countries(include_aggregates=True)
        try:
            latest = deps.service.repo.latest_year(deps.service.source().id, "population_total")
        except DataUnavailableError:
            latest = None  # no dataset imported: plan anyway; the Data Agent reports the gap
        latest = latest or datetime.now(UTC).year - 1
        plan = rules_plan(question, countries, latest)
        detail = f"rules plan: intent={plan['intent']}"
        # Claude may also rescue questions the keyword rules refused ("How do India and Sri Lanka differ?");
        # its plan is still validated and can only select deterministic tools.
        if deps.llm is not None and time_left(state) > 2 * deps.settings.llm_timeout_seconds:
            try:
                res = deps.llm.generate(PLANNER_SYSTEM.format(metrics=", ".join(METRICS)), question, max_tokens=300)
                llm_plan = parse_llm_plan(res.text, plan, build_name_index(countries), METRICS, latest)
                if llm_plan is not None:
                    plan, detail = llm_plan, f"claude plan accepted: intent={llm_plan['intent']}"
                else:
                    detail += " (claude plan rejected by validation)"
            except LLMError as exc:
                detail += f" (claude planner unavailable: {exc})"
        steps = [a for a, on in (("data", plan["needs_data"]), ("analysis", plan["needs_analysis"]),
                                 ("research", plan["needs_research"])) if on]
        return {"plan": plan, "research_attempts": 0, "generation_attempts": 0,
                "_detail": f"{detail}; agents: {', '.join(steps) or 'none'}"}

    return supervisor
