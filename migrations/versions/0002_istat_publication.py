"""Immutable ISTAT revisions, temporal integrity and versioned public views."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = (Path(__file__).parents[1] / "sql" / "0002_istat_publication.sql").read_text(
        encoding="utf-8"
    )
    op.execute(text(sql))


def downgrade() -> None:
    raise RuntimeError("Irreversible evidence migration. Restore a verified backup.")
