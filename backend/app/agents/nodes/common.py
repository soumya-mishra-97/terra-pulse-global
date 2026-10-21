from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.agents.tools import DataTools
from app.config import Settings
from app.integrations.llm import LLMClient
from app.knowledge.retriever import Retriever
from app.observability import metrics
from app.services.population import PopulationService

log = logging.getLogger("terrapulse.agents")


@dataclass
class AgentDeps:
    service: PopulationService
    tools: DataTools
    retriever: Retriever
    llm: LLMClient | None
    settings: Settings


def time_left(state: dict) -> float:
    return state.get("deadline", float("inf")) - time.monotonic()


def traced(node: str, agent: str) -> Callable:
    """Wrap a node: time it, log it, and turn exceptions into a 'failed' trace step (partial failure)."""

    def deco(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            start = time.perf_counter()
            try:
                update = dict(fn(state) or {})
                status = update.pop("_status", "ok")
                detail = update.pop("_detail", "")
            except Exception as exc:  # node failure must not crash the graph
                log.exception("agent node failed", extra={"node": node})
                update, status, detail = {}, "failed", f"{type(exc).__name__}: {str(exc)[:160]}"
            ms = (time.perf_counter() - start) * 1000
            metrics.incr(f"agent.node.{node}.{status}")
            metrics.observe(f"agent.node.{node}", ms)
            log.info("agent node", extra={"node": node, "agent": agent, "status": status, "latency_ms": round(ms, 1)})
            update["trace"] = [{"node": node, "agent": agent, "status": status, "latency_ms": round(ms, 1),
                                "detail": detail}]
            return update

        return wrapper

    return deco
