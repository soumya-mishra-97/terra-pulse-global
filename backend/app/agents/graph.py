"""LangGraph wiring for the TerraPulse Copilot (multi-agent workflow).

    START -> supervisor --(out_of_scope)--------------------------------------> finalize -> END
                        --(needs data)--> data_agent -> analysis_agent --+
                        --(methodology)----------------------------------+--> research_agent
    research_agent -> evidence_validator --(no docs, retry<2)--> research_agent
                                         --(otherwise)---------> responder -> output_validator
    output_validator --(failed, retry<2)--> responder ; otherwise -> finalize -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.analysis_agent import make_analysis_agent
from app.agents.nodes.common import AgentDeps
from app.agents.nodes.data_agent import make_data_agent
from app.agents.nodes.finalize import make_finalize
from app.agents.nodes.research_agent import make_research_agent
from app.agents.nodes.responder import make_responder
from app.agents.nodes.supervisor import make_supervisor
from app.agents.nodes.validation_agent import make_evidence_validator, make_output_validator
from app.agents.state import CopilotState


def route_after_supervisor(state: CopilotState) -> str:
    plan = state.get("plan")
    if not plan or plan["intent"] == "out_of_scope":
        return "finalize"
    return "data_agent" if plan["needs_data"] else "research_agent"


def route_after_analysis(state: CopilotState) -> str:
    return "research_agent" if state["plan"]["needs_research"] else "evidence_validator"


def route_after_evidence(state: CopilotState) -> str:
    return "research_agent" if (state.get("evidence") or {}).get("retry_research") else "responder"


def route_after_output(state: CopilotState) -> str:
    v = state.get("output_validation") or {}
    if not v.get("passed") and not v.get("replaced_with_template") and state.get("generation_feedback") \
            and state.get("mode") == "claude":
        return "responder"
    return "finalize"


def build_copilot_graph(deps: AgentDeps):
    g = StateGraph(CopilotState)
    g.add_node("supervisor", make_supervisor(deps))
    g.add_node("data_agent", make_data_agent(deps))
    g.add_node("analysis_agent", make_analysis_agent(deps))
    g.add_node("research_agent", make_research_agent(deps))
    g.add_node("evidence_validator", make_evidence_validator(deps))
    g.add_node("responder", make_responder(deps))
    g.add_node("output_validator", make_output_validator(deps))
    g.add_node("finalize", make_finalize(deps))

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route_after_supervisor, ["data_agent", "research_agent", "finalize"])
    g.add_edge("data_agent", "analysis_agent")
    g.add_conditional_edges("analysis_agent", route_after_analysis, ["research_agent", "evidence_validator"])
    g.add_edge("research_agent", "evidence_validator")
    g.add_conditional_edges("evidence_validator", route_after_evidence, ["research_agent", "responder"])
    g.add_edge("responder", "output_validator")
    g.add_conditional_edges("output_validator", route_after_output, ["responder", "finalize"])
    g.add_edge("finalize", END)
    return g.compile()


GRAPH_DESCRIPTION = {
    "nodes": [
        {"id": "supervisor", "agent": "Supervisor Agent", "kind": "planner",
         "does": "Validates the question, resolves countries/metrics/period, chooses which agents run. "
                 "Uses Claude to propose a plan when configured; the plan is validated against an allowlist."},
        {"id": "data_agent", "agent": "Data Agent", "kind": "tool",
         "does": "Loads series and provenance from PostgreSQL through PopulationService. No LLM."},
        {"id": "analysis_agent", "agent": "Analysis Agent", "kind": "deterministic",
         "does": "Computes change, CAGR, shares and rankings in Python and numbers each result as a fact (F1..)."},
        {"id": "research_agent", "agent": "Research Agent", "kind": "rag",
         "does": "BM25 retrieval over approved methodology documents; strips instruction-like lines."},
        {"id": "evidence_validator", "agent": "Validation Agent", "kind": "rules",
         "does": "Checks provenance, coverage, comparability, freshness; retries research when evidence is missing."},
        {"id": "responder", "agent": "Response Generator", "kind": "llm",
         "does": "Claude writes a grounded explanation citing [F#]/[D#]; deterministic template in demo mode."},
        {"id": "output_validator", "agent": "Validation Agent", "kind": "rules",
         "does": "Rejects numbers or citations not present in the evidence; one regeneration, then template fallback."},
        {"id": "finalize", "agent": "Supervisor Agent", "kind": "synthesis",
         "does": "Attaches citations, limitations, mode/model metadata and chart data."},
    ],
    "edges": [
        ["START", "supervisor"], ["supervisor", "data_agent"], ["supervisor", "research_agent"],
        ["supervisor", "finalize"], ["data_agent", "analysis_agent"], ["analysis_agent", "research_agent"],
        ["analysis_agent", "evidence_validator"], ["research_agent", "evidence_validator"],
        ["evidence_validator", "research_agent"], ["evidence_validator", "responder"],
        ["responder", "output_validator"], ["output_validator", "responder"], ["output_validator", "finalize"],
        ["finalize", "END"],
    ],
}
