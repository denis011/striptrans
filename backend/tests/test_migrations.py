from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app import models  # noqa: F401  registruje tabele
from app.db import Base, make_engine, run_migrations


def test_migrations_match_models(settings):
    run_migrations(settings.database_url)
    engine = make_engine(settings.database_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []


def test_upgrade_keeps_text_blocks_and_backs_up_database(settings):
    from pathlib import Path

    from alembic import command
    from sqlalchemy import text

    from app.db import migration_config

    url = settings.database_url
    command.upgrade(migration_config(url), "0006")
    engine = make_engine(url)
    with engine.begin() as connection:
        now = "2026-09-16 10:00:00"
        connection.execute(
            text(
                "INSERT INTO projects (id, series_id, created_at, updated_at) VALUES (1, 1, :now, :now)"  # noqa: E501
            ),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO pages (id, project_id, kind, position, import_order, source_name, width, height,"  # noqa: E501
                " image_path, thumbnail_path, created_at, skip, ocr_reviewed)"
                " VALUES (1, 1, 'original', 1, 1, 'a.jpg', 10, 10, 'a', 'b', :now, 0, 0)"
            ),
            {"now": now},
        )
        connection.execute(
            text(
                "INSERT INTO text_blocks (page_id, position, kind, x, y, width, height, text, source,"  # noqa: E501
                " needs_review, created_at, updated_at)"
                " VALUES (1, 1, 'speech', 0, 0, 5, 5, 'AIUTO!', 'manual', 0, :now, :now)"
            ),
            {"now": now},
        )
    engine.dispose()

    run_migrations(url)  # 0007 pravi tabelu pages iznova

    engine = make_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT text FROM text_blocks")).scalars().all() == [
            "AIUTO!"
        ]
    engine.dispose()
    assert len(list((Path(settings.data_dir) / "backups").glob("test-0006-*.db"))) == 1
