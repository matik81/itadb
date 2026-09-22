"""Versioned evidence, territorial dimensions and partitioned observations."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = (Path(__file__).parents[1] / "sql" / "0001_foundation.sql").read_text(encoding="utf-8")
    # Compile literal percent signs in PostgreSQL format() correctly for psycopg.
    # TextClause also supports Alembic's offline SQL generation.
    op.execute(text(sql))


def downgrade() -> None:
    raise RuntimeError(
        "Irreversible evidence migration. Restore a verified backup; never drop evidence."
    )
