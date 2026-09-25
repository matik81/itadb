"""Prepare display geography in DuckDB; no spatial extensions are needed by the API."""

import json
from pathlib import Path
from typing import Any

import duckdb

from itadb.pipeline.geography import admin_code, shape_records
from itadb.pipeline.storage import sha256_file
from itadb.synthesis.population_models import PopulationInput


def load_spatial(db: duckdb.DuckDBPyConnection) -> None:
    try:
        db.execute("LOAD spatial")
    except duckdb.Error as exc:
        raise RuntimeError(
            "Eseguire itadb prepare-spatial prima della pubblicazione cartografica"
        ) from exc


def rounded_geometry(value: str) -> str:
    def rounded(item: Any) -> Any:
        if isinstance(item, float):
            return round(item, 5)
        if isinstance(item, list):
            return [rounded(i) for i in item]
        if isinstance(item, dict):
            return {k: rounded(v) for k, v in item.items()}
        return item

    return json.dumps(rounded(json.loads(value)), separators=(",", ":"))


def display_geometry(db: duckdb.DuckDBPyConnection, original: str, simplified: str) -> str:
    """Keep display approximation within 1% of the source polygon's area."""
    for candidate in (rounded_geometry(simplified), rounded_geometry(original), original):
        accepted = db.execute(
            """WITH shapes AS (SELECT ST_GeomFromGeoJSON(?) source_geom,
            ST_GeomFromGeoJSON(?) candidate)
            SELECT CASE WHEN ST_IsValid(candidate) AND NOT ST_IsEmpty(candidate)
            THEN ST_Area(ST_SymDifference(source_geom,candidate))/ST_Area(source_geom)<=0.01
            ELSE false END FROM shapes""",
            [original, candidate],
        ).fetchone()
        if accepted == (True,):
            return candidate
    raise ValueError("Invalid population display approximation")


def load_population_geography(
    db: duckdb.DuckDBPyConnection, sid: int, root: Path, inputs: PopulationInput
) -> None:
    municipalities = inputs.national.municipalities
    fixture = inputs.national.evidence_kind == "invented_load_fixture"
    names: dict[tuple[str, str], str] = {}
    if not fixture:
        digest = inputs.national.source_hashes["geography"]
        path = root / "raw" / digest[:2] / digest / "payload"
        if sha256_file(path) != digest:
            raise ValueError("Geography checksum differs")
        load_spatial(db)
        db.execute(
            "CREATE TEMP TABLE shapes(level VARCHAR,code INTEGER,region_code INTEGER,"
            "name VARCHAR,shape JSON)"
        )
        source_rows = []
        for level, record, shape in shape_records(path):
            code = admin_code(level, record)
            name = record[
                {"region": "DEN_REG", "province": "DEN_UTS", "municipality": "COMUNE"}[level]
            ]
            names[level, code] = name
            source_rows.append(
                (
                    level,
                    int(code),
                    int(record["COD_REG"]),
                    name,
                    json.dumps(shape.__geo_interface__),
                )
            )
        db.executemany("INSERT INTO shapes VALUES (?,?,?,?,?)", source_rows)
        db.execute("""CREATE TEMP TABLE geometries AS SELECT *,
            ST_Transform(ST_MakeValid(ST_GeomFromGeoJSON(shape)), 'EPSG:32632', 'EPSG:4326',
            always_xy := true) geom FROM shapes""")
        invalid = db.execute("""SELECT 1 FROM geometries
            WHERE ST_IsEmpty(geom) OR NOT ST_IsValid(geom)
            OR NOT ST_CoveredBy(geom,ST_MakeEnvelope(6,35,19,48)) LIMIT 1""").fetchone()
        if invalid:
            raise ValueError("Invalid population display geography")
    rows = [
        (
            sid,
            int(m.code),
            f"Comune inventato {m.code}" if fixture else names["municipality", m.code],
            int(m.province),
            "Provincia inventata" if fixture else names["province", m.province],
            int(m.region),
            "Regione inventata" if fixture else names["region", m.region],
            m.population,
            m.household_total,
        )
        for m in municipalities
    ]
    db.executemany(
        "INSERT INTO api.population_municipalities (snapshot_id,code,name,province_code,"
        "province_name,region_code,region_name,persons,households) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    if fixture:
        return
    for level, tolerance in [("region", 0.01), ("province", 0.002), ("municipality", 0.002)]:
        shapes = db.execute(
            """SELECT code,region_code,name,
            ST_AsGeoJSON(ST_Multi(ST_CollectionExtract(geom,3))),
            ST_AsGeoJSON(ST_Multi(ST_CollectionExtract(ST_SimplifyPreserveTopology(geom,?),3))),
            ST_X(ST_PointOnSurface(geom)),ST_Y(ST_PointOnSurface(geom))
            FROM geometries WHERE level=? ORDER BY code""",
            [tolerance, level],
        ).fetchall()
        for code, region, name, original, simplified, x, y in shapes:
            geometry = display_geometry(db, original, simplified)
            if level == "region":
                db.execute(
                    "INSERT INTO api.population_regions VALUES (?,?,?,?)",
                    [sid, code, name, geometry],
                )
            elif level == "province":
                db.execute(
                    "INSERT INTO api.population_provinces VALUES (?,?,?,?,?,?)",
                    [sid, code, region, name, digest, geometry],
                )
            else:
                db.execute(
                    "UPDATE api.population_municipalities SET geometry=?,longitude=?,latitude=? "
                    "WHERE snapshot_id=? AND code=?",
                    [geometry, x, y, sid, code],
                )
        print(f"Cartografia {level}: {len(shapes)} confini", flush=True)
    if db.execute(
        "SELECT 1 FROM api.population_municipalities "
        "WHERE snapshot_id=? AND geometry IS NULL LIMIT 1",
        [sid],
    ).fetchone():
        raise ValueError("Incomplete municipal geography")
    if sha256_file(path) != digest:
        raise ValueError("Geography changed during publication")
