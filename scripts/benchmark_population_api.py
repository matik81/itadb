"""Measure actual published population queries without changing the database."""

import argparse
import json
import platform
import statistics
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

from itadb.api.population_repository import PopulationRepository
from itadb.config import Settings


class MeasuredRepository(PopulationRepository):
    capture: bool = False
    plans: list[dict[str, Any]] = []

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if self.capture:
            with self.pool.connection() as connection:
                connection.execute("SET TRANSACTION READ ONLY")
                connection.execute("SET LOCAL statement_timeout='5s'")
                result = connection.execute(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
                ).fetchone()
                assert result is not None
                self.plans.append(result[0][0])
        return super()._query(sql, params)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 2 or args.repeats > 30:
        parser.error("repeats must be between 2 and 30")
    settings = Settings()
    with ConnectionPool(settings.database_url, min_size=1, max_size=2) as pool:
        repository = MeasuredRepository(pool)
        snapshot = repository.snapshot(args.snapshot)
        if snapshot is None:
            raise ValueError("Published snapshot not found")
        # A national large-city scope exercises nontrivial ordering and filters.
        sid = args.snapshot
        tests = {
            "municipality_id_page": lambda: repository.persons(
                sid, "058091", None, None, 0, 100, "person_id", "asc", 0, 100
            ),
            "municipality_age_desc": lambda: repository.persons(
                sid, "058091", None, None, 0, 100, "age", "desc", 0, 100
            ),
            "municipality_citizenship_filter": lambda: repository.persons(
                sid, "058091", "F", "201", 18, 65, "person_id", "asc", 0, 100
            ),
            "household_members": lambda: repository.household(sid, 1),
            "national_distribution": lambda: repository.distributions(
                sid, None, None, None, None, 0, 100
            ),
            "municipality_distribution": lambda: repository.distributions(
                sid, "058091", None, None, None, 0, 100
            ),
            "national_validation": lambda: repository.validation(sid, None),
            "map_municipalities": lambda: repository.municipalities(sid, None, None, 0, 10000),
            "map_regions": lambda: repository.regions(sid),
        }
        measurements = {}
        started = time.monotonic()
        for label, call in tests.items():
            durations = []
            for i in range(args.repeats):
                before = time.monotonic()
                call()
                durations.append((time.monotonic() - before) * 1000)
                print(
                    f"{label}: {i + 1}/{args.repeats}, {durations[-1]:.1f} ms; "
                    f"trascorsi {time.monotonic() - started:.1f}s",
                    flush=True,
                )
            repository.capture = True
            repository.plans = []
            call()
            repository.capture = False
            measurements[label] = {
                "samples_ms": durations,
                "median_ms": statistics.median(durations),
                "max_ms": max(durations),
                "plans": repository.plans,
            }
        with psycopg.connect(settings.admin_database_url) as db:
            storage = db.execute("""SELECT sum(pg_total_relation_size(c.oid)) FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='population' AND c.relkind='r'""").fetchone()
            version = db.execute("SELECT version()").fetchone()
        result = {
            "scope": (
                "local single-client actual national population; "
                "not a concurrency or hosted-service benchmark"
            ),
            "run_id": snapshot["run_id"],
            "snapshot_id": sid,
            "persons": snapshot["persons"],
            "households": snapshot["households"],
            "python": platform.python_version(),
            "platform": platform.system(),
            "postgresql": version[0] if version else None,
            "population_schema_bytes": int(storage[0]) if storage else None,
            "queries": measurements,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(f"Esito: misure e piani salvati in {args.output}", flush=True)


if __name__ == "__main__":
    main()
