"""Build new immutable DuckDB archives; only verified candidates become published."""

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import duckdb
from filelock import FileLock

from itadb.config import Settings
from itadb.serving.archive import (
    DATABASE,
    activate_archive,
    create_schema,
    install_archive,
    seal_archive,
    verify_archive,
    write_json,
)
from itadb.serving.schema import SCHEMA, TEXT_ORDER_INPUTS
from itadb.serving.sql import row


def insert(db: duckdb.DuckDBPyConnection, table: str, values: dict[str, Any]) -> None:
    if table not in SCHEMA or not set(values) <= SCHEMA[table].keys():
        raise ValueError("Unknown public fields")
    columns = ",".join(f'"{name}"' for name in values)
    parameters = ",".join("?" for _ in values)
    db.execute(f"INSERT INTO api.{table} ({columns}) VALUES ({parameters})", list(values.values()))


class Publication:
    def __init__(self, db: duckdb.DuckDBPyConnection):
        self.db = db
        self.changed = False


def published_root(settings: Settings) -> Path:
    return settings.data_dir / "published"


@contextmanager
def publication(settings: Settings) -> Iterator[Publication]:
    root = published_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    attempt = uuid4().hex
    candidate = root / "attempts" / attempt
    candidate.mkdir(parents=True)
    published = False
    try:
        with FileLock(str(root / ".writer.lock"), timeout=60):
            current = root / "current"
            if not current.exists() and not current.is_symlink():
                current = settings.serving_dir / "current"
            if current.exists() or current.is_symlink():
                source = current.resolve()
                verify_archive(source)
                shutil.copyfile(source / DATABASE, candidate / DATABASE)
            with duckdb.connect(str(candidate / DATABASE)) as db:
                db.execute("SET threads=2")
                db.execute("SET memory_limit='1GB'")
                db.execute("SET TimeZone='UTC'")
                if not db.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name='api'"
                ).fetchone():
                    create_schema(db)
                db.execute("BEGIN")
                writer = Publication(db)
                yield writer
                if not writer.changed:
                    write_json(candidate / "result.json", {"changed": False})
                    return
                # Each archive defines its own stable ordering, independent of host locale.
                db.execute("DELETE FROM api.text_order")
                db.execute(
                    "INSERT INTO api.text_order SELECT value,row_number() OVER (ORDER BY value) "
                    "FROM ("
                    + " UNION ".join(TEXT_ORDER_INPUTS)
                    + ") values_ WHERE value IS NOT NULL"
                )
                tables = {
                    table: {"rows": row(db.execute(f"SELECT count(*) FROM api.{table}"))[0]}
                    for table in SCHEMA
                }
                db.execute("COMMIT")
                db.execute("CHECKPOINT")
            seal_archive(candidate, tables, "duckdb-publication/1")
            installed = install_archive(candidate, root)
            activate_archive(root, installed)
            published = True
            write_json(candidate / "result.json", {"changed": True, "release": installed.name})
    except Exception as exc:
        quarantine = settings.data_dir / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        write_json(
            quarantine / f"publication-{attempt}.json",
            {
                "error_type": type(exc).__name__,
                "published": published,
            },
        )
        raise


class RevisionConflict(ValueError):
    """A revision must identify its current predecessor and explain the change."""


def check_revision(
    db: duckdb.DuckDBPyConnection,
    dataset: str,
    period: object,
    supersedes: UUID | None,
    reason: str | None,
) -> None:
    row = db.execute(
        "SELECT id FROM api.releases_v2 WHERE dataset_id=? AND reference_period=? "
        "ORDER BY published_at DESC,id DESC LIMIT 1",
        [dataset, period],
    ).fetchone()
    if (
        (row[0] if row else None) != supersedes
        or (supersedes is not None and not (reason or "").strip())
        or (supersedes is None and reason is not None)
    ):
        raise RevisionConflict("Specify the current predecessor and revision reason")


def add_source(db: duckdb.DuckDBPyConnection, source: str, demo: bool) -> None:
    if not db.execute("SELECT 1 FROM api.sources WHERE id=?", [source]).fetchone():
        insert(
            db,
            "sources",
            {
                "id": source,
                "name": "Fixture inventata" if demo else "ISTAT",
                "homepage": "urn:itadb:fixture" if demo else "https://www.istat.it/",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"
                if demo
                else "https://creativecommons.org/licenses/by/4.0/",
                "is_demo": demo,
            },
        )


def add_evidence(
    db: duckdb.DuckDBPyConnection,
    rid: UUID,
    checks: dict[str, bool],
    details: dict[str, Any],
    artifacts: dict[str, Path],
    *,
    v1: bool = False,
) -> None:
    from itadb.pipeline.storage import sha256_file

    if not checks or not all(checks.values()):
        raise ValueError("Publication quality checks failed")
    for kind, path in artifacts.items():
        insert(
            db,
            "artifacts_v2",
            {
                "release_id": rid,
                "kind": kind,
                "sha256": sha256_file(path),
                "byte_size": path.stat().st_size,
            },
        )
    for name, passed in checks.items():
        values = {
            "release_id": rid,
            "check_name": name,
            "passed": passed,
            "details": json.dumps(details, default=str),
        }
        insert(db, "quality_v2", values)
        if v1:
            insert(db, "quality", values)
