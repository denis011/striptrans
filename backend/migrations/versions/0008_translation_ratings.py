"""translation ratings

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translation_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study", sa.String(length=50), nullable=False),
        sa.Column("item", sa.Integer(), nullable=False),
        sa.Column("page_position", sa.Integer(), nullable=False),
        sa.Column("block_position", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("candidate", sa.String(length=100), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("translation", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("rated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("translation_ratings") as batch_op:
        batch_op.create_index("ix_translation_ratings_study", ["study"], unique=False)


def downgrade() -> None:
    op.drop_table("translation_ratings")
