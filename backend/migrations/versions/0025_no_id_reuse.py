"""SQLite AUTOINCREMENT: ids of deleted rows are never reused

Revision ID: 0025
Revises: 0024
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tabele čiji broj ide u adrese slika, foldere ili veze (keš pregledača, AI predlozi, izvozi)
TABLES = ("projects", "pages", "text_blocks", "patches", "fonts", "exports", "jobs")


def upgrade() -> None:
    for table in TABLES:  # tabela se pravi iznova sa istim podacima i brojevima
        with op.batch_alter_table(
            table, recreate="always", table_kwargs={"sqlite_autoincrement": True}
        ):
            pass


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(
            table, recreate="always", table_kwargs={"sqlite_autoincrement": False}
        ):
            pass
