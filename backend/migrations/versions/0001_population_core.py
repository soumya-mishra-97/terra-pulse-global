"""Population core: sources, countries, baselines, estimates, events, agent runs, audit logs.

Revision ID: 0001_population_core
Revises:
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_population_core"
down_revision = None
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(120), nullable=False, unique=True),
        sa.Column("dataset_name", sa.String(255), nullable=False),
        sa.Column("publisher", sa.String(255), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("landing_page", sa.Text),
        sa.Column("license", sa.String(120), nullable=False),
        sa.Column("release_version", sa.String(64), nullable=False),
        sa.Column("reference_date_convention", sa.Text, nullable=False),
        sa.Column("geographic_coverage", sa.Text, nullable=False),
        sa.Column("methodology_notes", sa.Text, nullable=False),
        sa.Column("uncertainty_note", sa.Text, nullable=False),
        sa.Column("value_kind", sa.String(40), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False, unique=True),
        sa.Column("retrieved_at", sa.String(64)),
        sa.Column("imported_at", TS, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("is_synthetic", sa.Boolean, nullable=False),
        sa.Column("superseded_by_id", sa.Integer, sa.ForeignKey("data_sources.id")),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("country_count", sa.Integer, nullable=False),
        sa.Column("coverage", JSON, nullable=False),
    )
    op.create_table(
        "countries",
        sa.Column("iso3", sa.String(3), primary_key=True),
        sa.Column("iso2", sa.String(2)),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("region_code", sa.String(3)),
        sa.Column("region", sa.String(120)),
        sa.Column("income_level", sa.String(120)),
        sa.Column("capital", sa.String(120)),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("is_aggregate", sa.Boolean, nullable=False),
    )
    op.create_table(
        "country_baselines",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_iso3", sa.String(3), sa.ForeignKey("countries.iso3"), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(80), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("reference_date", sa.Date, nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("value_kind", sa.String(40), nullable=False),
        sa.UniqueConstraint("source_id", "country_iso3", "metric", "year", name="uq_baseline_obs"),
    )
    op.create_index("ix_baseline_lookup", "country_baselines", ["source_id", "country_iso3", "metric", "year"])
    op.create_index("ix_baseline_metric_year", "country_baselines", ["source_id", "metric", "year"])
    op.create_table(
        "calculation_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.id", ondelete="SET NULL")),
        sa.Column("inputs_hash", sa.String(64), nullable=False),
        sa.Column("params", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("output_summary", JSON, nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("finished_at", TS),
    )
    op.create_table(
        "population_estimates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("calculation_run_id", sa.Integer, sa.ForeignKey("calculation_runs.id")),
        sa.Column("scope", sa.String(3), nullable=False),
        sa.Column("reference_date", sa.Date, nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("value_kind", sa.String(40), nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("lower", sa.Float),
        sa.Column("upper", sa.Float),
        sa.Column("uncertainty_note", sa.Text, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_estimate_scope", "population_estimates", ["source_id", "scope"])
    op.create_table(
        "source_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("input", JSON, nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("model", sa.String(80)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trace", JSON, nullable=False),
        sa.Column("validation", JSON, nullable=False),
        sa.Column("latency_ms", sa.Float),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_agent_runs_user", "agent_runs", ["user_id", "created_at"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("details", JSON, nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_audit_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_entity", "audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_agent_runs_user", "agent_runs")
    op.drop_table("agent_runs")
    op.drop_table("source_events")
    op.drop_index("ix_estimate_scope", "population_estimates")
    op.drop_table("population_estimates")
    op.drop_table("calculation_runs")
    op.drop_index("ix_baseline_metric_year", "country_baselines")
    op.drop_index("ix_baseline_lookup", "country_baselines")
    op.drop_table("country_baselines")
    op.drop_table("countries")
    op.drop_table("data_sources")
