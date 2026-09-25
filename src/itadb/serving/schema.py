"""Version 1 of the complete public serving schema; no source data."""

SCHEMA: dict[str, dict[str, str]] = {
    "artifacts_v2": {
        "release_id": "UUID",
        "kind": "VARCHAR",
        "sha256": "VARCHAR",
        "byte_size": "BIGINT",
    },
    "boundaries_v2": {
        "release_id": "UUID",
        "territory_id": "BIGINT",
        "geometry": "JSON",
        "simplification_degrees": "DOUBLE",
    },
    "coverage_v2": {
        "release_id": "UUID",
        "series_code": "VARCHAR",
        "title": "VARCHAR",
        "unit": "VARCHAR",
        "dimensions": "JSON",
        "period": "DATE",
        "scheme": "VARCHAR",
        "territory_snapshot": "DATE",
        "row_count": "BIGINT",
    },
    "crosswalks_v2": {
        "id": "BIGINT",
        "release_id": "UUID",
        "event_id": "VARCHAR",
        "kind": "VARCHAR",
        "effective_date": "DATE",
        "source_url": "VARCHAR",
        "evidence_sha256": "VARCHAR",
        "description": "VARCHAR",
        "from_code": "VARCHAR",
        "from_scheme": "VARCHAR",
        "to_code": "VARCHAR",
        "to_scheme": "VARCHAR",
        "allocation_weight": "DECIMAL(20,12)",
        "weight_basis": "VARCHAR",
    },
    "observations": {
        "release_id": "UUID",
        "series_code": "VARCHAR",
        "unit": "VARCHAR",
        "territory_id": "BIGINT",
        "territory_code": "VARCHAR",
        "territory_name": "VARCHAR",
        "scheme": "VARCHAR",
        "period": "DATE",
        "value": "DECIMAL(20,6)",
        "status": "VARCHAR",
    },
    "observations_v2": {
        "release_id": "UUID",
        "series_code": "VARCHAR",
        "unit": "VARCHAR",
        "territory_id": "BIGINT",
        "territory_code": "VARCHAR",
        "territory_name": "VARCHAR",
        "scheme": "VARCHAR",
        "period": "DATE",
        "value": "DECIMAL(20,6)",
        "status": "VARCHAR",
        "level": "VARCHAR",
        "parent_code": "VARCHAR",
        "upstream_status": "VARCHAR",
        "upstream_note": "VARCHAR",
        "upstream_unit": "VARCHAR",
        "upstream_unit_multiplier": "VARCHAR",
    },
    "population_cells": {
        "snapshot_id": "BIGINT",
        "municipality_code": "INTEGER",
        "sex": "VARCHAR",
        "age": "SMALLINT",
        "citizenship_code": "SMALLINT",
        "persons": "BIGINT",
        "region_code": "SMALLINT",
        "province_code": "SMALLINT",
    },
    "population_households": {
        "snapshot_id": "BIGINT",
        "household_id": "BIGINT",
        "municipality_code": "INTEGER",
        "size": "SMALLINT",
        "data_kind": "VARCHAR",
    },
    "population_municipalities": {
        "snapshot_id": "BIGINT",
        "code": "INTEGER",
        "name": "VARCHAR",
        "province_code": "SMALLINT",
        "province_name": "VARCHAR",
        "region_code": "SMALLINT",
        "region_name": "VARCHAR",
        "persons": "BIGINT",
        "households": "BIGINT",
        "geometry": "JSON",
        "longitude": "DOUBLE",
        "latitude": "DOUBLE",
    },
    "population_persons": {
        "snapshot_id": "BIGINT",
        "person_id": "BIGINT",
        "household_id": "BIGINT",
        "municipality_code": "INTEGER",
        "sex": "VARCHAR",
        "birth_year": "SMALLINT",
        "birth_year_upper_bound": "SMALLINT",
        "citizenship_code": "SMALLINT",
        "reference_adult": "BOOLEAN",
        "reference_date": "DATE",
        "age": "INTEGER",
        "age_is_lower_bound": "BOOLEAN",
        "data_kind": "VARCHAR",
    },
    "population_provinces": {
        "snapshot_id": "BIGINT",
        "code": "SMALLINT",
        "region_code": "SMALLINT",
        "name": "VARCHAR",
        "source_sha256": "VARCHAR",
        "geometry": "JSON",
    },
    "population_regions": {
        "snapshot_id": "BIGINT",
        "code": "SMALLINT",
        "name": "VARCHAR",
        "geometry": "JSON",
    },
    "population_snapshots": {
        "id": "BIGINT",
        "run_id": "VARCHAR",
        "manifest_sha256": "VARCHAR",
        "reference_date": "DATE",
        "household_reference": "DATE",
        "persons": "BIGINT",
        "households": "BIGINT",
        "municipalities": "INTEGER",
        "is_fixture": "BOOLEAN",
        "published_at": "TIMESTAMPTZ",
        "data_kind": "VARCHAR",
        "located_persons": "BIGINT",
        "report": "JSON",
        "provenance": "JSON",
        "publication_checks": "JSON",
    },
    "population_validation": {
        "snapshot_id": "BIGINT",
        "municipality_code": "INTEGER",
        "kind": "VARCHAR",
        "sex": "VARCHAR",
        "category": "SMALLINT",
        "expected": "BIGINT",
        "actual": "BIGINT",
    },
    "quality": {
        "release_id": "UUID",
        "check_name": "VARCHAR",
        "passed": "BOOLEAN",
        "details": "JSON",
    },
    "quality_v2": {
        "release_id": "UUID",
        "check_name": "VARCHAR",
        "passed": "BOOLEAN",
        "details": "JSON",
    },
    "releases": {
        "id": "UUID",
        "dataset_id": "VARCHAR",
        "title": "VARCHAR",
        "limitations": "VARCHAR",
        "source_id": "VARCHAR",
        "is_demo": "BOOLEAN",
        "reference_period": "DATE",
        "retrieved_at": "TIMESTAMPTZ",
        "published_at": "TIMESTAMPTZ",
        "upstream_url": "VARCHAR",
        "raw_sha256": "VARCHAR",
        "transform_version": "VARCHAR",
        "contract_sha256": "VARCHAR",
        "license_url": "VARCHAR",
        "row_count": "BIGINT",
    },
    "releases_v2": {
        "id": "UUID",
        "dataset_id": "VARCHAR",
        "title": "VARCHAR",
        "limitations": "VARCHAR",
        "source_id": "VARCHAR",
        "is_demo": "BOOLEAN",
        "reference_period": "DATE",
        "retrieved_at": "TIMESTAMPTZ",
        "published_at": "TIMESTAMPTZ",
        "upstream_url": "VARCHAR",
        "raw_sha256": "VARCHAR",
        "transform_version": "VARCHAR",
        "contract_sha256": "VARCHAR",
        "license_url": "VARCHAR",
        "row_count": "BIGINT",
        "metadata_sha256": "VARCHAR",
        "upstream_last_update": "TIMESTAMPTZ",
        "upstream_published_at": "TIMESTAMPTZ",
        "supersedes_release_id": "UUID",
        "revision_reason": "VARCHAR",
        "territory_snapshot": "DATE",
        "series_code": "VARCHAR",
        "attribution": "VARCHAR",
    },
    "sources": {
        "id": "VARCHAR",
        "name": "VARCHAR",
        "homepage": "VARCHAR",
        "license_url": "VARCHAR",
        "is_demo": "BOOLEAN",
    },
    "territories_v2": {
        "release_id": "UUID",
        "territory_id": "BIGINT",
        "scheme": "VARCHAR",
        "code": "VARCHAR",
        "name": "VARCHAR",
        "level": "VARCHAR",
        "valid_from": "DATE",
        "valid_to": "DATE",
        "parent_code": "VARCHAR",
        "snapshot": "DATE",
        "has_boundary": "BOOLEAN",
    },
}

