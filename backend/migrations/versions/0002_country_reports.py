"""Country Intelligence Reports: reports, report sources, generation runs.

Section content is stored inside country_reports.content (JSON) because sections are always
read and written together; a separate report_sections table would add joins without benefit.

Revision ID: 0002_country_reports
Revises: 0001_population_core
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_country_reports"
down_revision = "0001_population_core"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "country_reports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("country_iso3", sa.String(3), sa.ForeignKey("countries.iso3"), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("sections", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.Integer, nullable=False),
        sa.Column("current_step", sa.String(64)),
        sa.Column("error", sa.Text),
        sa.Column("content", JSON),
        sa.Column("validation_status", sa.String(20)),
        sa.Column("validation", JSON, nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(80)),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.id", ondelete="SET NULL")),
        sa.Column("mode", sa.String(20)),
        sa.Column("model", sa.String(80)),
        sa.Column("pdf_key", sa.String(255)),
        sa.Column("md_key", sa.String(255)),
        sa.Column("export_meta", JSON, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("generated_at", TS),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_report_idempotency"),
    )
    op.create_index("ix_reports_owner", "country_reports", ["owner_id", "created_at"])
    op.create_index("ix_reports_request_hash", "country_reports", ["owner_id", "request_hash"])
    op.create_table(
        "report_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.String(32), sa.ForeignKey("country_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("publisher", sa.String(255)),
        sa.Column("url", sa.Text),
        sa.Column("published", sa.String(64)),
        sa.Column("reference", sa.Text),
    )
    op.create_index("ix_report_sources_report_id", "report_sources", ["report_id"])
    op.create_table(
        "report_generation_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.String(32), sa.ForeignKey("country_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trace", JSON, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("finished_at", TS),
    )
    op.create_index("ix_report_generation_runs_report_id", "report_generation_runs", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_report_generation_runs_report_id", "report_generation_runs")
    op.drop_table("report_generation_runs")
    op.drop_index("ix_report_sources_report_id", "report_sources")
    op.drop_table("report_sources")
    op.drop_index("ix_reports_request_hash", "country_reports")
    op.drop_index("ix_reports_owner", "country_reports")
    op.drop_table("country_reports")
