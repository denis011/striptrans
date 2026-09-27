"""album exports (Faza 5b)

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("image_format", sa.String(length=10), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.String(length=10), nullable=False),
        sa.Column("positions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("received", sa.JSON(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exports_project_id", "exports", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_exports_project_id", "exports")
    op.drop_table("exports")
