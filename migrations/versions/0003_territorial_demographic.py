"""M2 coverage, geographic versions and documented territorial crosswalks."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            (Path(__file__).parents[1] / "sql/0003_territorial_demographic.sql").read_text(
                encoding="utf-8"
            )
        )
    )


def downgrade() -> None:
    raise RuntimeError("Irreversible evidence migration. Restore a verified backup.")
