"""Append immutable province cartography from each snapshot's geographic source."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0002_province_boundaries"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text((Path(__file__).parents[1] / "sql/0002_province_boundaries.sql").read_text()))


def downgrade() -> None:
    raise RuntimeError("Irreversible evidence migration. Restore a verified backup.")
