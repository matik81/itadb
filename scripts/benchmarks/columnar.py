"""Reproducible columnar capacity probe, not a synthetic population generator."""

import argparse
import json
import platform
import time
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path, default=Path("data/reports/capacity.parquet"))
    args = parser.parse_args()
    if not 1 <= args.rows <= 100_000_000:
        parser.error("rows must be between 1 and 100 million")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("output already exists; choose a new output path")
    with duckdb.connect() as db:
        db.execute("SET memory_limit='1GB'")
        db.execute("SET threads=4")
        started = time.perf_counter()
        db.sql(
            """SELECT i::BIGINT AS person_id, (i//3)::BIGINT AS household_id,
            (i%8000)::INTEGER AS territory_id, (i%101)::SMALLINT AS age,
            (i%3)::SMALLINT AS category FROM range(?) t(i)""",
            params=[args.rows],
        ).write_parquet(str(args.output), compression="zstd", row_group_size=122880)
        write_seconds = time.perf_counter() - started
        started = time.perf_counter()
        result = db.execute(
            "SELECT territory_id,count(*) FROM read_parquet(?) GROUP BY territory_id",
            [str(args.output)],
        ).fetchall()
        print(
            json.dumps(
                {
                    "rows": args.rows,
                    "bytes": args.output.stat().st_size,
                    "write_seconds": write_seconds,
                    "group_seconds": time.perf_counter() - started,
                    "groups": len(result),
                    "duckdb": duckdb.__version__,
                    "platform": platform.platform(),
                    "caution": "Artificial low-entropy probe; not a production sizing estimate",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
