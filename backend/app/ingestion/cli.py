"""TerraPulse data CLI.

    python -m app.ingestion.cli migrate
    python -m app.ingestion.cli import-snapshot data/snapshots/wdi-2026-10-08 [--skip-invalid]
    python -m app.ingestion.cli bootstrap            # migrate + import newest bundled snapshot if none active
    python -m app.ingestion.cli sources
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.db import get_session_factory, run_migrations
from app.domain.errors import DuplicateImportError, ImportValidationError
from app.ingestion.importer import ImportOptions, import_snapshot
from app.observability import configure_logging
from app.repositories.population import PopulationRepository


def _import(path: Path, skip_invalid: bool) -> int:
    settings = get_settings()
    try:
        result = import_snapshot(
            get_session_factory(), path,
            ImportOptions(skip_invalid=skip_invalid, stale_after_days=settings.stale_after_days),
        )
    except DuplicateImportError as exc:
        print(f"Skipped: {exc}")
        return 3
    except ImportValidationError as exc:
        print(f"Import rejected: {exc}", file=sys.stderr)
        for r in exc.rejected[:10]:
            print(f"  line {r.get('line', '?')}: {r['reason']}", file=sys.stderr)
        return 2
    print(json.dumps(result.__dict__, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="terrapulse")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    imp = sub.add_parser("import-snapshot", help="import a dataset snapshot directory")
    imp.add_argument("path", type=Path)
    imp.add_argument("--skip-invalid", action="store_true", help="import valid rows and record rejected rows")
    sub.add_parser("bootstrap", help="migrate and import the newest bundled snapshot when no source is active")
    sub.add_parser("sources", help="list imported data sources")
    args = parser.parse_args(argv)
    configure_logging(get_settings().log_level)

    if args.cmd == "migrate":
        run_migrations()
        print("Migrations applied.")
        return 0
    if args.cmd == "import-snapshot":
        return _import(args.path, args.skip_invalid)
    if args.cmd == "bootstrap":
        run_migrations()
        with get_session_factory()() as s:
            if PopulationRepository(s).active_source():
                print("Active data source present; nothing to import.")
                return 0
        snapshots = sorted(p for p in get_settings().snapshot_dir.iterdir() if (p / "manifest.json").is_file())
        if not snapshots:
            print("No bundled snapshot found. Run scripts/fetch_worldbank_snapshot.py first.", file=sys.stderr)
            return 1
        code = _import(snapshots[-1], skip_invalid=False)
        return 0 if code in (0, 3) else code
    if args.cmd == "sources":
        with get_session_factory()() as s:
            for src in PopulationRepository(s).list_sources():
                flag = "ACTIVE" if src.is_active else "superseded"
                print(f"[{flag}] #{src.id} {src.snapshot_id} {src.dataset_name} release={src.release_version} "
                      f"imported={src.imported_at:%Y-%m-%d} checksum={src.checksum[:12]}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
