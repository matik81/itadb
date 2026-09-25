"""Build isolated national storage candidates; never mutate the source snapshot."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import duckdb
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from itadb.config import Settings

PERSON_SELECT = """person_id::INTEGER person_id, household_id::INTEGER household_id,
municipality::INTEGER municipality_code, sex,
coalesce(2024-birth_year,100)::SMALLINT age,
citizenship_code::SMALLINT citizenship_code, reference_adult"""


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["duckdb", "postgres"], required=True)
    parser.add_argument("--database", default="itadb_storage_compact_20260925")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = args.source.resolve()
    started = time.monotonic()
    if args.phase == "duckdb":
        if (root / "population.duckdb").exists():
            raise ValueError("Output exists: choose a new experiment directory")
        manifest = json.loads((source / "manifest.json").read_text())
        files = sorted(source.glob("batch-*/persons.parquet"))
        households = sorted(source.glob("batch-*/households.parquet"))
        hashes = {str(p.relative_to(source)): digest(p) for p in files + households}
        # The independent verify-population command must also pass before benchmarking.
        for relative, actual in hashes.items():
            expected = manifest["files"][relative]
            if isinstance(expected, dict):
                expected = expected["sha256"]
            if actual != expected:
                raise ValueError(f"Checksum mismatch: {relative}")
        print(f"Checksum verificati: {len(hashes)} file", flush=True)
        db = duckdb.connect(str(root / "population.duckdb"))
        db.execute("SET threads=4; SET memory_limit='6GB'")
        db.execute(
            f"CREATE TABLE person AS SELECT {PERSON_SELECT} FROM read_parquet(?) "
            "ORDER BY municipality_code,person_id",
            [[str(p) for p in files]],
        )
        print("Individui caricati", flush=True)
        db.execute(
            "CREATE TABLE household AS SELECT household_id::INTEGER household_id, "
            "municipality::INTEGER municipality_code,size::SMALLINT size "
            "FROM read_parquet(?) ORDER BY household_id",
            [[str(p) for p in households]],
        )
        db.execute(
            "CREATE TABLE cell AS SELECT municipality_code,sex,age,citizenship_code,"
            "count(*)::BIGINT persons FROM person GROUP BY ALL "
            "ORDER BY municipality_code,age,sex,citizenship_code"
        )
        db.execute(
            "CREATE TABLE geography AS SELECT DISTINCT municipality::INTEGER "
            "municipality_code,province::INTEGER province_code,region::INTEGER region_code "
            "FROM read_parquet(?)",
            [[str(p) for p in households]],
        )
        print("Famiglie, celle e geografia caricate", flush=True)
        for table, identity in [("person", "person_id"), ("household", "household_id")]:
            row = db.execute(
                f"SELECT count(*),count(DISTINCT {identity}),min({identity}),"
                f"max({identity}) FROM {table}"
            ).fetchone()
            if not (row[0] == row[1] == row[3] and row[2] == 1):
                raise ValueError("Dense unique identifiers required by this prototype")
        # Verify that cohort compression is exactly reversible, including the open class.
        invalid = db.execute(
            "SELECT count(*) FROM read_parquet(?) WHERE "
            "((birth_year BETWEEN 1925 AND 2024 "
            "AND birth_year_upper_bound IS NULL) OR "
            "(birth_year IS NULL AND birth_year_upper_bound=1924)) IS NOT TRUE",
            [[str(p) for p in files]],
        ).fetchone()[0]
        if invalid:
            raise ValueError("Unsupported cohort encoding")
        exports = {
            "person": "SELECT person_id,coalesce(household_id,0),municipality_code,"
            "CASE sex WHEN 'F' THEN 0 WHEN 'M' THEN 1 ELSE 255 END,age,"
            "citizenship_code,reference_adult::INTEGER FROM person ORDER BY person_id",
            "household": "SELECT * FROM household ORDER BY household_id",
            "cell": "SELECT municipality_code,CASE sex WHEN 'F' THEN 0 ELSE 1 END,"
            "age,citizenship_code,persons FROM cell ORDER BY municipality_code,age,sex,"
            "citizenship_code",
        }
        for name, query in exports.items():
            db.execute(f"COPY ({query}) TO '{root / (name + '.csv')}' (HEADER false)")
            print(f"Esportato {name}", flush=True)
        # Avoid ART over 59M keys: clustered zone maps are the low-memory DuckDB candidate.
        db.execute("CHECKPOINT")
        metrics = {
            "build_seconds": time.monotonic() - started,
            "duckdb_version": duckdb.__version__,
            "run_id": source.name,
            "source_manifest_sha256": digest(source / "manifest.json"),
            "input_bytes": sum(p.stat().st_size for p in files + households),
            "source_files_sha256": hashes,
            "counts": {
                t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ["person", "household", "cell", "geography"]
            },
        }
        db.close()
        metrics["archive_bytes"] = (root / "population.duckdb").stat().st_size
        (root / "prepare-duckdb.json").write_text(json.dumps(metrics, indent=2) + "\n")
        print(json.dumps({k: v for k, v in metrics.items() if k != "source_files_sha256"}))
    else:
        config = conninfo_to_dict(Settings().admin_database_url)
        config["dbname"] = "postgres"
        name = args.database
        with psycopg.connect(**config, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name))
            )
        config["dbname"] = name
        with psycopg.connect(**config, autocommit=True) as db:
            db.execute("SET maintenance_work_mem='512MB'; SET statement_timeout=0")
            db.execute(
                "CREATE TABLE person (person_id integer NOT NULL,household_id integer,"
                "municipality_code integer NOT NULL,sex smallint NOT NULL,age smallint "
                "NOT NULL,citizenship_code smallint NOT NULL,reference_adult smallint NOT NULL)"
            )
            db.execute(
                "CREATE TABLE household (household_id integer NOT NULL,"
                "municipality_code integer NOT NULL,size smallint NOT NULL)"
            )
            db.execute(
                "CREATE TABLE cell (municipality_code integer NOT NULL,sex smallint "
                "NOT NULL,age smallint NOT NULL,citizenship_code smallint NOT NULL,"
                "persons bigint NOT NULL)"
            )
            for table in ["person", "household", "cell"]:
                print(f"COPY PostgreSQL {table}", flush=True)
                with (
                    db.cursor().copy(f"COPY {table} FROM STDIN WITH (FORMAT CSV)") as copy,
                    (root / f"{table}.csv").open("rb") as stream,
                ):
                    while block := stream.read(8 * 1024 * 1024):
                        copy.write(block)
            # household_id=0 is the explicit null sentinel in this snapshot-only encoding.
            for statement in [
                "ALTER TABLE person ADD PRIMARY KEY(person_id)",
                "CREATE INDEX person_municipality_id ON person(municipality_code,person_id)",
                "CREATE INDEX person_family ON person(household_id,person_id) WHERE household_id>0",
                "CREATE INDEX person_municipality_age "
                "ON person(municipality_code,age DESC,person_id)",
                "ALTER TABLE household ADD PRIMARY KEY(household_id)",
                "CREATE INDEX household_municipality ON household(municipality_code,household_id)",
                "CREATE INDEX cell_municipality ON cell(municipality_code)",
                "VACUUM (ANALYZE) person",
                "VACUUM (ANALYZE) household",
                "VACUUM (ANALYZE) cell",
            ]:
                print(statement, flush=True)
                db.execute(statement)
            sizes = db.execute(
                "SELECT relname,pg_table_size(oid),pg_indexes_size(oid),"
                "pg_total_relation_size(oid) FROM pg_class WHERE relnamespace="
                "'public'::regnamespace AND relkind='r' ORDER BY relname"
            ).fetchall()
            result = {
                "database": name,
                "build_seconds": time.monotonic() - started,
                "relations": sizes,
                "archive_bytes": sum(r[3] for r in sizes),
                "database_bytes": db.execute(
                    "SELECT pg_database_size(current_database())"
                ).fetchone()[0],
            }
            (root / "prepare-postgres.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
