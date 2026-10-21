"""SQLAlchemy table mappings. Schema changes go through Alembic migrations in ../migrations."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")
BigIntType = BigInteger().with_variant(Integer(), "sqlite")  # sqlite autoincrement needs INTEGER


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DataSourceRow(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(120), unique=True)
    dataset_name: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text)
    landing_page: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str] = mapped_column(String(120))
    release_version: Mapped[str] = mapped_column(String(64))
    reference_date_convention: Mapped[str] = mapped_column(Text)
    geographic_coverage: Mapped[str] = mapped_column(Text)
    methodology_notes: Mapped[str] = mapped_column(Text)
    uncertainty_note: Mapped[str] = mapped_column(Text)
    value_kind: Mapped[str] = mapped_column(String(40))
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    retrieved_at: Mapped[str | None] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    country_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage: Mapped[dict] = mapped_column(JsonType, default=dict)


class CountryRow(Base):
    __tablename__ = "countries"
    iso3: Mapped[str] = mapped_column(String(3), primary_key=True)
    iso2: Mapped[str | None] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(String(160))
    region_code: Mapped[str | None] = mapped_column(String(3))
    region: Mapped[str | None] = mapped_column(String(120))
    income_level: Mapped[str | None] = mapped_column(String(120))
    capital: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    is_aggregate: Mapped[bool] = mapped_column(Boolean, default=False)


class CountryBaselineRow(Base):
    __tablename__ = "country_baselines"
    __table_args__ = (
        UniqueConstraint("source_id", "country_iso3", "metric", "year", name="uq_baseline_obs"),
        Index("ix_baseline_lookup", "source_id", "country_iso3", "metric", "year"),
        Index("ix_baseline_metric_year", "source_id", "metric", "year"),
    )
    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    country_iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"))
    metric: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(80))
    year: Mapped[int] = mapped_column(Integer)
    reference_date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    value_kind: Mapped[str] = mapped_column(String(40))


class PopulationEstimateRow(Base):
    __tablename__ = "population_estimates"
    __table_args__ = (Index("ix_estimate_scope", "source_id", "scope"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    calculation_run_id: Mapped[int | None] = mapped_column(ForeignKey("calculation_runs.id"))
    scope: Mapped[str] = mapped_column(String(3))
    reference_date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    value_kind: Mapped[str] = mapped_column(String(40))
    method: Mapped[str] = mapped_column(Text)
    lower: Mapped[float | None] = mapped_column(Float)
    upper: Mapped[float | None] = mapped_column(Float)
    uncertainty_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CalculationRunRow(Base):
    __tablename__ = "calculation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    inputs_hash: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JsonType, default=dict)
    status: Mapped[str] = mapped_column(String(20))
    output_summary: Mapped[dict] = mapped_column(JsonType, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceEventRow(Base):
    __tablename__ = "source_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_user", "user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_type: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict] = mapped_column(JsonType, default=dict)
    mode: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))
    trace: Mapped[list] = mapped_column(JsonType, default=list)
    validation: Mapped[dict] = mapped_column(JsonType, default=dict)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLogRow(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CountryReportRow(Base):
    __tablename__ = "country_reports"
    __table_args__ = (
        Index("ix_reports_owner", "owner_id", "created_at"),
        Index("ix_reports_request_hash", "owner_id", "request_hash"),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_report_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    country_iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"))
    period: Mapped[str] = mapped_column(String(16))
    sections: Mapped[list] = mapped_column(JsonType, default=list)
    status: Mapped[str] = mapped_column(String(20))  # queued|running|completed|failed|blocked
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict | None] = mapped_column(JsonType)
    validation_status: Mapped[str | None] = mapped_column(String(20))
    validation: Mapped[dict] = mapped_column(JsonType, default=dict)
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    mode: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(80))
    pdf_key: Mapped[str | None] = mapped_column(String(255))
    md_key: Mapped[str | None] = mapped_column(String(255))
    export_meta: Mapped[dict] = mapped_column(JsonType, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ReportSourceRow(Base):
    __tablename__ = "report_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("country_reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # dataset|document
    label: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    published: Mapped[str | None] = mapped_column(String(64))
    reference: Mapped[str | None] = mapped_column(Text)


class ReportGenerationRunRow(Base):
    __tablename__ = "report_generation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("country_reports.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    trace: Mapped[list] = mapped_column(JsonType, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
