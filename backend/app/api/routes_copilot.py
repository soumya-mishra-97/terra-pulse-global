from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.graph import GRAPH_DESCRIPTION
from app.agents.tools import TOOL_REGISTRY
from app.api.deps import current_user, get_container, get_session
from app.schemas.copilot import ChatRequest, ChatResponse
from app.services.copilot import CopilotService

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: str = Depends(current_user), session: Session = Depends(get_session),
         container=Depends(get_container)) -> ChatResponse:
    container.rate_limiter.check(f"copilot:{user}", container.settings.copilot_requests_per_minute, 60)
    return CopilotService(session, container.settings, container.retriever, container.llm).ask(body.question, user)


@router.get("/architecture")
def architecture(container=Depends(get_container)) -> dict:
    return {"graph": GRAPH_DESCRIPTION, "tools": TOOL_REGISTRY,
            "mode": "claude" if container.llm is not None else "demo",
            "model": container.llm.model if container.llm is not None else None,
            "documents": sorted({c.doc.title for c in getattr(container.retriever, "chunks", [])})}
