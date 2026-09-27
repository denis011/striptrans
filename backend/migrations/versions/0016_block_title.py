"""title glyphs cut from the original (Faza 6a)

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.add_column(sa.Column("title", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.drop_column("title")
