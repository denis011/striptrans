"""patch visibility mask (brush erases and restores parts of a patch)

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("patches") as batch:
        batch.add_column(sa.Column("mask_path", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("patches") as batch:
        batch.drop_column("mask_path")
