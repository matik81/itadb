"""Publish the reviewed regional slice directly to a verified DuckDB archive."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import duckdb

from itadb.config import Settings
from itadb.pipeline.istat_population import check_population_sample
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError
from itadb.serving.publication import add_evidence, add_source, check_revision, insert, publication
from itadb.serving.sql import row

TRANSFORM_VERSION = "istat-population-regions/publication-2.0.0"
DATASET = "istat_population_regions"
SERIES = "resident_population_jan1"


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
    with publication(settings) as writer:
        rid = _publish(
            writer.db,
            settings.data_dir,
            acquisition,
            structure,
            dataflow,
            onboarding_contract,
            publication_contract,
            license_evidence,
            supersedes,
            revision_reason,
        )
        writer.changed = rid[1]
        return rid[0]


def _publish(
    db: duckdb.DuckDBPyConnection,
    root: Path,
    acquisition: Path,
    structure: Path,
    dataflow: Path,
    onboarding_contract: Path,
    publication_contract: Path,
    license_evidence: Path,
    supersedes: UUID | None,
    revision_reason: str | None,
) -> tuple[UUID, bool]:
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
    if db.execute("SELECT 1 FROM api.releases_v2 WHERE id=?", [release_id]).fetchone():
        return release_id, False
    check_revision(db, DATASET, snapshot, supersedes, revision_reason)
    differences = []
    if supersedes is not None:
        old = dict(
            db.execute(
                "SELECT territory_code,value FROM api.observations_v2 WHERE release_id=?",
                [supersedes],
            ).fetchall()
        )
        differences = [
            {
                "territory_code": r["territory_code"],
                "before": str(old.get(r["territory_code"])),
                "after": str(r["population"]),
            }
            for r in report["observations"]
            if old.get(r["territory_code"]) != r["population"]
        ]
    curated = _parquet(root, report["observations"])
    add_source(db, "istat", False)
    insert(
        db,
        "releases_v2",
        dict(
            id=release_id,
            dataset_id=DATASET,
            title="Popolazione residente regionale",
            limitations="Campione regionale: Italia e regioni; non sommare livelli sovrapposti.",
            source_id="istat",
            is_demo=False,
            reference_period=snapshot,
            retrieved_at=evidence["data"]["retrieved_at"],
            published_at=datetime.now(UTC),
            upstream_url=evidence["data"]["url"],
            raw_sha256=evidence["data"]["sha256"],
            transform_version=TRANSFORM_VERSION,
            contract_sha256=contract_hash,
            license_url=report["license"]["url"],
            row_count=report["rows"],
            metadata_sha256=metadata_hash,
            upstream_last_update=report["upstream_last_update"],
            upstream_published_at=report["upstream_published_at"],
            supersedes_release_id=supersedes,
            revision_reason=revision_reason,
            territory_snapshot=snapshot,
            series_code=SERIES,
            attribution=report["license"]["attribution"],
        ),
    )
    start = row(db.execute("SELECT coalesce(max(territory_id),0) FROM api.observations_v2"))[0]
    db.execute(
        """INSERT INTO api.observations_v2 SELECT ?,?,'persons',
        ?+row_number() OVER (ORDER BY
        territory_code),territory_code,territory_name,?,period,population,
        status,level,CASE WHEN level='region' THEN 'IT' END,
        upstream_status,upstream_note,upstream_unit,upstream_unit_multiplier FROM
        read_parquet(?)""",
        [release_id, SERIES, start, scheme, str(curated)],
    )
    actual = db.execute(
        """SELECT count(*),sum(value) FILTER(WHERE level='region'),
        max(value) FILTER(WHERE level='country') FROM api.observations_v2 WHERE release_id=?""",
        [release_id],
    ).fetchone()
    checks["loaded_row_count"] = actual is not None and actual[0] == report["rows"]
    checks["loaded_reconciliation"] = (
        actual is not None and actual[1] == actual[2] == report["reconciliation"]["national_total"]
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
    add_evidence(
        db,
        release_id,
        checks,
        {
            "rows": report["rows"],
            "reconciliation": report["reconciliation"],
            "changed_values": differences,
        },
        artifacts,
    )
    return release_id, True
