"""Publish validated aggregate evidence and cartography in one immutable DuckDB archive."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import duckdb

from itadb.config import Settings
from itadb.pipeline.coverage import Bundle, validate_bundle
from itadb.pipeline.geography import boundary_rows
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError
from itadb.population.cartography import load_spatial, rounded_geometry
from itadb.serving.publication import add_evidence, add_source, check_revision, insert, publication
from itadb.serving.sql import row

TRANSFORM_VERSION = "territorial-demographic/publication-2.0.0"


def archive_json(root: Path, content: dict[str, Any]) -> Path:
    temporary = root / "state" / f".{uuid4().hex}.json"
    try:
        atomic_json(temporary, content)
        return archive_file(temporary, root / "raw")[0]
    finally:
        temporary.unlink(missing_ok=True)


def _curate(root: Path, bundle: Bundle) -> Path:
    temporary = root / "state" / f".{uuid4().hex}.parquet"
    rows_path = temporary.with_suffix(".jsonl")
    try:
        with rows_path.open("w", encoding="utf-8", newline="\n") as stream:
            for index, observation in enumerate(bundle.observations, 1):
                stream.write(observation.model_dump_json() + "\n")
                if index % 10000 == 0:
                    print(f"Normalizzazione: {index:,} / {len(bundle.observations):,}", flush=True)
        with duckdb.connect() as db:
            db.execute("SET memory_limit='256MB'")
            db.execute("SET threads=2")
            db.execute(
                """CREATE TABLE normalized AS SELECT * FROM read_json(?,format='newline_delimited',
                columns={territory_key:'VARCHAR',series_code:'VARCHAR',period:'DATE',
value:'DECIMAL(20,6)',status:'VARCHAR',upstream_status:'VARCHAR',upstream_note:'VARCHAR',
                upstream_unit:'VARCHAR',upstream_unit_multiplier:'VARCHAR'})""",
                [str(rows_path)],
            )
            db.execute(
                "COPY (SELECT * FROM normalized ORDER BY series_code,period,territory_key) "
                "TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                [str(temporary)],
            )
        return archive_file(temporary, root / "curated")[0]
    finally:
        temporary.unlink(missing_ok=True)
        rows_path.unlink(missing_ok=True)


def _load_geography(
    db: duckdb.DuckDBPyConnection, root: Path, rid: UUID, bundle: Bundle
) -> dict[str, Any]:
    load_spatial(db)
    db.execute("""CREATE TEMP TABLE staged_territory(key VARCHAR PRIMARY KEY,scheme VARCHAR,
        code VARCHAR,name VARCHAR,level VARCHAR,valid_from DATE,valid_to DATE,snapshot DATE,
        parent_key VARCHAR,id BIGINT)""")
    next_id = row(db.execute("SELECT coalesce(max(territory_id),0) FROM api.territories_v2"))[0]
    db.executemany(
        "INSERT INTO staged_territory VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                t.key,
                t.scheme,
                t.code,
                t.name,
                t.level,
                t.valid_from,
                t.valid_to,
                t.snapshot,
                t.parent_key,
                next_id + i,
            )
            for i, t in enumerate(bundle.territories, 1)
        ],
    )
    if db.execute("""SELECT 1 FROM staged_territory s JOIN api.territories_v2 t
        ON s.scheme=t.scheme AND s.code=t.code AND s.valid_from=t.valid_from
        LEFT JOIN staged_territory p ON p.key=s.parent_key
        WHERE s.name<>t.name OR s.level<>t.level OR s.valid_to IS DISTINCT FROM t.valid_to
        OR p.code IS DISTINCT FROM t.parent_code LIMIT 1""").fetchone():
        raise ValueError("Geographic definition differs from existing evidence")
    if db.execute("""SELECT 1 FROM staged_territory s JOIN api.territories_v2 t
        ON s.scheme=t.scheme AND s.code=t.code AND s.valid_from<>t.valid_from
        WHERE s.valid_from<coalesce(t.valid_to,DATE '9999-12-31') AND t.valid_from<s.valid_to
        LIMIT 1""").fetchone():
        raise ValueError("Overlapping territorial validity")
    db.execute("""UPDATE staged_territory s SET id=t.territory_id FROM
        (SELECT DISTINCT scheme,code,valid_from,territory_id FROM api.territories_v2) t
        WHERE s.scheme=t.scheme AND s.code=t.code AND s.valid_from=t.valid_from""")
    db.execute("CREATE TEMP TABLE staged_boundary(key VARCHAR PRIMARY KEY,geom GEOMETRY)")
    evidence = {e.name: e for e in bundle.evidence}
    for source in bundle.boundaries:
        db.execute("CREATE TEMP TABLE boundary_input(key VARCHAR,geojson JSON)")
        rows = list(
            boundary_rows(
                root / evidence[source.evidence_name].path, source.snapshot, source.format
            )
        )
        if rows:
            db.executemany("INSERT INTO boundary_input VALUES (?,?)", rows)
        db.execute(
            """INSERT INTO staged_boundary SELECT key,ST_Multi(ST_Transform(
            ST_GeomFromGeoJSON(geojson),?,'EPSG:4326',always_xy := true)) FROM boundary_input""",
            [f"EPSG:{source.source_srid}"],
        )
        db.execute("DROP TABLE boundary_input")
        print(f"Confini {source.snapshot}: {len(rows):,} geometrie caricate", flush=True)
    repairs = [
        r[0]
        for r in db.execute(
            "SELECT key FROM staged_boundary WHERE NOT ST_IsValid(geom) ORDER BY key"
        ).fetchall()
    ]
    if set(repairs) != set(bundle.boundary_repair_keys):
        raise QualityError(
            {"checks": {"reviewed_boundary_repairs": False}, "invalid_keys": repairs}
        )
    repair_details = []
    for key in repairs:
        difference = db.execute(
            """SELECT abs(ST_Area(geom)-ST_Area(fixed))/nullif(ST_Area(fixed),0)
            FROM (SELECT geom,ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),3)) fixed
                  FROM staged_boundary WHERE key=?)""",
            [key],
        ).fetchone()
        if (
            difference is None
            or difference[0] is None
            or difference[0] > bundle.boundary_area_tolerance
        ):
            raise QualityError({"checks": {"repair_area_conservation": False}, "key": key})
        repair_details.append({"key": key, "relative_area_change": difference[0]})
        db.execute(
            "UPDATE staged_boundary SET geom=ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),3)) "
            "WHERE key=?",
            [key],
        )
    if db.execute("""SELECT 1 FROM staged_boundary WHERE NOT ST_IsValid(geom) OR ST_IsEmpty(geom)
        OR ST_GeometryType(geom)<>'MULTIPOLYGON'
        OR NOT ST_CoveredBy(geom,ST_MakeEnvelope(6,35,19,48)) LIMIT 1""").fetchone():
        raise QualityError({"checks": {"valid_italian_boundaries": False}})
    if db.execute("""SELECT 1 FROM staged_territory t FULL JOIN staged_boundary b USING(key)
        WHERE (t.level<>'country' AND b.key IS NULL) OR t.key IS NULL
        OR (t.level='country' AND b.key IS NOT NULL) LIMIT 1""").fetchone():
        raise ValueError("Boundary coverage differs from territorial coverage")
    outside = row(
        db.execute("""SELECT coalesce(max(ST_Area_Spheroid(
        ST_FlipCoordinates(ST_Difference(b.geom,pb.geom)))
        /nullif(ST_Area_Spheroid(ST_FlipCoordinates(b.geom)),0)),0)
        FROM staged_boundary b JOIN staged_territory t USING(key)
        JOIN staged_boundary pb ON pb.key=t.parent_key""")
    )[0]
    if bundle.derive_parent_boundaries:
        for level in ("province", "region"):
            db.execute(
                """UPDATE staged_boundary p SET geom=q.geom FROM (
                SELECT t.parent_key,ST_Multi(ST_Union_Agg(b.geom)) geom
                FROM staged_boundary b JOIN staged_territory t USING(key)
                JOIN staged_territory parent ON parent.key=t.parent_key WHERE parent.level=?
                GROUP BY t.parent_key) q WHERE p.key=q.parent_key""",
                [level],
            )
        if db.execute("""SELECT 1 FROM staged_boundary b JOIN staged_territory t USING(key)
            JOIN staged_boundary p ON p.key=t.parent_key
            WHERE NOT ST_CoveredBy(b.geom,p.geom) OR NOT ST_IsValid(p.geom) LIMIT 1""").fetchone():
            raise QualityError({"checks": {"derived_boundary_hierarchy": False}})
    elif outside > 0.02:
        raise QualityError(
            {"checks": {"boundary_hierarchy": False}, "max_outside_fraction": outside}
        )
    db.execute(
        """INSERT INTO api.territories_v2 SELECT ?,t.id,t.scheme,t.code,t.name,t.level,
        t.valid_from,t.valid_to,p.code,t.snapshot,b.key IS NOT NULL FROM staged_territory t
        LEFT JOIN staged_territory p ON p.key=t.parent_key
        LEFT JOIN staged_boundary b ON b.key=t.key""",
        [rid],
    )
    geometries = db.execute("""SELECT t.id,ST_AsGeoJSON(geom) FROM (
        SELECT key,ST_Multi(ST_SimplifyPreserveTopology(geom,0.001)) geom FROM staged_boundary) b
        JOIN staged_territory t USING(key) WHERE ST_NPoints(geom)<=20000""").fetchall()
    if geometries:
        db.executemany(
            "INSERT INTO api.boundaries_v2 VALUES (?,?,?,0.001)",
            [(rid, tid, rounded_geometry(geom)) for tid, geom in geometries],
        )
    # has_boundary reflects a retrievable display geometry, including the vertex budget.
    db.execute(
        """UPDATE api.territories_v2 t SET has_boundary=EXISTS(
        SELECT 1 FROM api.boundaries_v2 b WHERE b.release_id=t.release_id AND
        b.territory_id=t.territory_id)
        WHERE t.release_id=?""",
        [rid],
    )
    by_key = {t.key: t for t in bundle.territories}
    cross_id = int(row(db.execute("SELECT coalesce(max(id),0) FROM api.crosswalks_v2"))[0])
    for event in bundle.changes:
        for before in event.from_keys:
            for after in event.to_keys:
                cross_id += 1
                insert(
                    db,
                    "crosswalks_v2",
                    dict(
                        id=cross_id,
                        release_id=rid,
                        event_id=event.event_id,
                        kind=event.kind,
                        effective_date=event.effective_date,
                        source_url=event.source_url,
                        evidence_sha256=event.evidence_sha256,
                        description=event.description,
                        from_code=by_key[before].code,
                        from_scheme=by_key[before].scheme,
                        to_code=by_key[after].code,
                        to_scheme=by_key[after].scheme,
                        allocation_weight=1 if event.weight_basis == "exact" else None,
                        weight_basis=event.weight_basis,
                    ),
                )
    return {
        "repairs": repair_details,
        "source_max_outside_parent_fraction": outside,
        "parent_boundaries": "union_of_children" if bundle.derive_parent_boundaries else "source",
        "outside_parent_tolerance": 0.02,
        "repair_area_tolerance": bundle.boundary_area_tolerance,
    }


def _load_observations(
    db: duckdb.DuckDBPyConnection, rid: UUID, bundle: Bundle, curated: Path
) -> None:
    for series in bundle.series:
        previous = db.execute(
            "SELECT title,unit,dimensions FROM api.coverage_v2 WHERE series_code=? LIMIT 1",
            [series.code],
        ).fetchone()
        if previous and (previous[0], previous[1], json.loads(previous[2])) != (
            series.title,
            series.unit,
            series.dimensions,
        ):
            raise ValueError("Series differs from its immutable definition")
    series_by_code = {s.code: s for s in bundle.series}
    for c in bundle.coverage:
        s = series_by_code[c.series_code]
        insert(
            db,
            "coverage_v2",
            dict(
                release_id=rid,
                series_code=s.code,
                title=s.title,
                unit=s.unit,
                dimensions=json.dumps(s.dimensions),
                period=c.period,
                scheme=c.scheme,
                territory_snapshot=c.snapshot,
                row_count=len(c.territory_keys),
            ),
        )
    db.execute(
        "CREATE TEMP TABLE staged_observation AS SELECT * FROM read_parquet(?)", [str(curated)]
    )
    db.execute("CREATE TEMP TABLE series(code VARCHAR,unit VARCHAR)")
    db.executemany("INSERT INTO series VALUES (?,?)", [(s.code, s.unit) for s in bundle.series])
    db.execute(
        """INSERT INTO api.observations_v2 SELECT ?,o.series_code,s.unit,t.id,t.code,t.name,
        t.scheme,o.period,o.value,o.status,t.level,p.code,o.upstream_status,o.upstream_note,
        o.upstream_unit,o.upstream_unit_multiplier FROM staged_observation o
        JOIN staged_territory t ON t.key=o.territory_key LEFT JOIN staged_territory p ON
        p.key=t.parent_key
        JOIN series s ON s.code=o.series_code""",
        [rid],
    )
    actual = db.execute(
        "SELECT count(*) FROM api.observations_v2 WHERE release_id=?", [rid]
    ).fetchone()
    if actual != (len(bundle.observations),):
        raise ValueError("Loaded observation count differs")
    if db.execute(
        """SELECT 1 FROM staged_observation e JOIN staged_territory t ON t.key=e.territory_key
        LEFT JOIN api.observations_v2 o ON o.release_id=? AND o.series_code=e.series_code
        AND o.territory_id=t.id AND o.period=e.period WHERE o.release_id IS NULL
        OR o.value IS DISTINCT FROM e.value OR o.status<>e.status
        OR o.upstream_status IS DISTINCT FROM e.upstream_status OR o.upstream_note IS DISTINCT
        FROM e.upstream_note
        OR o.upstream_unit IS DISTINCT FROM e.upstream_unit
        OR o.upstream_unit_multiplier IS DISTINCT FROM e.upstream_unit_multiplier LIMIT 1""",
        [rid],
    ).fetchone():
        raise ValueError("Loaded values differ from validated Parquet")


def publish_coverage(
    settings: Settings,
    bundle: Bundle,
    contract: Path,
    supersedes: UUID | None = None,
    revision_reason: str | None = None,
) -> UUID:
    root = settings.data_dir
    with publication(settings) as writer:
        db = writer.db
        report = validate_bundle(bundle)
        contract_path, contract_hash = archive_file(contract, root / "raw")
        for item in bundle.evidence:
            path = (root / item.path).resolve()
            if not path.is_relative_to(root.resolve()) or sha256_file(path) != item.sha256:
                raise ValueError("Evidence path or checksum does not match")
            archive_file(path, root / "raw")
        raw = archive_json(root, bundle.model_dump(mode="json"))
        raw_hash = sha256_file(raw)
        metadata_hash = hashlib.sha256(
            json.dumps(sorted((e.name, e.sha256, e.url) for e in bundle.evidence)).encode()
        ).hexdigest()
        rid = uuid5(
            NAMESPACE_URL,
            ":".join(
                (bundle.dataset_id, raw_hash, contract_hash, metadata_hash, TRANSFORM_VERSION)
            ),
        )
        if db.execute("SELECT 1 FROM api.releases_v2 WHERE id=?", [rid]).fetchone():
            return rid
        check_revision(db, bundle.dataset_id, bundle.reference_period, supersedes, revision_reason)
        curated = _curate(root, bundle)
        source = "demo" if bundle.is_demo else "istat"
        add_source(db, source, bundle.is_demo)
        first = bundle.evidence[0]
        insert(
            db,
            "releases_v2",
            dict(
                id=rid,
                dataset_id=bundle.dataset_id,
                title="Aggregati territoriali",
                limitations="Valori e territori inventati."
                if bundle.is_demo
                else "Copertura limitata agli input ammessi.",
                source_id=source,
                is_demo=bundle.is_demo,
                reference_period=bundle.reference_period,
                retrieved_at=first.retrieved_at,
                published_at=datetime.now(UTC),
                upstream_url=first.url,
                raw_sha256=raw_hash,
                transform_version=TRANSFORM_VERSION,
                contract_sha256=contract_hash,
                license_url=bundle.license_url,
                row_count=len(bundle.observations),
                metadata_sha256=metadata_hash,
                supersedes_release_id=supersedes,
                revision_reason=revision_reason,
                territory_snapshot=bundle.reference_period,
                series_code=bundle.default_series,
                attribution=bundle.attribution,
            ),
        )
        report["geography"] = _load_geography(db, root, rid, bundle)
        _load_observations(db, rid, bundle, curated)
        report["checks"].update(
            loaded_values=True,
            valid_boundaries=True,
            boundary_coverage=True,
            boundary_hierarchy=True,
        )
        report["reconciliations"] = bundle.reconciliations
        artifacts = {
            "raw": raw,
            "curated": curated,
            "contract": contract_path,
            "quality": archive_json(root, report),
            "evidence": archive_json(
                root, {"items": [e.model_dump(mode="json") for e in bundle.evidence]}
            ),
            "geography": archive_json(
                root, {"territories": [t.model_dump(mode="json") for t in bundle.territories]}
            ),
            "crosswalk": archive_json(
                root, {"events": [e.model_dump(mode="json") for e in bundle.changes]}
            ),
            "license": root
            / next(e.path for e in bundle.evidence if e.name == bundle.license_evidence_name),
        }
        add_evidence(
            db, rid, report["checks"], {"rows": report["rows"], **report["geography"]}, artifacts
        )
        for item in bundle.evidence:
            if sha256_file(root / item.path) != item.sha256:
                raise ValueError("Evidence changed during publication")
        writer.changed = True
    print(f"Pubblicazione completata: {rid}", flush=True)
    return rid
