from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

    @field_validator("question")
    @classmethod
    def strip_controls(cls, v: str) -> str:
        cleaned = "".join(ch for ch in v if ch.isprintable() or ch in "\n\t").strip()
        if len(cleaned) < 3:
            raise ValueError("question is too short")
        return cleaned


class FactOut(BaseModel):
    id: str
    label: str
    value: float
    display: str
    unit: str
    year: int | None
    scope: str
    metric: str
    kind: str
    source: str


class CitationOut(BaseModel):
    label: str
    kind: Literal["dataset", "document"]
    title: str | None
    publisher: str | None
    url: str | None
    published: str | None
    reference_date: str | None = None
    license: str | None = None
    section: str | None = None


class TraceStepOut(BaseModel):
    node: str
    agent: str
    status: str
    latency_ms: float
    detail: str = ""


class ChatResponse(BaseModel):
    run_id: str
    answer: str
    mode: Literal["claude", "demo", "fallback"]
    model: str | None
    refused: bool
    plan: dict | None
    key_findings: list[str]
    facts: list[FactOut]
    citations: list[CitationOut]
    limitations: list[str]
    validation: dict
    chart: dict | None
    trace: list[TraceStepOut]
    latency_ms: float
    disclaimer: str
