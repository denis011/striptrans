"""fonts (Faza 4b)

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fonts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("series") as batch:
        batch.add_column(sa.Column("dialogue_font", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("sfx_font", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("series") as batch:
        batch.drop_column("sfx_font")
        batch.drop_column("dialogue_font")
    op.drop_table("fonts")
