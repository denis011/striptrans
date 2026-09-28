"""translation styles (settings), series translation notes, translator note on blocks

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
        "translation_styles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("text", sa.Text()),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        table,
        [
            {
                "name": "Podrazumevani",
                "text": None,
                "builtin": True,
                "active": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    with op.batch_alter_table("series") as batch:
        batch.add_column(sa.Column("translation_notes", sa.Text(), nullable=True))
    with op.batch_alter_table("text_blocks") as batch:
        batch.add_column(sa.Column("translation_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.drop_column("translation_note")
    with op.batch_alter_table("series") as batch:
        batch.drop_column("translation_notes")
    op.drop_table("translation_styles")
