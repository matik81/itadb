import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import duckdb
import psycopg
from filelock import FileLock
from psycopg.types.json import Jsonb

from itadb.config import Settings
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError, normalize_demo

TRANSFORM_VERSION = "population-demo/1.0.1"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"


def ingest_demo(settings: Settings, source: Path, contract: Path) -> UUID:
    raw, checksum = archive_file(source, settings.data_dir / "raw")
    contract_hash = sha256_file(contract)
    identity = f"demo_population:{checksum}:{TRANSFORM_VERSION}:{contract_hash}"
    release_id = uuid5(NAMESPACE_URL, identity)
    state = settings.data_dir / "state"
    state.mkdir(parents=True, exist_ok=True)
    # Same-host file writes are serialized; database advisory lock covers separate hosts.
    with FileLock(str(state / f"{release_id}.lock"), timeout=60):
        return _run(settings, raw, checksum, contract, contract_hash, release_id, identity)


def _run(
    settings: Settings,
    raw: Path,
    checksum: str,
    contract: Path,
    contract_hash: str,
    release_id: UUID,
    identity: str,
) -> UUID:
    run_id = uuid4()
    now = datetime.now(UTC)
    curated = settings.data_dir / "curated" / str(release_id) / "observations.parquet"
    quality_path = settings.data_dir / "reports" / f"{release_id}.json"
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        db.execute(
            "INSERT INTO catalog.pipeline_run(id,started_at,status) VALUES (%s,%s,'running')",
            (run_id, now),
        )
        try:
            with db.transaction():
                lock = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], signed=True)
                db.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
                if db.execute(
                    "SELECT 1 FROM catalog.release WHERE id=%s AND status='published'",
                    (release_id,),
                ).fetchone():
                    db.execute(
                        "UPDATE catalog.pipeline_run SET release_id=%s,status='succeeded',"
                        "finished_at=now() WHERE id=%s",
                        (release_id, run_id),
                    )
                    return release_id
                report = normalize_demo(raw, curated, contract)
                atomic_json(quality_path, report)
                db.execute(
                    """INSERT INTO catalog.release
                    (id,dataset_id,reference_period,retrieved_at,upstream_url,raw_sha256,
                     transform_version,contract_sha256,license_url,status,row_count)
                    VALUES (%s,'demo_population',%s,%s,%s,%s,%s,%s,%s,'draft',%s)""",
                    (
                        release_id,
                        report["reference_period"],
                        now,
                        "urn:itadb:fixture:population-demo",
                        checksum,
                        TRANSFORM_VERSION,
                        contract_hash,
                        LICENSE_URL,
                        report["rows"],
                    ),
                )
                for kind, path in [("raw", raw), ("curated", curated), ("quality", quality_path)]:
                    db.execute(
                        "INSERT INTO catalog.artifact VALUES (%s,%s,%s,%s,%s)",
                        (
                            release_id,
                            kind,
                            path.relative_to(settings.data_dir).as_posix(),
                            sha256_file(path),
                            path.stat().st_size,
                        ),
                    )
                for name, passed in report["checks"].items():
                    db.execute(
                        "INSERT INTO catalog.quality_result VALUES (%s,%s,%s,%s)",
                        (release_id, name, passed, Jsonb({"rows": report["rows"]})),
                    )
                _load(db, curated, release_id)
                actual = db.execute(
                    "SELECT count(*) FROM stats.observation WHERE release_id=%s", (release_id,)
                ).fetchone()
                if actual is None or actual[0] != report["rows"]:
                    raise ValueError("Post-load row count mismatch")
                db.execute(
                    "UPDATE catalog.release SET status='validated' WHERE id=%s", (release_id,)
                )
                db.execute(
                    "UPDATE catalog.release SET status='published',published_at=now() WHERE id=%s",
                    (release_id,),
                )
                db.execute(
                    "UPDATE catalog.pipeline_run SET release_id=%s,status='succeeded',"
                    "finished_at=now() WHERE id=%s",
                    (release_id, run_id),
                )
        except Exception as error:
            if isinstance(error, QualityError):
                atomic_json(
                    settings.data_dir / "quarantine" / f"{run_id}.json",
                    {"raw_sha256": checksum, "report": error.report},
                )
            db.execute(
                "UPDATE catalog.pipeline_run SET status='failed',finished_at=now(),"
                "error_code=%s WHERE id=%s",
                (type(error).__name__, run_id),
            )
            raise
    return release_id


def _load(db: psycopg.Connection[Any], curated: Path, release_id: UUID) -> None:
    db.execute("""CREATE TEMP TABLE staged_population
        (territory_code text, territory_name text, period date, population bigint)
        ON COMMIT DROP""")
    with duckdb.connect() as analytical, db.cursor() as cursor:
        result = analytical.execute("SELECT * FROM read_parquet(?)", [str(curated)])
        with cursor.copy("COPY staged_population FROM STDIN") as copy:
            while batch := result.fetchmany(10_000):
                for row in batch:
                    copy.write_row(row)
    db.execute("""INSERT INTO geo.territory(scheme,code,name,level,valid_from)
        SELECT DISTINCT 'ITADB_DEMO',territory_code,territory_name,'municipality','2025-01-01'::date
        FROM staged_population ON CONFLICT (scheme,code,valid_from) DO NOTHING""")
    if db.execute("""SELECT 1 FROM staged_population p JOIN geo.territory t
        ON t.scheme='ITADB_DEMO' AND t.code=p.territory_code AND t.valid_from='2025-01-01'
        WHERE t.name <> p.territory_name LIMIT 1""").fetchone():
        raise ValueError("Territory label changed without a new territorial version")
    db.execute(
        """INSERT INTO stats.observation
        SELECT %s,s.id,t.id,p.period,p.population,'demo' FROM staged_population p
        JOIN geo.territory t ON t.scheme='ITADB_DEMO' AND t.code=p.territory_code
          AND t.valid_from='2025-01-01'
        CROSS JOIN stats.series s WHERE s.code='population_total'""",
        (release_id,),
    )
