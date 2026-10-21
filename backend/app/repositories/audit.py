from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.observability import correlation_id_var
from app.repositories.orm import AgentRunRow, AuditLogRow


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def log(self, actor: str, action: str, entity_type: str, entity_id: str, details: dict | None = None) -> None:
        self.s.add(
            AuditLogRow(
                actor=actor, action=action, entity_type=entity_type, entity_id=str(entity_id),
                details=details or {}, correlation_id=correlation_id_var.get(),
            )
        )

    def for_entity(self, entity_type: str, entity_id: str) -> list[AuditLogRow]:
        stmt = select(AuditLogRow).where(AuditLogRow.entity_type == entity_type, AuditLogRow.entity_id == entity_id)
        return list(self.s.scalars(stmt.order_by(AuditLogRow.id)))

    def save_agent_run(self, **fields) -> None:
        self.s.add(AgentRunRow(**fields))

    def agent_run(self, run_id: str) -> AgentRunRow | None:
        return self.s.get(AgentRunRow, run_id)
