"""Serve verified synthetic population snapshots independently of the generator."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text((Path(__file__).parents[1] / "sql/0006_population_product.sql").read_text()))


def downgrade() -> None:
    raise RuntimeError("Irreversible evidence migration. Restore a verified backup.")
