"""seed series

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    series = sa.table(
        "series",
        sa.column("name", sa.String),
        sa.column("source_lang", sa.String),
        sa.column("target_lang", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        series,
        [
            {
                "name": "Italijanski strip",
                "source_lang": "it",
                "target_lang": "sr",
                "created_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM series WHERE name = 'Italijanski strip'")
