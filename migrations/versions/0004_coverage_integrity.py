"""Recheck draft context when publishing coverage evidence."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            (Path(__file__).parents[1] / "sql/0004_coverage_integrity.sql").read_text(
                encoding="utf-8"
            )
        )
    )


def downgrade() -> None:
    raise RuntimeError("Irreversible evidence migration. Restore a verified backup.")
