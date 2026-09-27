"""lettering style per block (Faza 4c)

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.add_column(sa.Column("style", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.drop_column("style")
