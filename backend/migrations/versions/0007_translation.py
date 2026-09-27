"""block translation, page translation review, translation memory

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch_op:
        batch_op.add_column(
            sa.Column("translation", sa.Text(), nullable=False, server_default=sa.text("''"))
        )
        batch_op.add_column(sa.Column("translation_model", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column(
                "translation_status",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'none'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "translation_too_long", sa.Boolean(), nullable=False, server_default=sa.text("0")
            )
        )
    with op.batch_alter_table("pages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "translation_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("0")
            )
        )
    op.create_table(
        "translation_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "source", name="uq_translation_memory"),
    )
    with op.batch_alter_table("translation_memory") as batch_op:
        batch_op.create_index("ix_translation_memory_series_id", ["series_id"], unique=False)


def downgrade() -> None:
    op.drop_table("translation_memory")
    with op.batch_alter_table("pages") as batch_op:
        batch_op.drop_column("translation_reviewed")
    with op.batch_alter_table("text_blocks") as batch_op:
        batch_op.drop_column("translation_too_long")
        batch_op.drop_column("translation_status")
        batch_op.drop_column("translation_model")
        batch_op.drop_column("translation")
