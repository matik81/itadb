"""Append province boundaries from the already archived snapshot geography."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg

from itadb.config import Settings
from itadb.pipeline.geography import admin_code, shape_records
from itadb.pipeline.storage import sha256_file


def import_provinces(db: psycopg.Connection[Any], sid: int, root: Path) -> int:
    snapshot = db.execute(
        "SELECT is_fixture,provenance FROM population.snapshot WHERE id=%s", (sid,)
    ).fetchone()
    if snapshot is None:
        raise ValueError("Population snapshot not found")
    sources = [
        source
        for source in snapshot[1]["sources"]
        if source["group"] == "national" and source["name"] == "geography"
    ]
    if snapshot[0] and not sources:
        return 0
    if len(sources) != 1:
        raise ValueError("Snapshot geographic source is ambiguous")
    digest = sources[0]["sha256"]
    expected = {
        int(code): (int(region), name)
        for code, region, name in db.execute(
            "SELECT DISTINCT province_code,region_code,province_name "
            "FROM population.municipality WHERE snapshot_id=%s",
            (sid,),
        )
    }
    if not expected:
        raise ValueError("Snapshot geography is missing")
    db.execute("LOCK TABLE population.province IN SHARE ROW EXCLUSIVE MODE")
    existing = dict(
        db.execute(
            "SELECT code,source_sha256 FROM population.province WHERE snapshot_id=%s", (sid,)
        ).fetchall()
    )
    if existing:
        if existing != dict.fromkeys(expected, digest):
            raise ValueError("Existing province cartography differs; no overwrite allowed")
        return len(existing)
    path = root / "raw" / digest[:2] / digest / "payload"
    if sha256_file(path) != digest:
        raise ValueError("Geography checksum differs")
    rows = []
    seen: set[int] = set()
    for level, record, shape in shape_records(path):
        if level != "province":
            continue
        code = int(admin_code(level, record))
        if code not in expected:
            continue
        region, name = int(record["COD_REG"]), record["DEN_UTS"]
        if code in seen or expected[code] != (region, name):
            raise ValueError("Province identity differs from snapshot geography")
        seen.add(code)
        rows.append((code, region, name, json.dumps(shape.__geo_interface__)))
    if seen != set(expected) or sha256_file(path) != digest:
        raise ValueError("Incomplete or changed province source")
    db.execute(
        "CREATE TEMP TABLE province_input(code integer,region_code integer,name text,shape text) "
        "ON COMMIT DROP"
    )
    with db.cursor().copy("COPY province_input FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
    db.execute(
        """INSERT INTO population.province
        (snapshot_id,code,region_code,name,source_sha256,boundary)
        SELECT %s,code,region_code,name,%s,ST_Multi(ST_CollectionExtract(
            ST_SimplifyPreserveTopology(ST_Transform(ST_MakeValid(ST_SetSRID(
            ST_GeomFromGeoJSON(shape),32632)),4326),0.002),3)) FROM province_input""",
        (sid, digest),
    )
    return len(rows)


def publish_boundaries(
    settings: Settings,
    sid: int,
    emit: Callable[[str], None] = print,
) -> int:
    emit(f"Confini provinciali: verifica della fonte dello snapshot {sid}")
    with psycopg.connect(settings.admin_database_url) as db:
        count = import_provinces(db, sid, settings.data_dir)
    emit(f"Confini provinciali disponibili: {count}; individui e famiglie invariati")
    return count
