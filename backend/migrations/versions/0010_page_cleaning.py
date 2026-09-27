"""page cleaning (Faza 4a)

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pages") as batch:
        batch.add_column(sa.Column("clean_path", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("mask_path", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("cleaned_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pages") as batch:
        batch.drop_column("cleaned_at")
        batch.drop_column("mask_path")
        batch.drop_column("clean_path")
