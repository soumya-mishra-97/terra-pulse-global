"""Copilot application service: runs the LangGraph workflow and records an auditable agent run."""

from __future__ import annotations

import time
import uuid

from sqlalchemy.orm import Session

from app.agents.graph import build_copilot_graph
from app.agents.nodes.common import AgentDeps
from app.agents.tools import DataTools
from app.config import Settings
from app.integrations.llm import LLMClient
from app.knowledge.retriever import Retriever
from app.observability import correlation_id_var, metrics
from app.repositories.audit import AuditRepository
from app.repositories.population import PopulationRepository
from app.schemas.copilot import ChatResponse
from app.services.population import PopulationService

COPILOT_DEADLINE_SECONDS = 150  # planner + up to two generations, each bounded by the LLM timeout
DISCLAIMER = ("Population figures are dated estimates from the cited source, not real-time counts. "
              "AI-generated text explains the figures but never changes them.")


class CopilotService:
    def __init__(self, session: Session, settings: Settings, retriever: Retriever, llm: LLMClient | None) -> None:
        self.session = session
        self.settings = settings
        service = PopulationService(PopulationRepository(session), settings.stale_after_days)
        self.deps = AgentDeps(service=service, tools=DataTools(service), retriever=retriever, llm=llm, settings=settings)

    def ask(self, question: str, user_id: str) -> ChatResponse:
        run_id = uuid.uuid4().hex
        start = time.perf_counter()
        graph = build_copilot_graph(self.deps)
        state = graph.invoke(
            {"question": question, "user_id": user_id, "correlation_id": correlation_id_var.get(),
             "deadline": time.monotonic() + COPILOT_DEADLINE_SECONDS, "trace": []},
            {"recursion_limit": 25},
        )
        latency = (time.perf_counter() - start) * 1000
        metrics.incr(f"copilot.mode.{state.get('mode', 'demo')}")
        metrics.observe("copilot.latency", latency)
        validation = {"evidence": state.get("evidence"), "output": state.get("output_validation")}
        AuditRepository(self.session).save_agent_run(
            id=run_id, run_type="copilot", user_id=user_id, correlation_id=correlation_id_var.get(),
            input={"question": question, "plan": state.get("plan")}, mode=state.get("mode", "demo"),
            model=state.get("model"), status="refused" if state.get("refused") else "completed",
            trace=state.get("trace", []), validation=validation, latency_ms=latency,
        )
        self.session.commit()
        return ChatResponse(
            run_id=run_id, answer=state.get("answer", ""), mode=state.get("mode", "demo"), model=state.get("model"),
            refused=bool(state.get("refused")), plan=state.get("plan"), key_findings=state.get("key_findings") or [],
            facts=state.get("facts") or [], citations=state.get("citations") or [],
            limitations=state.get("limitations") or [], validation=validation, chart=state.get("chart"),
            trace=state.get("trace") or [], latency_ms=round(latency, 1), disclaimer=DISCLAIMER,
        )
