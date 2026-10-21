"""Response Generator: Claude (via LangChain) when configured, deterministic template otherwise."""

from __future__ import annotations

import re

from app.agents.nodes.common import AgentDeps, time_left, traced
from app.agents.prompts import COPILOT_SYSTEM, copilot_user_prompt
from app.integrations.llm import LLMError


def _first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return " ".join(parts[:n])


def template_answer(state: dict) -> str:
    """Deterministic answer built only from computed findings and retrieved passages."""
    plan = state.get("plan") or {}
    evidence = state.get("evidence") or {}
    findings = state.get("key_findings") or []
    docs = state.get("documents") or []
    if not evidence.get("sufficient", False):
        missing = [c["detail"] for c in evidence.get("checks", []) if not c["passed"] and c["severity"] == "error"]
        return ("I can't answer this reliably: the required evidence is missing. "
                + ("Details: " + "; ".join(missing) + ". " if missing else "")
                + "I only answer from TerraPulse's imported dataset and approved methodology documents.")
    parts: list[str] = []
    if plan.get("intent") == "methodology":
        for d in docs[:3]:
            parts.append(f"{_first_sentences(d['text'], 2)} [{d['label']}]")
    else:
        parts += findings[:6]
        if docs:
            parts.append(f"Context: {_first_sentences(docs[0]['text'], 1)} [{docs[0]['label']}]")
    return "\n\n".join(parts) if parts else "No supporting evidence was found for this question."


def make_responder(deps: AgentDeps):
    @traced("responder", "Response Generator")
    def responder(state: dict) -> dict:
        attempts = state.get("generation_attempts", 0) + 1
        evidence = state.get("evidence") or {}
        if deps.llm is None:
            return {"answer": template_answer(state), "mode": "demo", "model": None, "generation_attempts": attempts,
                    "_detail": "demo mode: deterministic template (no ANTHROPIC_API_KEY)"}
        if not evidence.get("sufficient"):
            return {"answer": template_answer(state), "mode": "fallback", "model": None,
                    "generation_attempts": attempts, "_status": "skipped",
                    "_detail": "evidence insufficient: LLM not called"}
        if time_left(state) < deps.settings.llm_timeout_seconds:  # not enough budget for one bounded call
            return {"answer": template_answer(state), "mode": "fallback", "model": None,
                    "generation_attempts": attempts, "_status": "degraded", "_detail": "deadline reached"}
        prompt = copilot_user_prompt(state["question"], state.get("facts") or [], state.get("documents") or [],
                                     state.get("provenance"), state.get("generation_feedback", ""))
        try:
            res = deps.llm.generate(COPILOT_SYSTEM, prompt, max_tokens=deps.settings.llm_max_output_tokens)
        except LLMError as exc:
            return {"answer": template_answer(state), "mode": "fallback", "model": None,
                    "generation_attempts": attempts, "_status": "degraded", "_detail": f"LLM unavailable ({exc})"}
        return {"answer": res.text, "mode": "claude", "model": res.model, "generation_attempts": attempts,
                "_detail": f"{res.model}, {res.output_tokens or '?'} output tokens, stop={res.stop_reason}"}

    return responder
