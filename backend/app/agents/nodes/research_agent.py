"""Research Agent: retrieves approved methodology passages (RAG). Retrieved text is untrusted."""

from __future__ import annotations

from dataclasses import asdict

from app.agents.nodes.common import AgentDeps, traced
from app.domain.formatting import METRIC_LABELS


def make_research_agent(deps: AgentDeps):
    @traced("research_agent", "Research Agent")
    def research_agent(state: dict) -> dict:
        plan = state["plan"]
        attempt = state.get("research_attempts", 0) + 1
        query = plan.get("research_query", state["question"])
        if attempt > 1:  # broaden on retry: add metric names and generic methodology terms
            query += " " + " ".join(METRIC_LABELS.get(m, m) for m in plan.get("metrics", []))
            query += " population estimates methodology definition"
        k = 4 if plan["intent"] == "methodology" else 3
        docs = [asdict(d) for d in deps.retriever.retrieve(query, k=k)]
        flagged = sum(len(d["flagged_lines"]) for d in docs)
        detail = f"attempt {attempt}: {len(docs)} passage(s)" + (f", {flagged} suspicious line(s) removed" if flagged else "")
        return {"documents": docs, "research_attempts": attempt, "_detail": detail,
                "_status": "ok" if docs else "degraded"}

    return research_agent
