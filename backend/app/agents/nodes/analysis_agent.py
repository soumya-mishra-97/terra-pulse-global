"""Analysis Agent: deterministic growth, comparison and ranking calculations (no LLM)."""

from __future__ import annotations

from app.agents.analysis import FactBook, analyse_compare, analyse_ranking, analyse_scope, line_chart
from app.agents.nodes.common import AgentDeps, traced


def make_analysis_agent(deps: AgentDeps):
    @traced("analysis_agent", "Analysis Agent")
    def analysis_agent(state: dict) -> dict:
        plan, data = state["plan"], state.get("data") or {}
        if data.get("error") or not data:
            return {"facts": [], "key_findings": [], "chart": None, "_status": "skipped", "_detail": "no data"}
        fb = FactBook()
        start, end = data["start"], data["end"]
        findings: list[str] = []
        issues = list(data.get("issues", []))
        chart = None
        if plan["intent"] == "ranking":
            res = analyse_ranking(fb, data["ranking"], start, end)
            findings, chart = res["findings"], res["chart"]
        elif plan["intent"] == "compare":
            res = analyse_compare(fb, data["scopes"], plan["metrics"], start, end)
            findings, issues = res["findings"], issues + res["issues"]
            chart = line_chart("Population", {s["name"]: s["series"].get("population_total", {}) for s in data["scopes"]},
                               "persons")
        else:
            for s in data["scopes"]:
                summ = analyse_scope(fb, s["name"], s["iso3"], s["series"], plan["metrics"], start, end)
                findings += summ["findings"]
                for m in summ.get("missing", []):
                    issues.append(f"{m} is unavailable for {s['name']} in {start}-{end}.")
            chart = line_chart("Population", {s["name"]: s["series"].get("population_total", {}) for s in data["scopes"]},
                               "persons")
        return {"facts": fb.facts, "key_findings": findings, "chart": chart,
                "data": {**data, "issues": issues}, "_detail": f"{len(fb.facts)} facts computed"}

    return analysis_agent
