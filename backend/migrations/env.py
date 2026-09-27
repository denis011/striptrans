from alembic import context

from app import models  # noqa: F401  registruje tabele
from app.config import get_settings
from app.db import Base, make_engine

url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url
engine = make_engine(url)
with engine.connect() as connection:
    # Batch migracije u SQLite-u prave tabelu iznova. Sa uključenim stranim ključevima DROP TABLE
    # kaskadno briše povezane redove (izmena tabele pages je tako obrisala sve tekst blokove).
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    connection.commit()
engine.dispose()
