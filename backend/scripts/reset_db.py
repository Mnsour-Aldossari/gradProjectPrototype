"""Reset the local database to a clean state: no missions, only the two demo users.

    python -m scripts.reset_db          # dry run: shows what would be deleted, changes nothing
    python -m scripts.reset_db --yes    # backs up the SQLite file to ../backups/, then resets

Stop the backend server first. The reset drops every table (alembic_version too), runs the
migrations again and the same user seeding the server runs at startup (supervisor and field
operator, test credentials only).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import MetaData, func
from sqlmodel import Session, SQLModel, select

from app.config import Settings
from app.db import init_db, make_engine
from app.seed import seed_users

BACKUP_DIR = Path(__file__).resolve().parents[2] / "backups"


def table_counts(engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            name: session.exec(select(func.count()).select_from(table)).one()
            for name, table in SQLModel.metadata.tables.items()
        }


def reset(engine) -> None:
    """Drop every table the database has, alembic_version included (so the migrations run again from the start,
    not just from where it was), then build it again and add the two demo users."""
    tables = MetaData()
    tables.reflect(engine)
    tables.drop_all(engine)
    init_db(engine)
    seed_users(engine)


def sqlite_file(url: str) -> Path | None:
    prefix = "sqlite:///"
    return Path(url[len(prefix):]) if url.startswith(prefix) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="actually reset (default is a dry run)")
    args = parser.parse_args()

    settings = Settings.from_env()
    engine = make_engine(settings.database_url)
    file = sqlite_file(settings.database_url)
    where = file if file else settings.database_url.split("@")[-1]
    print(f"Database: {where}")
    if file is not None and not file.exists():
        print("The database file does not exist yet; nothing to delete. Start the backend once to create it.")
        return 0

    counts = table_counts(engine)
    print("Rows that would be deleted:" if not args.yes else "Rows before reset:")
    for name, n in counts.items():
        print(f"  {name:<18}{n:>8}")
    print("Afterwards: empty tables, then the 2 demo users (supervisor, field operator) re-created.")

    if not args.yes:
        print("\nDry run only: nothing was changed. Re-run with --yes to reset.")
        return 0

    if file is not None:
        BACKUP_DIR.mkdir(exist_ok=True)
        backup = BACKUP_DIR / f"{file.name}.{datetime.now():%Y%m%d-%H%M%S}.bak"
        shutil.copy2(file, backup)
        print(f"Backup written: {backup}")
    else:
        print("Not a SQLite database: no automatic backup was made.")

    reset(engine)
    print("After reset:")
    for name, n in table_counts(engine).items():
        print(f"  {name:<18}{n:>8}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
