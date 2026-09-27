"""shared sound-effect glossary; series glossary entries of kind sfx move into it

Revision ID: 0021
Revises: 0020
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# odluka korisnika (2026-09-27): ove se ne prevode, a SH i W se prilagođavaju izgovoru
SEED = {
    "BANG": "BANG",
    "TUMP": "TUMP",
    "TRAS": "TRAS",
    "ZING": "ZING",
    "TUP": "TUP",
    "ZIP": "ZIP",
    "FLAP": "FLAP",
    "SKREEK": "SKREEK",
    "SVISH": "SVIŠ",
    "SWACK": "SCVAK",
    "CRASH": "KRAŠ",
}


def key(text: str) -> str:
    return " ".join(re.findall(r"[^\W\d_]+|\d+", text.upper()))


def upgrade() -> None:
    table = op.create_table(
        "sfx_glossary",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(200), nullable=False, unique=True),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    connection = op.get_bind()
    entries = {}
    old = connection.execute(
        sa.text(
            "SELECT source, target FROM glossary_entries "
            "WHERE kind = 'sfx' AND status = 'approved' ORDER BY id"
        )
    )
    for source, target in old:
        if key(source):
            entries.setdefault(key(source), target)
    entries.update(SEED)
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        table,
        [
            {"source": s, "target": t, "created_at": now, "updated_at": now}
            for s, t in entries.items()
        ],
    )
    connection.execute(sa.text("DELETE FROM glossary_entries WHERE kind = 'sfx'"))


def downgrade() -> None:
    op.drop_table("sfx_glossary")
