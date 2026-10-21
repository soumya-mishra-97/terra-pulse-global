from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.repositories.orm import CountryReportRow, ReportGenerationRunRow, ReportSourceRow

ACTIVE_STATUSES = ("queued", "running")


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def get(self, report_id: str) -> CountryReportRow | None:
        return self.s.get(CountryReportRow, report_id)

    def get_for_owner(self, report_id: str, owner_id: str) -> CountryReportRow | None:
        return self.s.scalar(
            select(CountryReportRow).where(CountryReportRow.id == report_id, CountryReportRow.owner_id == owner_id)
        )

    def by_idempotency_key(self, owner_id: str, key: str) -> CountryReportRow | None:
        return self.s.scalar(
            select(CountryReportRow).where(CountryReportRow.owner_id == owner_id, CountryReportRow.idempotency_key == key)
        )

    def recent_same_request(self, owner_id: str, request_hash: str, window_seconds: int) -> CountryReportRow | None:
        since = datetime.now(UTC) - timedelta(seconds=window_seconds)
        return self.s.scalar(
            select(CountryReportRow)
            .where(
                CountryReportRow.owner_id == owner_id,
                CountryReportRow.request_hash == request_hash,
                CountryReportRow.status.in_(("queued", "running", "completed")),
                CountryReportRow.created_at >= since,
            )
            .order_by(CountryReportRow.created_at.desc())
        )

    def count_active(self, owner_id: str) -> int:
        return self.s.scalar(
            select(func.count()).select_from(CountryReportRow).where(
                CountryReportRow.owner_id == owner_id, CountryReportRow.status.in_(ACTIVE_STATUSES)
            )
        ) or 0

    def list_for_owner(self, owner_id: str, limit: int, offset: int) -> tuple[list[CountryReportRow], int]:
        base = select(CountryReportRow).where(CountryReportRow.owner_id == owner_id)
        total = self.s.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = list(self.s.scalars(base.order_by(CountryReportRow.created_at.desc()).limit(limit).offset(offset)))
        return rows, total

    def add(self, row: CountryReportRow) -> None:
        self.s.add(row)
        self.s.flush()

    def set_progress(self, report_id: str, status: str, progress: int, step: str | None) -> None:
        self.s.execute(
            update(CountryReportRow)
            .where(CountryReportRow.id == report_id)
            .values(status=status, progress=progress, current_step=step, updated_at=datetime.now(UTC))
        )

    def replace_sources(self, report_id: str, sources: list[dict]) -> None:
        self.s.query(ReportSourceRow).filter(ReportSourceRow.report_id == report_id).delete()
        for src in sources:
            self.s.add(ReportSourceRow(report_id=report_id, **src))

    def sources(self, report_id: str) -> list[ReportSourceRow]:
        return list(self.s.scalars(select(ReportSourceRow).where(ReportSourceRow.report_id == report_id).order_by(ReportSourceRow.id)))

    def add_run(self, **fields) -> ReportGenerationRunRow:
        row = ReportGenerationRunRow(**fields)
        self.s.add(row)
        self.s.flush()
        return row

    def runs(self, report_id: str) -> list[ReportGenerationRunRow]:
        return list(self.s.scalars(select(ReportGenerationRunRow).where(ReportGenerationRunRow.report_id == report_id).order_by(ReportGenerationRunRow.id)))

    def mark_interrupted(self) -> int:
        """Called on startup: jobs that were queued/running when the process died cannot resume."""
        res = self.s.execute(
            update(CountryReportRow)
            .where(CountryReportRow.status.in_(ACTIVE_STATUSES))
            .values(status="failed", error="Generation was interrupted by a server restart. Please regenerate.",
                    current_step=None, updated_at=datetime.now(UTC))
        )
        return res.rowcount or 0

    def delete(self, row: CountryReportRow) -> None:
        self.s.delete(row)
