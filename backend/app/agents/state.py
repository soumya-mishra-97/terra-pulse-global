"""Typed LangGraph state for the Copilot and report workflows."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

Intent = Literal["world", "country", "compare", "ranking", "methodology", "out_of_scope"]


class Plan(TypedDict, total=False):
    intent: Intent
    countries: list[str]  # ISO3 codes (may include aggregates such as WLD or SAS)
    metrics: list[str]
    start_year: int | None
    end_year: int | None
    needs_data: bool
    needs_analysis: bool
    needs_research: bool
    research_query: str
    planner: Literal["rules", "claude"]
    unresolved: list[str]


class Fact(TypedDict):
    id: str  # "F1"
    label: str
    value: float
    display: str
    unit: str
    year: int | None
    scope: str
    metric: str
    kind: str  # estimate | derived
    source: str  # "S1"


class TraceStep(TypedDict, total=False):
    node: str
    agent: str
    status: Literal["ok", "skipped", "degraded", "failed"]
    latency_ms: float
    detail: str


class CopilotState(TypedDict, total=False):
    # input
    question: str
    user_id: str
    correlation_id: str
    deadline: float  # monotonic seconds; nodes skip optional work past it
    # supervisor
    plan: Plan
    # data + analysis agents
    provenance: dict
    data: dict
    facts: list[Fact]
    key_findings: list[str]
    chart: dict | None
    # research agent
    documents: list[dict]
    research_attempts: int
    # validation agent
    evidence: dict
    # responder
    answer: str
    mode: Literal["claude", "demo", "fallback"]
    model: str | None
    generation_attempts: int
    generation_feedback: str
    output_validation: dict
    # final
    limitations: list[str]
    citations: list[dict]
    refused: bool
    trace: Annotated[list[TraceStep], operator.add]
