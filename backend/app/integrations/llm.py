"""Claude via LangChain (langchain-anthropic), behind a narrow interface.

The rest of the application only sees `LLMClient.generate(system, user, max_tokens)`. When no
ANTHROPIC_API_KEY is configured, `build_llm()` returns None and the agents use deterministic
templates ("demo" mode). The key is read server-side only and never sent to the browser.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings
from app.observability import metrics

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """Any failure talking to the model. Callers degrade to deterministic output."""


class LLMRefusal(LLMError):
    pass


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float


class LLMClient(Protocol):
    model: str

    def generate(self, system: str, user: str, max_tokens: int) -> LLMResult: ...


class ClaudeLangChainClient:
    def __init__(self, settings: Settings) -> None:
        from langchain_anthropic import ChatAnthropic  # imported lazily: optional at runtime

        self.model = settings.anthropic_model
        kwargs: dict = {}
        betas = None
        if settings.llm_server_fallbacks:
            # Server-side refusal fallbacks (beta): the API reroutes a refused request by category.
            betas = [FALLBACK_BETA]
            kwargs["extra_body"] = {"fallbacks": "default"}
        self._chat = ChatAnthropic(
            model=self.model,
            api_key=settings.anthropic_api_key.get_secret_value(),
            max_tokens=settings.llm_max_output_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,  # SDK retries 408/409/429/5xx with backoff
            reasoning_effort="low",  # short grounded explanations; thinking stays adaptive
            betas=betas,
            model_kwargs=kwargs,
        )

    def generate(self, system: str, user: str, max_tokens: int) -> LLMResult:
        from langchain_core.messages import HumanMessage, SystemMessage

        start = time.perf_counter()
        try:
            msg = self._chat.invoke([SystemMessage(content=system), HumanMessage(content=user)], max_tokens=max_tokens)
        except Exception as exc:  # network, auth, rate-limit, timeout after bounded retries
            metrics.incr("llm.errors")
            log.warning("llm call failed", extra={"error_type": type(exc).__name__})
            raise LLMError(type(exc).__name__) from exc
        latency = (time.perf_counter() - start) * 1000
        meta = msg.response_metadata or {}
        stop = meta.get("stop_reason")
        usage = meta.get("usage") or {}
        metrics.incr("llm.calls")
        metrics.observe("llm.latency", latency)
        if stop == "refusal":
            raise LLMRefusal("model declined the request")
        text = msg.text if isinstance(msg.text, str) else str(msg.content)
        if stop == "max_tokens":
            log.info("llm output hit max_tokens", extra={"max_tokens": max_tokens})
        return LLMResult(text=text.strip(), model=meta.get("model", self.model), stop_reason=stop,
                         input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                         latency_ms=latency)


def build_llm(settings: Settings) -> LLMClient | None:
    if not settings.llm_enabled:
        return None
    try:
        return ClaudeLangChainClient(settings)
    except Exception as exc:  # misconfiguration must not take the API down
        log.error("could not initialise Claude client; continuing in demo mode", extra={"error_type": type(exc).__name__})
        return None
