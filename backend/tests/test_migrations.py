from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.config import BACKEND_DIR
from app.db import make_engine, run_migrations
from app.repositories.orm import Base

EXPECTED = {"data_sources", "countries", "country_baselines", "population_estimates", "calculation_runs",
            "source_events", "agent_runs", "audit_logs", "country_reports", "report_sources", "report_generation_runs"}


def test_migrations_create_all_tables_and_match_orm(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)
    engine = make_engine(url)
    assert EXPECTED <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    # Only type-affinity noise is tolerated on SQLite; no missing tables/columns/indexes.
    structural = [d for d in diffs if d[0] in ("add_table", "remove_table", "add_column", "remove_column",
                                                "add_index", "remove_index")]
    assert structural == []


def test_migrations_downgrade_to_base(tmp_path):
    url = f"sqlite:///{tmp_path / 'd.db'}"
    run_migrations(url)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.downgrade(cfg, "base")
    assert set(inspect(make_engine(url)).get_table_names()) <= {"alembic_version"}
