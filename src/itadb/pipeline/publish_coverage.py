"""Atomic, repeatable publication of validated M2 aggregate evidence."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import duckdb
import psycopg
from psycopg.types.json import Jsonb

from itadb.config import Settings
from itadb.pipeline.coverage import Bundle, validate_bundle
from itadb.pipeline.geography import boundary_rows
from itadb.pipeline.publish_istat import RevisionConflict
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError

TRANSFORM_VERSION = "territorial-demographic/publication-1.0.0"


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
    db: psycopg.Connection[Any],
    root: Path,
    rid: UUID,
    bundle: Bundle,
) -> dict[str, Any]:
    db.execute("""CREATE TEMP TABLE staged_territory(key text PRIMARY KEY,scheme text,code text,
        name text,level text,valid_from date,valid_to date,snapshot date,parent_key text,
        id bigint) ON COMMIT DROP""")
    with db.cursor().copy(
        "COPY staged_territory "
        "(key,scheme,code,name,level,valid_from,valid_to,snapshot,parent_key) FROM STDIN"
    ) as copy:
        for t in bundle.territories:
            copy.write_row(
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
                )
            )
    # Serialize shared dimensions, including competing datasets and geography-only releases.
    db.execute("SELECT pg_advisory_xact_lock(72193403)")
    for level in ("country", "region", "province", "municipality"):
        db.execute(
            """INSERT INTO geo.territory(scheme,code,name,level,valid_from,valid_to,parent_id)
            SELECT st.scheme,st.code,st.name,st.level,st.valid_from,st.valid_to,p.id
            FROM staged_territory st LEFT JOIN staged_territory p ON p.key=st.parent_key
            WHERE st.level=%s ON CONFLICT (scheme,code,valid_from) DO NOTHING""",
            (level,),
        )
        db.execute(
            """UPDATE staged_territory st SET id=t.id FROM geo.territory t
            WHERE t.scheme=st.scheme AND t.code=st.code AND t.valid_from=st.valid_from
            AND st.level=%s""",
            (level,),
        )
    if db.execute("""SELECT 1 FROM staged_territory st JOIN geo.territory t ON t.id=st.id
        LEFT JOIN staged_territory p ON p.key=st.parent_key
        WHERE t.name<>st.name OR t.level<>st.level OR t.valid_to IS DISTINCT FROM st.valid_to
        OR t.parent_id IS DISTINCT FROM p.id LIMIT 1""").fetchone():
        raise ValueError("Geographic definition differs from existing evidence")
    db.execute(
        "INSERT INTO geo.release_territory SELECT %s,id,snapshot FROM staged_territory", (rid,)
    )
    db.execute(
        "CREATE TEMP TABLE staged_boundary(key text PRIMARY KEY,geom geometry) ON COMMIT DROP"
    )
    evidence = {e.name: e for e in bundle.evidence}
    for source in bundle.boundaries:
        db.execute("CREATE TEMP TABLE boundary_input(key text,geojson text) ON COMMIT DROP")
        count = 0
        with db.cursor().copy("COPY boundary_input FROM STDIN") as copy:
            for key, geom in boundary_rows(
                root / evidence[source.evidence_name].path, source.snapshot, source.format
            ):
                copy.write_row((key, geom))
                count += 1
                if count % 1000 == 0:
                    print(f"Confini {source.snapshot}: {count:,} geometrie caricate", flush=True)
        db.execute(
            """INSERT INTO staged_boundary
            SELECT key,ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(geojson),%s),4326))
            FROM boundary_input""",
            (source.source_srid,),
        )
        db.execute("DROP TABLE boundary_input")
    repairs = db.execute("""SELECT key,ST_IsValidReason(geom) FROM staged_boundary
        WHERE NOT ST_IsValid(geom) ORDER BY key""").fetchall()
    if {r[0] for r in repairs} != set(bundle.boundary_repair_keys):
        raise QualityError(
            {
                "checks": {"reviewed_boundary_repairs": False},
                "invalid_keys": [r[0] for r in repairs],
            }
        )
    repair_details = []
    for key, reason in repairs:
        difference = db.execute(
            """SELECT abs(ST_Area(geom)-ST_Area(fixed))/NULLIF(ST_Area(fixed),0)
            FROM (SELECT geom,ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),3)) AS fixed
            FROM staged_boundary WHERE key=%s) b""",
            (key,),
        ).fetchone()
        if (
            difference is None
            or difference[0] is None
            or difference[0] > bundle.boundary_area_tolerance
        ):
            raise QualityError({"checks": {"repair_area_conservation": False}, "key": key})
        repair_details.append({"key": key, "reason": reason, "relative_area_change": difference[0]})
        db.execute(
            "UPDATE staged_boundary SET geom=ST_Multi(ST_CollectionExtract(ST_MakeValid(geom),3)) "
            "WHERE key=%s",
            (key,),
        )
    invalid = db.execute("""SELECT count(*) FROM staged_boundary WHERE NOT ST_IsValid(geom)
        OR ST_IsEmpty(geom) OR GeometryType(geom)<>'MULTIPOLYGON'
        OR NOT ST_CoveredBy(geom,ST_MakeEnvelope(6,35,19,48,4326))""").fetchone()
    if invalid is None or invalid[0]:
        raise QualityError(
            {
                "checks": {"valid_italian_boundaries": False},
                "invalid": invalid[0] if invalid else None,
            }
        )
    if db.execute("""SELECT 1 FROM staged_territory t FULL JOIN staged_boundary b USING(key)
        WHERE (t.level<>'country' AND b.key IS NULL) OR t.key IS NULL
        OR (t.level='country' AND b.key IS NOT NULL) LIMIT 1""").fetchone():
        raise ValueError("Boundary coverage differs from territorial coverage")
    # Generalized borders can differ slightly across scales. Use area tolerance,
    # retaining originals and recording only contract-reviewed topological repairs.
    outside = db.execute("""SELECT coalesce(max(ST_Area(ST_Difference(b.geom,pb.geom)::geography)
        / NULLIF(ST_Area(b.geom::geography),0)),0)
        FROM staged_boundary b JOIN staged_territory t USING(key)
        JOIN staged_boundary pb ON pb.key=t.parent_key""").fetchone()
    if bundle.derive_parent_boundaries:
        # Preserve source shapes in the archive; publish explicitly derived parent
        # outlines so all levels use exactly the same municipal partition.
        for level in ("province", "region"):
            db.execute(
                """UPDATE staged_boundary p SET geom=q.geom FROM (
                SELECT t.parent_key,ST_Multi(ST_UnaryUnion(ST_Collect(b.geom))) AS geom
                FROM staged_boundary b JOIN staged_territory t USING(key)
                JOIN staged_territory parent ON parent.key=t.parent_key
                WHERE parent.level=%s GROUP BY t.parent_key) q WHERE p.key=q.parent_key""",
                (level,),
            )
        if db.execute("""SELECT 1 FROM staged_boundary b JOIN staged_territory t USING(key)
            JOIN staged_boundary p ON p.key=t.parent_key
            WHERE NOT ST_CoveredBy(b.geom,p.geom) OR NOT ST_IsValid(p.geom) LIMIT 1""").fetchone():
            raise QualityError({"checks": {"derived_boundary_hierarchy": False}})
    elif outside is None or outside[0] > 0.02:
        raise QualityError(
            {
                "checks": {"boundary_hierarchy": False},
                "max_outside_fraction": outside[0] if outside else None,
            }
        )
    db.execute(
        """INSERT INTO geo.boundary SELECT t.id,%s,b.geom
        FROM staged_boundary b JOIN staged_territory t USING(key)""",
        (rid,),
    )
    for event in bundle.changes:
        db.execute(
            "INSERT INTO geo.change_event VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                rid,
                event.event_id,
                event.kind,
                event.effective_date,
                event.source_url,
                event.evidence_sha256,
                event.description,
            ),
        )
        for before in event.from_keys:
            for after in event.to_keys:
                db.execute(
                    """INSERT INTO geo.crosswalk(release_id,event_id,from_territory_id,
                    to_territory_id,allocation_weight,weight_basis)
                    SELECT %s,%s,f.id,t.id,%s,%s FROM staged_territory f
                    CROSS JOIN staged_territory t WHERE f.key=%s AND t.key=%s""",
                    (
                        rid,
                        event.event_id,
                        1 if event.weight_basis == "exact" else None,
                        event.weight_basis,
                        before,
                        after,
                    ),
                )
    return {
        "repairs": repair_details,
        "source_max_outside_parent_fraction": outside[0] if outside else None,
        "parent_boundaries": "union_of_children" if bundle.derive_parent_boundaries else "source",
        "outside_parent_tolerance": 0.02,
        "repair_area_tolerance": bundle.boundary_area_tolerance,
    }


def _load_observations(
    db: psycopg.Connection[Any],
    rid: UUID,
    bundle: Bundle,
    curated: Path,
) -> None:
    for s in bundle.series:
        db.execute(
            "INSERT INTO stats.series(code,title,unit,dimensions) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (code) DO NOTHING",
            (s.code, s.title, s.unit, Jsonb(s.dimensions)),
        )
        actual = db.execute(
            "SELECT title,unit,dimensions FROM stats.series WHERE code=%s", (s.code,)
        ).fetchone()
        if actual != (s.title, s.unit, s.dimensions):
            raise ValueError("Series differs from its immutable definition")
    for c in bundle.coverage:
        db.execute(
            """INSERT INTO catalog.coverage
            SELECT %s,id,%s,%s,%s,%s FROM stats.series WHERE code=%s""",
            (rid, c.period, c.scheme, c.snapshot, len(c.territory_keys), c.series_code),
        )
    db.execute("""CREATE TEMP TABLE staged_observation(territory_key text,series_code text,
        period date,value numeric(20,6),status text,upstream_status text,upstream_note text,
        upstream_unit text,upstream_unit_multiplier text) ON COMMIT DROP""")
    with (
        duckdb.connect() as analytical,
        db.cursor().copy("COPY staged_observation FROM STDIN") as copy,
    ):
        result = analytical.execute("SELECT * FROM read_parquet(?)", [str(curated)])
        while batch := result.fetchmany(1000):
            for row in batch:
                copy.write_row(row)
    db.execute(
        """INSERT INTO stats.observation
        SELECT %s,s.id,t.id,o.period,o.value,o.status,o.upstream_status,o.upstream_note,
            o.upstream_unit,o.upstream_unit_multiplier
        FROM staged_observation o JOIN staged_territory t ON t.key=o.territory_key
        JOIN stats.series s ON s.code=o.series_code""",
        (rid,),
    )
    mismatch = db.execute(
        """SELECT 1 FROM staged_observation e
        JOIN staged_territory t ON t.key=e.territory_key JOIN stats.series s ON s.code=e.series_code
        LEFT JOIN stats.observation o ON o.release_id=%s AND o.series_id=s.id
        AND o.territory_id=t.id AND o.period=e.period
        WHERE o.release_id IS NULL OR o.value IS DISTINCT FROM e.value
        OR o.status<>e.status OR o.upstream_status<>e.upstream_status
        OR o.upstream_note<>e.upstream_note OR o.upstream_unit<>e.upstream_unit
        OR o.upstream_unit_multiplier<>e.upstream_unit_multiplier LIMIT 1""",
        (rid,),
    ).fetchone()
    if mismatch:
        raise ValueError("Loaded values differ from the validated Parquet")


def publish_coverage(
    settings: Settings,
    bundle: Bundle,
    contract: Path,
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
            with db.transaction():
                lock = int.from_bytes(
                    hashlib.sha256(bundle.dataset_id.encode()).digest()[:8], signed=True
                )
                db.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
                if db.execute(
                    "SELECT 1 FROM catalog.release WHERE id=%s AND status='published'", (rid,)
                ).fetchone():
                    db.execute(
                        "UPDATE catalog.pipeline_run SET status='succeeded',release_id=%s,"
                        "finished_at=now() WHERE id=%s",
                        (rid, run_id),
                    )
                    return rid
                prior = db.execute(
                    "SELECT id FROM catalog.release WHERE dataset_id=%s AND reference_period=%s "
                    "AND status='published' ORDER BY published_at DESC,id DESC LIMIT 1",
                    (bundle.dataset_id, bundle.reference_period),
                ).fetchone()
                if (
                    (prior[0] if prior else None) != supersedes
                    or (supersedes is not None and not (revision_reason or "").strip())
                    or (supersedes is None and revision_reason is not None)
                ):
                    raise RevisionConflict("Specify the current predecessor and revision reason")
                source = "demo" if bundle.is_demo else "istat"
                if bundle.is_demo:
                    db.execute(
                        "INSERT INTO catalog.dataset VALUES "
                        "('demo_m2','demo','M2 — fixture inventata','Test del percorso M2',"
                        "'Valori e territori inventati; non usare per analisi.') "
                        "ON CONFLICT DO NOTHING"
                    )
                # The initial series must exist before the release FK is evaluated.
                initial = next(s for s in bundle.series if s.code == bundle.default_series)
                db.execute(
                    "INSERT INTO stats.series(code,title,unit,dimensions) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT DO NOTHING",
                    (initial.code, initial.title, initial.unit, Jsonb(initial.dimensions)),
                )
                if db.execute(
                    "SELECT source_id FROM catalog.dataset WHERE id=%s", (bundle.dataset_id,)
                ).fetchone() != (source,):
                    raise ValueError("Source classification does not match")
                first = bundle.evidence[0]
                curated = _curate(root, bundle)
                db.execute(
                    """INSERT INTO catalog.release(id,dataset_id,reference_period,retrieved_at,
                    upstream_url,raw_sha256,transform_version,contract_sha256,license_url,
                    status,row_count,
                    api_version,metadata_sha256,supersedes_release_id,revision_reason,territory_snapshot,
                    series_code,attribution,publication_kind)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,2,
                    %s,%s,%s,%s,%s,%s,'coverage')""",
                    (
                        rid,
                        bundle.dataset_id,
                        bundle.reference_period,
                        first.retrieved_at,
                        first.url,
                        raw_hash,
                        TRANSFORM_VERSION,
                        contract_hash,
                        bundle.license_url,
                        len(bundle.observations),
                        metadata_hash,
                        supersedes,
                        revision_reason,
                        bundle.reference_period,
                        bundle.default_series,
                        bundle.attribution,
                    ),
                )
                print("Pubblicazione: caricamento delle geografie", flush=True)
                report["geography"] = _load_geography(db, root, rid, bundle)
                print("Pubblicazione: COPY e confronto integrale delle osservazioni", flush=True)
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
                        root,
                        {"territories": [t.model_dump(mode="json") for t in bundle.territories]},
                    ),
                    "crosswalk": archive_json(
                        root, {"events": [e.model_dump(mode="json") for e in bundle.changes]}
                    ),
                    "license": root
                    / next(
                        e.path for e in bundle.evidence if e.name == bundle.license_evidence_name
                    ),
                }
                for kind, path in artifacts.items():
                    db.execute(
                        "INSERT INTO catalog.artifact VALUES (%s,%s,%s,%s,%s)",
                        (
                            rid,
                            kind,
                            path.relative_to(root).as_posix(),
                            sha256_file(path),
                            path.stat().st_size,
                        ),
                    )
                for name, passed in report["checks"].items():
                    db.execute(
                        "INSERT INTO catalog.quality_result VALUES (%s,%s,%s,%s)",
                        (rid, name, passed, Jsonb({"rows": report["rows"]})),
                    )
                db.execute(
                    "UPDATE catalog.release SET status='published',published_at=now() WHERE id=%s",
                    (rid,),
                )
                db.execute(
                    "UPDATE catalog.pipeline_run SET status='succeeded',release_id=%s,"
                    "finished_at=now() WHERE id=%s",
                    (rid, run_id),
                )
            print(f"Pubblicazione completata: {rid}", flush=True)
            return rid
        except Exception as error:
            atomic_json(
                root / "quarantine" / f"coverage-{run_id}.json",
                {
                    "run_id": run_id,
                    "published": False,
                    "error_code": type(error).__name__,
                    "report": error.report if isinstance(error, QualityError) else None,
                },
            )
            db.execute(
                "UPDATE catalog.pipeline_run SET status='failed',finished_at=now(),error_code=%s "
                "WHERE id=%s",
                (type(error).__name__, run_id),
            )
            raise
