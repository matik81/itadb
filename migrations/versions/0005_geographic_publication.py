"""Revalidate territorial events and boundary containment at publication."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            (Path(__file__).parents[1] / "sql/0005_geographic_publication.sql").read_text(
                encoding="utf-8"
            )
        )
    )


def downgrade() -> None:
    raise RuntimeError("Irreversible evidence migration. Restore a verified backup.")
