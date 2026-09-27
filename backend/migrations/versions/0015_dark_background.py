"""dark background under a block: lettering is drawn light (Faza 5)

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.add_column(sa.Column("dark_background", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.drop_column("dark_background")
