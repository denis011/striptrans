"""patch remembers the block it covers (image from the AI app pasted on a block)

Revision ID: 0026
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("patches", table_kwargs={"sqlite_autoincrement": True}) as batch:
        batch.add_column(sa.Column("block_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_patches_block_id", "text_blocks", ["block_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("patches", table_kwargs={"sqlite_autoincrement": True}) as batch:
        batch.drop_constraint("fk_patches_block_id", type_="foreignkey")
        batch.drop_column("block_id")