EXPORT_QUERIES: dict[str, str] = {
    "artifacts_v2": ('SELECT "release_id","kind","sha256","byte_size" FROM api.artifacts_v2'),
    "boundaries_v2": (
        "SELECT release_id,territory_id,ST_AsGeoJSON(geom,5)::json AS geometry,0.001"
        "::double precision AS simplification_degrees FROM (SELECT release_id,territ"
        "ory_id,ST_Multi(ST_SimplifyPreserveTopology(geom,0.001)) AS geom FROM api.b"
        "oundaries_v2) b WHERE ST_NPoints(geom)<=20000"
    ),
    "coverage_v2": (
        'SELECT "release_id","series_code","title","unit","dimensions","period","sch'
        'eme","territory_snapshot","row_count" FROM api.coverage_v2'
    ),
    "crosswalks_v2": (
        'SELECT "id","release_id","event_id","kind","effective_date","source_url","e'
        'vidence_sha256","description","from_code","from_scheme","to_code","to_schem'
        'e","allocation_weight","weight_basis" FROM api.crosswalks_v2'
    ),
    "observations": (
        'SELECT "release_id","series_code","unit","territory_id","territory_code","t'
        'erritory_name","scheme","period","value","status" FROM api.observations'
    ),
    "observations_v2": (
        'SELECT "release_id","series_code","unit","territory_id","territory_code","t'
        'erritory_name","scheme","period","value","status","level","parent_code","up'
        'stream_status","upstream_note","upstream_unit","upstream_unit_multiplier" F'
        "ROM api.observations_v2"
    ),
    "population_cells": (
        'SELECT "snapshot_id","municipality_code","sex","age","citizenship_code","pe'
        'rsons","region_code","province_code" FROM api.population_cells'
    ),
    "population_households": (
        'SELECT "snapshot_id","household_id","municipality_code","size","data_kind" '
        "FROM api.population_households"
    ),
    "population_municipalities": (
        'SELECT "snapshot_id","code","name","province_code","province_name","region_'
        'code","region_name","persons","households",ST_AsGeoJSON(boundary,5)::json A'
        "S geometry,ST_X(center) AS longitude,ST_Y(center) AS latitude FROM api.popu"
        "lation_municipalities"
    ),
    "population_persons": (
        'SELECT "snapshot_id","person_id","household_id","municipality_code","sex","'
        'birth_year","birth_year_upper_bound","citizenship_code","reference_adult","'
        'reference_date","age","age_is_lower_bound","data_kind" FROM api.population_'
        "persons"
    ),
    "population_provinces": (
        'SELECT "snapshot_id","code","region_code","name","source_sha256",ST_AsGeoJS'
        "ON(boundary,5)::json AS geometry FROM api.population_provinces"
    ),
    "population_regions": (
        'SELECT "snapshot_id","code","name",ST_AsGeoJSON(boundary,5)::json AS geomet'
        "ry FROM api.population_regions"
    ),
    "population_snapshots": (
        'SELECT "id","run_id","manifest_sha256","reference_date","household_referenc'
        'e","persons","households","municipalities","is_fixture","published_at","dat'
        'a_kind","located_persons","report","provenance","publication_checks" FROM a'
        "pi.population_snapshots"
    ),
    "population_validation": (
        'SELECT "snapshot_id","municipality_code","kind","sex","category","expected"'
        ',"actual" FROM api.population_validation'
    ),
    "quality": ('SELECT "release_id","check_name","passed","details" FROM api.quality'),
    "quality_v2": ('SELECT "release_id","check_name","passed","details" FROM api.quality_v2'),
    "releases": (
        'SELECT "id","dataset_id","title","limitations","source_id","is_demo","refer'
        'ence_period","retrieved_at","published_at","upstream_url","raw_sha256","tra'
        'nsform_version","contract_sha256","license_url","row_count" FROM api.releas'
        "es"
    ),
    "releases_v2": (
        'SELECT "id","dataset_id","title","limitations","source_id","is_demo","refer'
        'ence_period","retrieved_at","published_at","upstream_url","raw_sha256","tra'
        'nsform_version","contract_sha256","license_url","row_count","metadata_sha25'
        '6","upstream_last_update","upstream_published_at","supersedes_release_id","'
        'revision_reason","territory_snapshot","series_code","attribution" FROM api.'
        "releases_v2"
    ),
    "sources": ('SELECT "id","name","homepage","license_url","is_demo" FROM api.sources'),
    "territories_v2": (
        'SELECT "release_id","territory_id","scheme","code","name","level","valid_fr'
        'om","valid_to","parent_code","snapshot","has_boundary" FROM api.territories'
        "_v2"
    ),
}

