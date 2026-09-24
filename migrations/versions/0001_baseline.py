"""Consolidated PostgreSQL/PostGIS baseline, including the synthetic population."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text((Path(__file__).parents[1] / "sql/0001_baseline.sql").read_text()))


def downgrade() -> None:
    raise RuntimeError("Irreversible evidence migration. Restore a verified backup.")
