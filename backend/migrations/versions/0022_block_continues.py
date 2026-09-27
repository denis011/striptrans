"""text block continues in another block (text split over columns or balloons)

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.add_column(sa.Column("continues_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_text_blocks_continues", "text_blocks", ["continues_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("text_blocks") as batch:
        batch.drop_constraint("fk_text_blocks_continues", type_="foreignkey")
        batch.drop_column("continues_id")
