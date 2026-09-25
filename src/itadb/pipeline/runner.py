"""Publish explicitly invented aggregate fixtures through the same immutable archive path."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from itadb.config import Settings
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import normalize_demo
from itadb.serving.publication import add_evidence, add_source, insert, publication
from itadb.serving.sql import row

TRANSFORM_VERSION = "population-demo/2.0.0"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"


def ingest_demo(settings: Settings, source: Path, contract: Path) -> UUID:
    raw, checksum = archive_file(source, settings.data_dir / "raw")
    contract_hash = sha256_file(contract)
    rid = uuid5(NAMESPACE_URL, f"demo_population:{checksum}:{TRANSFORM_VERSION}:{contract_hash}")
    with publication(settings) as writer:
        db = writer.db
        if db.execute("SELECT 1 FROM api.releases WHERE id=?", [rid]).fetchone():
            return rid
        curated = settings.data_dir / "curated" / str(rid) / "observations.parquet"
        report = normalize_demo(raw, curated, contract)
        quality_path = settings.data_dir / "reports" / f"{rid}.json"
        atomic_json(quality_path, report)
        add_source(db, "demo", True)
        now = datetime.now(UTC)
        release = dict(
            id=rid,
            dataset_id="demo_population",
            title="Popolazione dimostrativa",
            limitations="Valori e territori inventati. Non usare per analisi.",
            source_id="demo",
            is_demo=True,
            reference_period=report["reference_period"],
            retrieved_at=now,
            published_at=now,
            upstream_url="urn:itadb:fixture:population-demo",
            raw_sha256=checksum,
            transform_version=TRANSFORM_VERSION,
            contract_sha256=contract_hash,
            license_url=LICENSE_URL,
            row_count=report["rows"],
        )
        insert(db, "releases", release)
        insert(
            db,
            "releases_v2",
            {
                **release,
                "series_code": "population_total",
                "territory_snapshot": report["reference_period"],
                "attribution": "Fixture inventata CC0",
            },
        )
        db.execute("CREATE TEMP TABLE demo AS SELECT * FROM read_parquet(?)", [str(curated)])
        if db.execute("""SELECT 1 FROM demo d JOIN api.observations o USING(territory_code)
                      WHERE o.scheme='ITADB_DEMO' AND o.territory_name<>d.territory_name LIMIT
        1""").fetchone():
            raise ValueError("Territory label changed without a new territorial version")
        start = row(db.execute("SELECT coalesce(max(territory_id),0) FROM api.observations_v2"))[0]
        db.execute(
            """INSERT INTO api.observations SELECT ?,'population_total','persons',
            ?+row_number() OVER (ORDER BY
        territory_code),territory_code,territory_name,'ITADB_DEMO',
            period,population,'demo' FROM demo""",
            [rid, start],
        )
        db.execute(
            """INSERT INTO api.observations_v2 SELECT *, 'municipality',NULL,'','','',''
                      FROM api.observations WHERE release_id=?""",
            [rid],
        )
        if db.execute(
            "SELECT count(*) FROM api.observations WHERE release_id=?", [rid]
        ).fetchone() != (report["rows"],):
            raise ValueError("Loaded row count differs")
        add_evidence(
            db,
            rid,
            report["checks"],
            {"rows": report["rows"]},
            {"raw": raw, "curated": curated, "quality": quality_path},
            v1=True,
        )
        writer.changed = True
    return rid
