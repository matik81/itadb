"""Publish audited Parquet snapshots directly into a new immutable DuckDB archive."""

import csv
import json
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb

from itadb.config import Settings
from itadb.pipeline.storage import sha256_file
from itadb.population.cartography import load_population_geography
from itadb.serving.publication import insert, publication
from itadb.serving.sql import row
from itadb.synthesis.national_runner import check_files
from itadb.synthesis.population_models import PopulationInput
from itadb.synthesis.population_runner import verify_population

PUBLISH_VERSION = "population-duckdb/1"


def evidence(root: Path, inputs: PopulationInput) -> dict[str, Any]:
    sources = []
    for family, hashes in [
        ("national", inputs.national.source_hashes),
        ("citizenship", inputs.citizenship.source_hashes),
    ]:
        digest = hashes["contract"]
        path = root / "raw" / digest[:2] / digest / "payload"
        if sha256_file(path) != digest:
            raise ValueError("Source contract checksum differs")
        contract = json.loads(path.read_bytes())
        for name, spec in contract["sources"].items():
            if hashes[name] != spec["sha256"]:
                raise ValueError("Snapshot provenance differs from source contract")
            sources.append({"group": family, "name": name, **spec})
    return {
        "sources": sources,
        "attribution": [inputs.national.attribution, inputs.citizenship.attribution],
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "country_labels": inputs.citizenship.country_labels,
    }


def _expected(inputs: PopulationInput) -> Iterable[tuple[int, str, str, int, int]]:
    for m in inputs.national.municipalities:
        for sex, counts in [("M", m.male), ("F", m.female)]:
            for age, count in enumerate(counts):
                yield int(m.code), "sex_age", sex, age, count
        for size, count in enumerate(m.households, 1):
            yield int(m.code), "household_size", "*", size, count
    for citizen in inputs.citizenship.municipalities:
        for sex, counts in [("M", citizen.foreign_male), ("F", citizen.foreign_female)]:
            for age, count in enumerate(counts):
                yield int(citizen.code), "foreign_age", sex, age, count
        for country, counts in citizen.countries.items():
            for sex, count in zip(["M", "F"], counts, strict=True):
                yield int(citizen.code), "citizenship", sex, int(country), count


