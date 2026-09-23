"""Atomic publication of the reviewed, bounded ISTAT regional slice."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import duckdb
import psycopg
from filelock import FileLock
from psycopg.types.json import Jsonb

from itadb.config import Settings
from itadb.pipeline.istat_population import check_population_sample
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError

TRANSFORM_VERSION = "istat-population-regions/publication-1.0.0"
DATASET = "istat_population_regions"
SERIES = "resident_population_jan1"


class RevisionConflict(ValueError):
    """The requested predecessor is not the current published release."""


def metadata_fingerprint(structure: Path, dataflow: Path) -> str:
    """Ignore response headers, never the structural/semantic metadata."""
    digest = hashlib.sha256()
    for path in (structure, dataflow):
        canonical = ET.canonicalize(
            from_file=path,
            strip_text=True,
            exclude_tags={"{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message}Header"},
        )
        digest.update(canonical.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _archive_json(root: Path, content: dict[str, Any]) -> Path:
    temporary = root / "state" / f".{uuid4().hex}.json"
    try:
        atomic_json(temporary, content)
        return archive_file(temporary, root / "raw")[0]
    finally:
        temporary.unlink(missing_ok=True)


def _parquet(root: Path, rows: list[dict[str, Any]]) -> Path:
    temporary = root / "state" / f".{uuid4().hex}.parquet"
    try:
        with duckdb.connect() as db:
            db.execute("SET memory_limit='128MB'")
            db.execute("SET threads=2")
            db.execute("""CREATE TABLE normalized (
                territory_code VARCHAR, territory_name VARCHAR, level VARCHAR, period DATE,
                population BIGINT, status VARCHAR, upstream_status VARCHAR, upstream_note VARCHAR,
                upstream_unit VARCHAR, upstream_unit_multiplier VARCHAR)""")
            db.executemany(
                "INSERT INTO normalized VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        r["territory_code"],
                        r["territory_name"],
                        r["level"],
                        r["period"],
                        r["population"],
                        r["status"],
                        r["upstream_attributes"]["OBS_STATUS"],
                        r["upstream_attributes"]["NOTE_REF_AREA"],
                        r["upstream_attributes"]["UNIT_MEAS"],
                        r["upstream_attributes"]["UNIT_MULT"],
                    )
                    for r in rows
                ],
            )
            db.execute(
                "COPY (SELECT * FROM normalized ORDER BY territory_code) TO ? "
                "(FORMAT PARQUET, COMPRESSION ZSTD)",
                [str(temporary)],
            )
        return archive_file(temporary, root / "curated")[0]
    finally:
        temporary.unlink(missing_ok=True)


def _load(
    db: psycopg.Connection[Any],
    curated: Path,
    release_id: UUID,
    scheme: str,
    snapshot: date,
    valid_to: date,
) -> None:
    db.execute("""CREATE TEMP TABLE staged_istat (
        territory_code text, territory_name text, level text, period date, population bigint,
        status text, upstream_status text, upstream_note text, upstream_unit text,
        upstream_unit_multiplier text) ON COMMIT DROP""")
    with duckdb.connect() as analytical, db.cursor() as cursor:
        result = analytical.execute("SELECT * FROM read_parquet(?)", [str(curated)])
        with cursor.copy("COPY staged_istat FROM STDIN") as copy:
            while batch := result.fetchmany(1000):
                for row in batch:
                    copy.write_row(row)
    db.execute(
        """INSERT INTO geo.territory(scheme,code,name,level,valid_from,valid_to)
        SELECT %s,territory_code,territory_name,level,%s,%s FROM staged_istat WHERE level='country'
        ON CONFLICT (scheme,code,valid_from) DO NOTHING""",
        (scheme, snapshot, valid_to),
    )
    db.execute(
        """INSERT INTO geo.territory(scheme,code,name,level,valid_from,valid_to,parent_id)
        SELECT %s,p.territory_code,p.territory_name,p.level,%s,%s,t.id FROM staged_istat p
        JOIN geo.territory t ON t.scheme=%s AND t.code='IT' AND t.valid_from=%s
        WHERE p.level='region' ON CONFLICT (scheme,code,valid_from) DO NOTHING""",
        (scheme, snapshot, valid_to, scheme, snapshot),
    )
    if db.execute(
        """SELECT 1 FROM staged_istat p LEFT JOIN geo.territory t
        ON t.scheme=%s AND t.code=p.territory_code AND t.valid_from=%s
        LEFT JOIN geo.territory parent ON parent.id=t.parent_id
        WHERE t.id IS NULL OR t.name<>p.territory_name OR t.level<>p.level
        OR t.valid_to IS DISTINCT FROM %s::date
        OR (p.level='region' AND parent.code IS DISTINCT FROM 'IT')
        OR (p.level='country' AND t.parent_id IS NOT NULL) LIMIT 1""",
        (scheme, snapshot, valid_to),
    ).fetchone():
        raise ValueError("Territorial snapshot differs from its immutable definition")
    db.execute(
        """INSERT INTO stats.observation
        (release_id,series_id,territory_id,period,value,status,upstream_status,upstream_note,
         upstream_unit,upstream_unit_multiplier)
        SELECT %s,s.id,t.id,p.period,p.population,p.status,p.upstream_status,p.upstream_note,
               p.upstream_unit,p.upstream_unit_multiplier
        FROM staged_istat p JOIN geo.territory t
        ON t.scheme=%s AND t.code=p.territory_code AND t.valid_from=%s
        CROSS JOIN stats.series s WHERE s.code=%s""",
        (release_id, scheme, snapshot, SERIES),
    )


def ingest_istat_population(
    settings: Settings,
    acquisition: Path,
    structure: Path,
    dataflow: Path,
    onboarding_contract: Path,
    publication_contract: Path,
    license_evidence: Path,
    supersedes: UUID | None = None,
    revision_reason: str | None = None,
) -> UUID:
    root = settings.data_dir
    run_id = uuid4()
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        db.execute(
            "INSERT INTO catalog.pipeline_run(id,started_at,status) VALUES (%s,now(),'running')",
            (run_id,),
        )
        try:
            return _publish(
                db,
                root,
                run_id,
                acquisition,
                structure,
                dataflow,
                onboarding_contract,
                publication_contract,
                license_evidence,
                supersedes,
                revision_reason,
            )
        except Exception as error:
            atomic_json(
                root / "quarantine" / f"publication-{run_id}.json",
                {
                    "run_id": run_id,
                    "published": False,
                    "error_code": type(error).__name__,
                    "report": error.report if isinstance(error, QualityError) else None,
                },
            )
            db.execute(
                "UPDATE catalog.pipeline_run SET status='failed',finished_at=now(),"
                "error_code=%s WHERE id=%s",
                (type(error).__name__, run_id),
            )
            raise


def _publish(
    db: psycopg.Connection[Any],
    root: Path,
    run_id: UUID,
    acquisition: Path,
    structure: Path,
    dataflow: Path,
    onboarding_contract: Path,
    publication_contract: Path,
    license_evidence: Path,
    supersedes: UUID | None,
    revision_reason: str | None,
) -> UUID:
    contract_path, contract_hash = archive_file(publication_contract, root / "raw")
    spec = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        spec["name"] != "istat-population-regions-publication"
        or spec["version"] not in {"1.0.0", "1.0.1"}
        or spec["dataset_id"] != DATASET
        or spec["series_code"] != SERIES
        or spec["onboarding_contract_sha256"] != sha256_file(onboarding_contract)
    ):
        raise ValueError("Publication contract does not match the reviewed adapter/onboarding")
    report_path = check_population_sample(
        root, acquisition, structure, dataflow, onboarding_contract
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence = report["evidence"]
    license_path, license_hash = archive_file(license_evidence, root / "raw")
    if (
        license_hash != spec["license_evidence_sha256"]
        or license_hash != report["license"]["evidence_sha256"]
    ):
        raise ValueError("License evidence does not match the reviewed contract")
    snapshot = date.fromisoformat(spec["territory_snapshot"])
    valid_to = date.fromisoformat(spec["territory_valid_to"])
    if (
        str(snapshot) != report["reference_period"]
        or (valid_to - snapshot).days != 1
        or spec["source_scheme"] != report["territory_scheme"]
        or spec["national_code"] != "IT"
        or spec["status"] != "unflagged_upstream"
        or spec["max_value_exclusive"] != 10**14
    ):
        raise ValueError("Unsupported territorial snapshot, status or numeric storage range")
    checks = dict(report["checks"])
    checks["numeric_storage_range"] = all(r["population"] < 10**14 for r in report["observations"])
    if not checks["numeric_storage_range"]:
        raise QualityError({"checks": checks, "rows": report["rows"]})
    metadata_hash = metadata_fingerprint(
        root / evidence["structure"]["path"], root / evidence["dataflow"]["path"]
    )
    identity = ":".join(
        (DATASET, evidence["data"]["sha256"], TRANSFORM_VERSION, contract_hash, metadata_hash)
    )
    release_id = uuid5(NAMESPACE_URL, identity)
    geography = [
        (r["territory_code"], r["territory_name"], r["level"]) for r in report["observations"]
    ]
    geography_hash = hashlib.sha256(json.dumps(geography, ensure_ascii=False).encode()).hexdigest()
    scheme = f"{spec['source_scheme']}:{snapshot}:{geography_hash}"
    with FileLock(str(root / "state" / f"{release_id}.lock"), timeout=60), db.transaction():
        # Serialize all competing inputs for this dataset/period, not only identical inputs.
        lock = int.from_bytes(
            hashlib.sha256(f"{DATASET}:{snapshot}".encode()).digest()[:8], signed=True
        )
        db.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
        if db.execute(
            "SELECT 1 FROM catalog.release WHERE id=%s AND status='published'", (release_id,)
        ).fetchone():
            db.execute(
                "UPDATE catalog.pipeline_run SET release_id=%s,status='succeeded',"
                "finished_at=now() WHERE id=%s",
                (release_id, run_id),
            )
            return release_id
        previous = db.execute(
            "SELECT id FROM catalog.release WHERE dataset_id=%s AND reference_period=%s "
            "AND status='published' ORDER BY published_at DESC,id DESC LIMIT 1",
            (DATASET, snapshot),
        ).fetchone()
        latest = previous[0] if previous else None
        if (
            latest != supersedes
            or (supersedes is not None and not (revision_reason or "").strip())
            or (supersedes is None and revision_reason is not None)
        ):
            raise RevisionConflict(
                "Specify the current predecessor and a reason for a new revision"
            )
        differences: list[dict[str, Any]] = []
        if supersedes is not None:
            old = dict(
                db.execute(
                    "SELECT territory_code,value FROM api.observations_v2 WHERE release_id=%s",
                    (supersedes,),
                ).fetchall()
            )
            for row in report["observations"]:
                code = row["territory_code"]
                if code not in old or old[code] != row["population"]:
                    differences.append(
                        {
                            "territory_code": code,
                            "before": str(old.get(code)),
                            "after": str(row["population"]),
                        }
                    )
        curated = _parquet(root, report["observations"])
        db.execute(
            """INSERT INTO catalog.release
            (id,dataset_id,reference_period,retrieved_at,upstream_url,raw_sha256,transform_version,
             contract_sha256,license_url,status,row_count,api_version,metadata_sha256,
             upstream_last_update,upstream_published_at,supersedes_release_id,revision_reason,
             territory_snapshot,series_code,attribution)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,2,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                release_id,
                DATASET,
                snapshot,
                evidence["data"]["retrieved_at"],
                evidence["data"]["url"],
                evidence["data"]["sha256"],
                TRANSFORM_VERSION,
                contract_hash,
                report["license"]["url"],
                report["rows"],
                metadata_hash,
                report["upstream_last_update"],
                report["upstream_published_at"],
                supersedes,
                revision_reason,
                snapshot,
                SERIES,
                report["license"]["attribution"],
            ),
        )
        _load(db, curated, release_id, scheme, snapshot, valid_to)
        actual = db.execute(
            "SELECT count(*),sum(value) FILTER (WHERE t.level='region'),"
            "max(value) FILTER (WHERE t.level='country') FROM stats.observation o "
            "JOIN geo.territory t ON t.id=o.territory_id WHERE release_id=%s",
            (release_id,),
        ).fetchone()
        checks["loaded_row_count"] = actual is not None and actual[0] == report["rows"]
        checks["loaded_reconciliation"] = (
            actual is not None
            and actual[1] == actual[2] == report["reconciliation"]["national_total"]
        )
        if not all(checks.values()):
            raise QualityError({"checks": checks, "rows": report["rows"]})
        quality = _archive_json(
            root,
            {
                "checks": checks,
                "rows": report["rows"],
                "release_id": str(release_id),
                "reconciliation": report["reconciliation"],
                "supersedes_release_id": supersedes,
                "revision_reason": revision_reason,
                "changed_values": differences,
            },
        )
        artifacts = {
            "raw": root / evidence["data"]["path"],
            "curated": curated,
            "quality": quality,
            "structure": root / evidence["structure"]["path"],
            "dataflow": root / evidence["dataflow"]["path"],
            "contract": contract_path,
            "onboarding_contract": root / evidence["contract_path"],
            "license": license_path,
            "onboarding": report_path,
            **{
                f"{name}_manifest": root / evidence[name]["manifest_path"]
                for name in ("data", "structure", "dataflow")
            },
        }
        for kind, path in artifacts.items():
            db.execute(
                "INSERT INTO catalog.artifact VALUES (%s,%s,%s,%s,%s)",
                (
                    release_id,
                    kind,
                    path.relative_to(root).as_posix(),
                    sha256_file(path),
                    path.stat().st_size,
                ),
            )
        for name, passed in checks.items():
            db.execute(
                "INSERT INTO catalog.quality_result VALUES (%s,%s,%s,%s)",
                (
                    release_id,
                    name,
                    passed,
                    Jsonb(
                        {
                            "rows": report["rows"],
                            "reconciliation": report["reconciliation"],
                            "changed_values": differences
                            if name == "national_reconciliation"
                            else [],
                        }
                    ),
                ),
            )
        db.execute("UPDATE catalog.release SET status='validated' WHERE id=%s", (release_id,))
        db.execute(
            "UPDATE catalog.release SET status='published',published_at=now() WHERE id=%s",
            (release_id,),
        )
        db.execute(
            "UPDATE catalog.pipeline_run SET release_id=%s,status='succeeded',"
            "finished_at=now() WHERE id=%s",
            (release_id, run_id),
        )
    return release_id
