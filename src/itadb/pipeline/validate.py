import csv
import json
from pathlib import Path
from typing import Any

import duckdb


def scalar(db: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = db.execute(query).fetchone()
    if row is None:
        raise RuntimeError("Expected a scalar query result")
    return row[0]


class QualityError(ValueError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__(
            "Quality gate failed: "
            + ", ".join(name for name, ok in report["checks"].items() if not ok)
        )


def normalize_demo(raw: Path, output: Path, contract: Path) -> dict[str, Any]:
    specification = json.loads(contract.read_text(encoding="utf-8"))
    with raw.open(encoding="utf-8", newline="") as file:
        columns = next(csv.reader(file), [])
    if columns != specification["columns"]:
        raise QualityError({"checks": {"exact_columns": False}, "rows": 0})
    output.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as db:
        db.execute("SET memory_limit='512MB'")
        db.execute("SET threads=2")
        db.execute(
            "CREATE TABLE input AS SELECT * FROM read_csv(?, header=true, all_varchar=true)",
            [str(raw)],
        )
        rows = scalar(db, "SELECT count(*) FROM input")
        invalid = scalar(
            db,
            """
            SELECT count(*) FROM input WHERE
              territory_code IS NULL OR NOT regexp_full_match(territory_code, 'DEMO[0-9]{3}')
              OR territory_name IS NULL OR length(trim(territory_name))=0
              OR period IS NULL OR NOT regexp_full_match(period, '[0-9]{4}-[0-9]{2}-[0-9]{2}')
              OR try_cast(period AS DATE) IS NULL OR period < '2025-01-01'
              OR population IS NULL OR NOT regexp_full_match(population, '[0-9]+')
              OR try_cast(population AS BIGINT) IS NULL
        """,
        )
        duplicates = scalar(
            db,
            """SELECT count(*) FROM
            (SELECT territory_code, period FROM input GROUP BY ALL HAVING count(*)>1)""",
        )
        periods = scalar(db, "SELECT count(DISTINCT period) FROM input")
        checks = {
            "exact_columns": True,
            "nonempty": rows > 0,
            "valid_values": invalid == 0,
            "unique_key": duplicates == 0,
            "single_period": periods == 1,
        }
        report: dict[str, Any] = {
            "checks": checks,
            "rows": rows,
            "invalid_rows": invalid,
            "duplicate_keys": duplicates,
            "is_demo": True,
        }
        if not all(checks.values()):
            raise QualityError(report)
        db.execute(
            """COPY (SELECT territory_code, territory_name,
            cast(period AS DATE) AS period, cast(population AS BIGINT) AS population
            FROM input ORDER BY territory_code, period) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)""",
            [str(output)],
        )
        report["reference_period"] = str(scalar(db, "SELECT min(period) FROM input"))
        return report