def _validate(
    db: duckdb.DuckDBPyConnection, sid: int, inputs: PopulationInput, emit: Callable[[str], None]
) -> dict[str, Any]:
    emit("Controllo degli identificativi e delle relazioni")
    for table, identity in (
        ("population_persons", "person_id"),
        ("population_households", "household_id"),
    ):
        if db.execute(
            f"SELECT 1 FROM api.{table} WHERE snapshot_id=? GROUP BY {identity} "
            f"HAVING count(*)<>1 OR {identity} IS NULL OR {identity}<1 LIMIT 1",
            [sid],
        ).fetchone():
            raise ValueError("Invalid or duplicate record identity")
    invalid = db.execute(
        """SELECT 1 FROM api.population_persons p
        LEFT JOIN api.population_municipalities m ON m.snapshot_id=p.snapshot_id
        AND m.code=p.municipality_code WHERE p.snapshot_id=? AND
        (m.code IS NULL OR p.sex IS NULL OR p.sex NOT IN ('M','F')
        OR p.age NOT BETWEEN 0 AND 100 OR p.age IS NULL
        OR p.citizenship_code IS NULL OR p.citizenship_code NOT BETWEEN 1 AND 999
        OR p.reference_adult IS NULL OR p.reference_date IS DISTINCT FROM ?::DATE
        OR p.data_kind IS DISTINCT FROM 'synthetic'
        OR p.age_is_lower_bound IS DISTINCT FROM (p.birth_year IS NULL)
        OR (p.birth_year IS NULL)=(p.birth_year_upper_bound IS NULL)
        OR (p.birth_year_upper_bound IS NOT NULL AND p.age<>100)
        OR (p.birth_year_upper_bound IS NOT NULL AND p.birth_year_upper_bound<>?)
        OR (p.birth_year IS NOT NULL AND (p.age<>?-p.birth_year OR p.age>=100))
        OR (p.household_id IS NULL AND (p.age<18 OR p.reference_adult))) LIMIT 1""",
        [
            sid,
            inputs.national.population_reference,
            int(inputs.national.population_reference[:4]) - 101,
            int(inputs.national.population_reference[:4]) - 1,
        ],
    ).fetchone()
    if invalid:
        raise ValueError("Invalid person geography, cohort or unassigned minor")
    invalid = db.execute(
        """WITH members AS (
        SELECT household_id,count(*) n,min(municipality_code) lo,max(municipality_code) hi,
        count(*) FILTER(WHERE reference_adult) refs,
        count(*) FILTER(WHERE reference_adult AND age<18) minors
        FROM api.population_persons WHERE snapshot_id=? AND household_id IS NOT NULL
        GROUP BY household_id)
        SELECT 1 FROM (SELECT * FROM api.population_households WHERE snapshot_id=?) h
        FULL JOIN members p USING(household_id) WHERE
        h.household_id IS NULL OR p.household_id IS NULL OR h.size IS NULL OR h.size<>p.n
        OR h.municipality_code IS NULL OR h.municipality_code<>p.lo
        OR h.data_kind IS DISTINCT FROM 'synthetic'
        OR p.lo<>p.hi OR p.refs<>1 OR p.minors<>0 LIMIT 1""",
        [sid, sid],
    ).fetchone()
    if invalid:
        raise ValueError("Household relationships differ from snapshot constraints")
    emit("Ricalcolo delle distribuzioni dai record DuckDB")
    db.execute(
        """INSERT INTO api.population_cells SELECT p.snapshot_id,p.municipality_code,
        p.sex,p.age,p.citizenship_code,count(*),m.region_code,m.province_code
        FROM api.population_persons p JOIN api.population_municipalities m
        ON m.snapshot_id=p.snapshot_id AND m.code=p.municipality_code WHERE p.snapshot_id=?
        GROUP BY ALL ORDER BY p.municipality_code,p.age,p.sex,p.citizenship_code""",
        [sid],
    )
    with TemporaryDirectory(prefix="itadb-expected-") as temporary:
        path = Path(temporary) / "expected.csv"
        with path.open("w", newline="") as stream:
            csv.writer(stream).writerows(_expected(inputs))
        db.execute(
            """CREATE TEMP TABLE expected AS SELECT * FROM read_csv(?,header=false,
            columns={'municipality_code':'INTEGER','kind':'VARCHAR','sex':'VARCHAR',
                     'category':'SMALLINT','n':'BIGINT'})""",
            [str(path)],
        )
    db.execute(
        """CREATE TEMP TABLE actual AS
        SELECT municipality_code,'sex_age' kind,sex,age category,sum(persons)::bigint n
        FROM api.population_cells WHERE snapshot_id=? GROUP BY municipality_code,sex,age
        UNION ALL SELECT municipality_code,'foreign_age',sex,age,sum(persons)::bigint
        FROM api.population_cells WHERE snapshot_id=? AND citizenship_code<>100
        GROUP BY municipality_code,sex,age
        UNION ALL SELECT municipality_code,'citizenship',sex,citizenship_code,sum(persons)::bigint
        FROM api.population_cells WHERE snapshot_id=? GROUP BY
        municipality_code,sex,citizenship_code
        UNION ALL SELECT municipality_code,'household_size','*',size,count(*)
        FROM api.population_households WHERE snapshot_id=? GROUP BY municipality_code,size""",
        [sid] * 4,
    )
    emit("Confronto integrale dei vincoli demografici e familiari")
    db.execute(
        """INSERT INTO api.population_validation
        SELECT ?,coalesce(e.municipality_code,a.municipality_code),coalesce(e.kind,a.kind),
        coalesce(e.sex,a.sex),coalesce(e.category,a.category),coalesce(e.n,0),coalesce(a.n,0)
        FROM expected e FULL JOIN actual a USING(municipality_code,kind,sex,category)
        ORDER BY 2,3,5,4""",
        [sid],
    )
    result = db.execute(
        "SELECT count(*),max(abs(expected-actual)) FROM api.population_validation "
        "WHERE snapshot_id=?",
        [sid],
    ).fetchone()
    if result is None or result[1] != 0:
        raise ValueError("Database distributions differ from admitted source counts")
    for table, expected_count in [
        ("population_persons", sum(m.population for m in inputs.national.municipalities)),
        ("population_households", sum(m.household_total for m in inputs.national.municipalities)),
    ]:
        if db.execute(
            f"SELECT count(*) FROM api.{table} WHERE snapshot_id=?", [sid]
        ).fetchone() != (expected_count,):
            raise ValueError("Imported record count differs")
    return {
        "snapshot_audit": True,
        "database_constraints": True,
        "database_relationships": True,
        "constraints_checked": result[0],
        "max_absolute_error": result[1],
        "publisher": PUBLISH_VERSION,
    }


