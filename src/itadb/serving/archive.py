"""Versioned, verified archives. Failed builds never replace the active release."""

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
from filelock import FileLock

from itadb.serving.schema import SCHEMA

FORMAT = "itadb-serving/1"
DATABASE = "application.duckdb"
READ_CONFIG: dict[str, str | bool | int | float | list[str]] = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
}


class ArchiveUnavailable(Exception):
    """Safe public failure; details are never returned by the API."""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def create_schema(db: duckdb.DuckDBPyConnection) -> None:
    db.execute("CREATE SCHEMA api")
    for table, columns in SCHEMA.items():
        ddl = ",".join(f'"{name}" {kind}' for name, kind in columns.items())
        db.execute(f"CREATE TABLE api.{table} ({ddl})")


def inspect_schema(db: duckdb.DuckDBPyConnection) -> None:
    actual = db.execute(
        "SELECT table_name,column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='api' ORDER BY table_name,ordinal_position"
    ).fetchall()
    expected = [
        (table, column, str(duckdb.sqltype(kind)))
        for table in sorted(SCHEMA)
        for column, kind in SCHEMA[table].items()
    ]
    if actual != expected:
        raise ArchiveUnavailable("Serving schema is incomplete or incompatible")
    # Resolve every column with its declared type, including empty tables.
    for table, columns in SCHEMA.items():
        casts = ",".join(f'"{name}"::{kind}' for name, kind in columns.items())
        db.execute(f"SELECT {casts} FROM api.{table} LIMIT 0")


def seal_archive(directory: Path, tables: dict[str, Any], source: str) -> dict[str, Any]:
    database = directory / DATABASE
    with database.open("rb") as stream:
        os.fsync(stream.fileno())
    manifest = {
        "format": FORMAT,
        "created_at": datetime.now(UTC).isoformat(),
        "duckdb_version": duckdb.__version__,
        "source": source,
        "database": {
            "name": DATABASE,
            "sha256": digest(database),
            "bytes": database.stat().st_size,
        },
        "tables": tables,
    }
    write_json(directory / "manifest.json", manifest)
    database.chmod(0o444)
    sync_directory(directory)
    verify_archive(directory)
    return manifest


def verify_archive(directory: Path) -> dict[str, Any]:
    try:
        manifest: dict[str, Any] = json.loads((directory / "manifest.json").read_bytes())
        database = directory / DATABASE
        if manifest["format"] != FORMAT or manifest["database"]["name"] != DATABASE:
            raise ArchiveUnavailable("Unsupported archive")
        if set(manifest["tables"]) != set(SCHEMA):
            raise ArchiveUnavailable("Incomplete manifest")
        if database.stat().st_size != manifest["database"]["bytes"]:
            raise ArchiveUnavailable("Archive size mismatch")
        if digest(database) != manifest["database"]["sha256"]:
            raise ArchiveUnavailable("Archive checksum mismatch")
        with duckdb.connect(str(database), read_only=True, config=READ_CONFIG) as db:
            inspect_schema(db)
            for table in SCHEMA:
                count = db.execute(f"SELECT count(*) FROM api.{table}").fetchone()
                if count is None or count[0] != manifest["tables"][table]["rows"]:
                    raise ArchiveUnavailable("Archive row count mismatch")
        return manifest
    except (OSError, ValueError, KeyError, TypeError, duckdb.Error) as exc:
        raise ArchiveUnavailable("Archive verification failed") from exc


def empty_archive(directory: Path) -> Path:
    """Explicit empty catalog for a new installation; never an error fallback."""
    directory.mkdir(parents=True, exist_ok=False)
    with duckdb.connect(str(directory / DATABASE)) as db:
        create_schema(db)
        db.execute("CHECKPOINT")
    seal_archive(directory, {t: {"rows": 0} for t in SCHEMA}, "explicit-empty-catalog")
    return directory


def install_archive(source: Path, root: Path) -> Path:
    manifest = verify_archive(source)
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".publish.lock")):
        target = releases / str(manifest["database"]["sha256"])
        if target.exists():
            verify_archive(target)
            return target
        staging = releases / (".install-" + uuid4().hex)
        staging.mkdir()
        for name in (DATABASE, "manifest.json"):
            with (source / name).open("rb") as src, (staging / name).open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
        verify_archive(staging)
        (staging / DATABASE).chmod(0o444)
        sync_directory(staging)
        staging.rename(target)
        sync_directory(releases)
        return target


def activate_archive(root: Path, release: Path) -> None:
    root = root.resolve()
    release = release.resolve()
    if release.parent != root / "releases" or release.name.startswith("."):
        raise ArchiveUnavailable("Only installed releases can be activated")
    with FileLock(str(root / ".publish.lock")):
        manifest = verify_archive(release)
        current = root / "current"
        if current.exists() and current.resolve() == release:
            return
        history = root / "activations"
        history.mkdir(exist_ok=True)
        token = uuid4().hex
        # Record intent before the durable pointer change; never overwrite history.
        write_json(
            history / (token + ".json"),
            {
                "created_at": datetime.now(UTC).isoformat(),
                "previous": current.resolve().name if current.exists() else None,
                "next": release.name,
                "sha256": manifest["database"]["sha256"],
            },
        )
        pointer = root / (".current-" + token)
        pointer.symlink_to(release.relative_to(root), target_is_directory=True)
        os.replace(pointer, current)
        sync_directory(root)