# Preserve the source database's textual ordering, including punctuation and accents,
# independently of libc/ICU versions and the deployment host's locale.
SCHEMA["text_order"] = {"value": "VARCHAR", "ordinal": "BIGINT"}
TEXT_ORDER_INPUTS = (
    "SELECT id AS value FROM api.sources",
    "SELECT kind FROM api.artifacts_v2",
    "SELECT check_name FROM api.quality",
    "SELECT check_name FROM api.quality_v2",
    "SELECT series_code FROM api.coverage_v2",
    "SELECT territory_name FROM api.observations_v2",
    "SELECT territory_code FROM api.observations_v2",
    "SELECT description FROM api.crosswalks_v2",
    "SELECT from_code FROM api.crosswalks_v2",
    "SELECT to_code FROM api.crosswalks_v2",
    "SELECT weight_basis FROM api.crosswalks_v2",
    "SELECT DISTINCT kind FROM api.population_validation",
    "SELECT unnest(ARRAY['Dimostrativo','Mancante','Osservato','Riservato','—','Stimato'])",
)
EXPORT_QUERIES["text_order"] = (
    "SELECT value,dense_rank() OVER (ORDER BY value)::bigint ordinal FROM ("
    + " UNION ".join(TEXT_ORDER_INPUTS)
    + ") strings WHERE value IS NOT NULL"
)
