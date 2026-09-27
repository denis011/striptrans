import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, make_url
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    """SQLite engine sa WAL režimom, da api i worker mogu istovremeno da koriste bazu."""
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def migration_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def backup_before_upgrade(config: Config, database_url: str) -> Path | None:
    """Kopija postojeće baze pre migracije, u data/backups/ (nova ili ažurna baza se ne kopira)."""
    path = make_url(database_url).database
    if not path or path == ":memory:" or not Path(path).exists():
        return None
    engine = make_engine(database_url)
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    if current is None or current == ScriptDirectory.from_config(config).get_current_head():
        return None
    backups = Path(path).parent / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = backups / f"{Path(path).stem}-{current}-{stamp}.db"
    with sqlite3.connect(path) as source, sqlite3.connect(target) as copy:
        source.backup(copy)
    return target


def run_migrations(database_url: str) -> None:
    config = migration_config(database_url)
    backup_before_upgrade(config, database_url)
    command.upgrade(config, "head")
