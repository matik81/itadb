"""Export only published API views using a consistent PostgreSQL reader snapshot."""

import hashlib
import time
from pathlib import Path
from typing import Any

import duckdb
import psycopg

from itadb.config import Settings
from itadb.serving.archive import DATABASE, create_schema, seal_archive, verify_archive, write_json
from itadb.serving.schema import EXPORT_QUERIES, SCHEMA


def export_archive(settings: Settings, directory: Path, evidence: Path) -> Path:
    if (directory / "manifest.json").exists():
        verify_archive(directory)
        print("Archivio immutabile esistente verificato; nessuna riscrittura", flush=True)
        return directory
    directory.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    tables: dict[str, Any] = {}
    try:
        with (
            psycopg.connect(settings.database_url) as source,
            duckdb.connect(str(directory / DATABASE)) as target,
        ):
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            source.execute("SET LOCAL timezone='UTC'")
            source.execute("SET LOCAL datestyle='ISO, YMD'")
            # The API reader normally has a 5-second statement timeout. A bounded
            # offline full export legitimately scans every published record.
            source.execute("SET LOCAL statement_timeout=0")
            source.execute("SET LOCAL idle_in_transaction_session_timeout=0")
            target.execute("SET threads=4")
            target.execute("SET memory_limit='2GB'")
            create_schema(target)
            for name, query in EXPORT_QUERIES.items():
                print(
                    f"Esportazione {name}; trascorsi {time.monotonic() - started:.1f} s", flush=True
                )
                csv = evidence / (name + ".csv")
                sha = hashlib.sha256()
                with csv.open("xb") as stream, source.cursor() as cursor:
                    with cursor.copy(f"COPY ({query}) TO STDOUT (FORMAT CSV, NULL '\\N')") as copy:
                        for block in copy:
                            stream.write(block)
                            sha.update(block)
                    copied_rows = cursor.rowcount
                columns = SCHEMA[name]
                read = (
                    "read_csv(?,columns=?,header=false,nullstr='\\N',auto_detect=false,"
                    "allow_quoted_nulls=false)"
                )
                params: list[Any] = [str(csv), columns]
                order = {
                    "population_persons": "snapshot_id,municipality_code,person_id",
                    "population_households": "snapshot_id,household_id",
                    "population_cells": "snapshot_id,municipality_code,age,sex,citizenship_code",
                    "population_validation": "snapshot_id,municipality_code,kind,category,sex",
                }.get(name)
                suffix = f" ORDER BY {order}" if order else ""
                # Empty COPY output still has a declared schema; no inference or float coercion.
                if csv.stat().st_size:
                    target.execute(f"INSERT INTO api.{name} SELECT * FROM {read}{suffix}", params)
                cols = ",".join(f'"{c}"' for c in columns)
                fingerprint = (
                    "count(*),sum(hash(" + cols + ")::HUGEINT),bit_xor(hash(" + cols + "))"
                )
                actual = target.execute(f"SELECT {fingerprint} FROM api.{name}").fetchone()
                expected = (
                    target.execute(f"SELECT {fingerprint} FROM {read}", params).fetchone()
                    if csv.stat().st_size
                    else (0, None, None)
                )
                if expected != actual or actual is None or copied_rows != actual[0]:
                    raise ValueError(f"Round-trip data mismatch: {name}")
                assert actual is not None
                tables[name] = {
                    "rows": actual[0],
                    "source_rows": copied_rows,
                    "copy_sha256": sha.hexdigest(),
                    "fingerprint": [str(v) if v is not None else None for v in actual[1:]],
                }
                print(f"Verificato {name}: {actual[0]} righe", flush=True)
            target.execute("CHECKPOINT")
        seal_archive(directory, tables, "postgres-api-repeatable-read")
        print(
            f"Archivio completo verificato; durata {time.monotonic() - started:.1f} s", flush=True
        )
        return directory
    except Exception as exc:
        # Preserve partial output and safe failure evidence, without credentials or row values.
        write_json(
            evidence / "failure.json",
            {"error_type": type(exc).__name__, "completed_tables": list(tables)},
        )
        raise
