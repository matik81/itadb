"""Full canonical row parity, relation sizes and query plans without source writes."""

import argparse
import hashlib
import json
import time

import psycopg
from psycopg.conninfo import conninfo_to_dict
from storage_compare import SQLStore
from storage_prepare import digest

from itadb.config import Settings


def main():
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = {"engines": {}, "source_storage": {}}
    queries = json.loads((args.root / "workload.json").read_text())
    for engine in ("postgres", "postgres_compact"):
        config = conninfo_to_dict(Settings().admin_database_url)
        compact = engine == "postgres_compact"
        if compact:
            config["dbname"] = json.loads((args.root / "prepare-postgres.json").read_text())[
                "database"
            ]
        metrics = {}
        with psycopg.connect(
            **config, autocommit=True, options="-c default_transaction_read_only=on"
        ) as db:
            if not compact:
                unsupported = db.execute(
                    "SELECT count(*) FROM population.person WHERE snapshot_id=1 AND "
                    "((birth_year BETWEEN 1925 AND 2024 AND birth_year_upper_bound IS NULL) OR "
                    "(birth_year IS NULL AND birth_year_upper_bound=1924)) IS NOT TRUE"
                ).fetchone()[0]
                if unsupported:
                    raise ValueError("Source PostgreSQL cohorts are not reversibly encoded")
            if compact:
                selects = {
                    "person": "SELECT * FROM person ORDER BY person_id",
                    "household": "SELECT * FROM household ORDER BY household_id",
                    "cell": "SELECT * FROM cell ORDER BY municipality_code,age,sex,"
                    "citizenship_code",
                }
            else:
                selects = {
                    "person": "SELECT person_id,coalesce(household_id,0),municipality_code,"
                    "CASE sex WHEN 'F' THEN 0 ELSE 1 END,age,citizenship_code,"
                    "reference_adult::INTEGER FROM api.population_persons "
                    "WHERE snapshot_id=1 ORDER BY person_id",
                    "household": "SELECT household_id,municipality_code,size "
                    "FROM api.population_households WHERE snapshot_id=1 "
                    "ORDER BY household_id",
                    "cell": "SELECT municipality_code,CASE sex WHEN 'F' THEN 0 ELSE 1 END,"
                    "age,citizenship_code,persons FROM api.population_cells WHERE "
                    "snapshot_id=1 ORDER BY municipality_code,age,sex,citizenship_code",
                }
            for table, select in selects.items():
                started = time.monotonic()
                hashed = hashlib.sha256()
                count = 0
                print(f"Audit integrale {engine}/{table}", flush=True)
                with db.cursor().copy(f"COPY ({select}) TO STDOUT WITH (FORMAT CSV)") as copy:
                    for block in copy:
                        hashed.update(block)
                        count += 1
                actual = hashed.hexdigest()
                expected = digest(args.root / f"{table}.csv")
                if actual != expected:
                    raise ValueError(f"Full parity mismatch: {engine}/{table}")
                metrics[table] = {
                    "sha256": actual,
                    "rows": count,
                    "seconds": time.monotonic() - started,
                }
                print(
                    f"Parità completa {engine}/{table}: {count} righe, SHA256 identico", flush=True
                )
            if not compact:
                result["source_storage"] = {
                    "database_bytes": db.execute(
                        "SELECT pg_database_size(current_database())"
                    ).fetchone()[0],
                    "population_relations": db.execute(
                        "SELECT c.relname,pg_table_size(c.oid),pg_indexes_size(c.oid),"
                        "pg_total_relation_size(c.oid) FROM pg_class c JOIN pg_namespace n "
                        "ON n.oid=c.relnamespace WHERE n.nspname='population' AND c.relkind='r' "
                        "ORDER BY c.relname"
                    ).fetchall(),
                    "version": db.execute("SELECT version()").fetchone()[0],
                }
        store = SQLStore(args.root, engine)
        plans = {}
        original = store.execute

        for label in [
            "municipality_id_page",
            "municipality_age_desc",
            "municipality_age_second_page",
            "national_distribution",
        ]:

            def explain(sql, params=(), original=original, plans=plans, label=label):
                plan = original("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
                plans.setdefault(label, []).extend(plan[0][0])
                return original(sql, params)

            store.execute = explain
            print(f"Piano {engine}/{label}", flush=True)
            store.query(queries[label])
        store.close()
        result["engines"][engine] = {"full_parity": metrics, "plans": plans}
    with (args.root / "audit-postgres.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