def publish_population(settings: Settings, directory: Path, *, allow_fixture: bool = False) -> int:
    started = time.monotonic()

    def emit(message: str) -> None:
        print(f"Pubblicazione · {time.monotonic() - started:.1f}s · {message}", flush=True)

    with publication(settings) as writer:
        db = writer.db
        emit("Audit indipendente dello snapshot")
        manifest = verify_population(directory)
        inputs = PopulationInput.model_validate_json((directory / "input.json").read_bytes())
        fixture = inputs.national.evidence_kind == "invented_load_fixture"
        if fixture and not allow_fixture:
            raise ValueError(
                "The application importer requires an official-input population snapshot"
            )
        checksum = sha256_file(directory / "manifest.json")
        existing = db.execute(
            "SELECT id,manifest_sha256 FROM api.population_snapshots WHERE run_id=?",
            [manifest["run_id"]],
        ).fetchone()
        if existing:
            if existing[1] != checksum:
                raise ValueError("Existing snapshot identity differs")
            emit(f"Snapshot {existing[0]} già pubblicato")
            return int(existing[0])
        provenance = (
            {
                "sources": [],
                "attribution": ["Fixture inventata CC0"],
                "country_labels": inputs.citizenship.country_labels,
            }
            if fixture
            else evidence(settings.data_dir, inputs)
        )
        provenance.update(
            {
                key: manifest["descriptor"][key]
                for key in ("execution_order", "algorithm", "input_sha256")
            }
        )
        provenance["model"] = manifest["descriptor"]["reference"]
        report = json.loads((directory / "report.json").read_bytes())
        sid = int(row(db.execute("SELECT coalesce(max(id),0)+1 FROM api.population_snapshots"))[0])
        insert(
            db,
            "population_snapshots",
            {
                "id": sid,
                "run_id": manifest["run_id"],
                "manifest_sha256": checksum,
                "reference_date": inputs.national.population_reference,
                "household_reference": inputs.national.household_reference,
                "persons": report["persons"],
                "households": report["households"],
                "municipalities": len(inputs.national.municipalities),
                "is_fixture": fixture,
                "published_at": datetime.now(UTC),
                "data_kind": "synthetic",
                "located_persons": 0,
                "report": json.dumps(report),
                "provenance": json.dumps(provenance),
            },
        )
        load_population_geography(db, sid, settings.data_dir, inputs)
        folders = sorted(directory.glob("batch-*"))
        year = int(inputs.national.population_reference[:4]) - 1
        for index, folder in enumerate(folders, 1):
            emit(f"Importazione Parquet {index}/{len(folders)}")
            db.execute(
                """INSERT INTO api.population_households SELECT ?,household_id,
                municipality::INTEGER,size,'synthetic' FROM read_parquet(?) ORDER BY
        household_id""",
                [sid, str(folder / "households.parquet")],
            )
            db.execute(
                """INSERT INTO api.population_persons SELECT ?,person_id,household_id,
municipality::INTEGER,sex,birth_year,birth_year_upper_bound,citizenship_code::SMALLINT,
                reference_adult,?::DATE,coalesce(?-birth_year,100),birth_year IS NULL,'synthetic'
                FROM read_parquet(?) ORDER BY municipality,person_id""",
                [sid, inputs.national.population_reference, year, str(folder / "persons.parquet")],
            )
        checks = _validate(db, sid, inputs, emit)
        check_files(directory, manifest["files"], "manifest.json")
        if sha256_file(directory / "manifest.json") != checksum:
            raise ValueError("Snapshot changed during publication")
        db.execute(
            "UPDATE api.population_snapshots SET publication_checks=? WHERE id=?",
            [json.dumps(checks), sid],
        )
        writer.changed = True
        emit(f"Verificati {report['persons']:,} individui e {report['households']:,} famiglie")
    emit(f"Snapshot {sid} pubblicato nell'archivio di preparazione")
    return sid
