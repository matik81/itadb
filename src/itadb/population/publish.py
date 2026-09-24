"""Atomically import verified population snapshots into the serving database."""

import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

import duckdb
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from itadb.config import Settings
from itadb.pipeline.geography import admin_code, shape_records
from itadb.pipeline.storage import atomic_json, sha256_file
from itadb.population.cartography import import_provinces
from itadb.synthesis.national_runner import check_files
from itadb.synthesis.population_models import PopulationInput
from itadb.synthesis.population_runner import verify_population

PUBLISH_VERSION = "population-serving/1"
TABLES = ("person", "household", "cell", "validation")


def partition(kind: str, sid: int) -> sql.Identifier:
    if kind not in TABLES or sid <= 0:
        raise ValueError("Invalid population partition")
    return sql.Identifier("population", f"{kind}_{sid}")


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


def _geography(db: psycopg.Connection[Any], sid: int, root: Path, inputs: PopulationInput) -> None:
    if inputs.national.evidence_kind == "invented_load_fixture":
        rows = [
            (
                sid,
                int(m.code),
                f"Comune inventato {m.code}",
                int(m.province),
                "Provincia inventata",
                int(m.region),
                "Regione inventata",
                m.population,
                m.household_total,
            )
            for m in inputs.national.municipalities
        ]
    else:
        digest = inputs.national.source_hashes["geography"]
        path = root / "raw" / digest[:2] / digest / "payload"
        if sha256_file(path) != digest:
            raise ValueError("Geography checksum differs")
        regions, provinces, localities = {}, {}, {}
        db.execute(
            "CREATE TEMP TABLE geometry_input(level text,code integer,shape text) ON COMMIT DROP"
        )
        with db.cursor().copy("COPY geometry_input FROM STDIN") as copy:
            for level, record, shape in shape_records(path):
                code = admin_code(level, record)
                if level == "region":
                    regions[code] = record["DEN_REG"]
                elif level == "province":
                    provinces[code] = record["DEN_UTS"]
                else:
                    localities[code] = record["COMUNE"]
                if level != "province":
                    copy.write_row((level, int(code), json.dumps(shape.__geo_interface__)))
        rows = [
            (
                sid,
                int(m.code),
                localities[m.code],
                int(m.province),
                provinces[m.province],
                int(m.region),
                regions[m.region],
                m.population,
                m.household_total,
            )
            for m in inputs.national.municipalities
        ]
        for code, name in regions.items():
            db.execute(
                "INSERT INTO population.region(snapshot_id,code,name) VALUES(%s,%s,%s)",
                (sid, int(code), name),
            )
        # Display geometries only; exact source bytes remain in the generation archive.
        db.execute(
            """UPDATE population.region r SET boundary=ST_Multi(ST_CollectionExtract(
            ST_SimplifyPreserveTopology(ST_Transform(ST_MakeValid(ST_SetSRID(
                ST_GeomFromGeoJSON(g.shape),32632)),4326),0.01),3))
            FROM geometry_input g WHERE r.snapshot_id=%s AND g.level='region' AND r.code=g.code""",
            (sid,),
        )
    with db.cursor().copy(
        "COPY population.municipality(snapshot_id,code,name,province_code,province_name,"
        "region_code,region_name,persons,households) FROM STDIN"
    ) as copy:
        for row in rows:
            copy.write_row(row)
    if inputs.national.evidence_kind != "invented_load_fixture":
        db.execute(
            """UPDATE population.municipality m SET
            boundary=ST_Multi(ST_CollectionExtract(ST_SimplifyPreserveTopology(g.geom,0.002),3)),
            center=ST_PointOnSurface(g.geom) FROM (
                SELECT code,ST_Transform(
                ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(shape),32632)),4326) geom
                FROM geometry_input WHERE level='municipality') g
            WHERE m.snapshot_id=%s AND m.code=g.code""",
            (sid,),
        )


def _copy_parquet(
    db: psycopg.Connection[Any], sid: int, kind: str, path: Path, scratch: Path
) -> None:
    fields = (
        (
            "person_id,household_id,municipality::INTEGER,sex,birth_year,birth_year_upper_bound,"
            "citizenship_code::SMALLINT,reference_adult"
        )
        if kind == "person"
        else ("household_id,municipality::INTEGER,size")
    )
    target = scratch / "batch.csv"
    with duckdb.connect() as con:
        con.execute("SET memory_limit='256MB'")
        con.execute("SET threads=2")
        con.read_parquet(str(path)).create_view("batch")
        con.execute(
            f"COPY (SELECT {sid},{fields} FROM batch) TO ? (FORMAT CSV,HEADER false)", [str(target)]
        )
    with (
        db.cursor().copy(
            sql.SQL("COPY {} FROM STDIN WITH (FORMAT CSV)").format(partition(kind, sid))
        ) as copy,
        target.open("rb") as stream,
    ):
        while block := stream.read(1024 * 1024):
            copy.write(block)
    target.unlink()


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
    db: psycopg.Connection[Any], sid: int, inputs: PopulationInput, emit: Callable[[str], None]
) -> dict[str, Any]:
    year = int(inputs.national.population_reference[:4]) - 1
    emit("Controllo delle relazioni fra persone, famiglie e territori")
    invalid = db.execute(
        """SELECT EXISTS(SELECT 1 FROM population.person p
        LEFT JOIN population.municipality m ON m.snapshot_id=p.snapshot_id AND
        m.code=p.municipality_code
        WHERE p.snapshot_id=%s AND (m.code IS NULL OR
        (p.birth_year IS NOT NULL AND p.birth_year NOT BETWEEN %s-99 AND %s) OR
        (p.birth_year_upper_bound IS NOT NULL AND p.birth_year_upper_bound<>%s-100) OR
        (coalesce(p.birth_year,p.birth_year_upper_bound)>%s-18 AND p.household_id IS NULL)))""",
        (sid, year, year, year, year),
    ).fetchone()
    if invalid != (False,):
        raise ValueError("Invalid person geography, birth cohort or unassigned minor")
    # Set-based relationship check: no foreign-key trigger for every copied person.
    invalid = db.execute(
        """WITH members AS (
        SELECT household_id,count(*) n,min(municipality_code) lo,max(municipality_code) hi,
        count(*) FILTER(WHERE reference_adult) refs,
        count(*) FILTER(WHERE reference_adult AND
        coalesce(birth_year,birth_year_upper_bound)>%s-18) minors
        FROM population.person WHERE snapshot_id=%s AND household_id IS NOT NULL GROUP BY
        household_id)
        SELECT EXISTS(SELECT 1 FROM (SELECT * FROM population.household WHERE snapshot_id=%s) h
        FULL JOIN members p USING(household_id)
        WHERE
        (h.household_id IS NULL OR p.household_id IS NULL OR h.size<>p.n OR
         h.municipality_code<>p.lo OR p.lo<>p.hi OR p.refs<>1 OR p.minors<>0))""",
        (year, sid, sid),
    ).fetchone()
    if invalid != (False,):
        raise ValueError("Household relationships differ from snapshot constraints")
    emit("Distribuzioni calcolate dai record PostgreSQL")
    db.execute(
        sql.SQL("""INSERT INTO {} SELECT snapshot_id,municipality_code,sex,
        coalesce(%s-birth_year,100),citizenship_code,count(*) FROM population.person
        WHERE snapshot_id=%s
        GROUP BY snapshot_id,municipality_code,sex,birth_year,citizenship_code""").format(
            partition("cell", sid)
        ),
        (year, sid),
    )
    db.execute(
        "CREATE TEMP TABLE expected(municipality_code integer,kind text,sex "
        "text,category smallint,n bigint) ON COMMIT DROP"
    )
    with db.cursor().copy("COPY expected FROM STDIN") as copy:
        for row in _expected(inputs):
            copy.write_row(row)
    db.execute(
        """CREATE TEMP TABLE actual ON COMMIT DROP AS
        SELECT municipality_code,'sex_age'::text kind,sex,age category,sum(persons)::bigint n
        FROM population.cell WHERE snapshot_id=%s GROUP BY municipality_code,sex,age
        UNION ALL SELECT municipality_code,'foreign_age',sex,age,sum(persons)::bigint
        FROM population.cell WHERE snapshot_id=%s AND citizenship_code<>100 GROUP BY
        municipality_code,sex,age
        UNION ALL SELECT municipality_code,'citizenship',sex,citizenship_code,sum(persons)::bigint
        FROM population.cell WHERE snapshot_id=%s GROUP BY municipality_code,sex,citizenship_code
        UNION ALL SELECT municipality_code,'household_size','*',size,count(*)
        FROM population.household WHERE snapshot_id=%s GROUP BY municipality_code,size""",
        (sid, sid, sid, sid),
    )
    emit("Confronto integrale con i vincoli demografici, STR/RCS e familiari")
    db.execute(
        sql.SQL("""INSERT INTO {} SELECT %s,coalesce(e.municipality_code,a.municipality_code),
        coalesce(e.kind,a.kind),coalesce(e.sex,a.sex),coalesce(e.category,a.category),
        coalesce(e.n,0),coalesce(a.n,0) FROM expected e FULL JOIN actual a
        USING(municipality_code,kind,sex,category)""").format(partition("validation", sid)),
        (sid,),
    )
    result = db.execute(
        "SELECT count(*),max(abs(expected-actual)) FROM population.validation WHERE snapshot_id=%s",
        (sid,),
    ).fetchone()
    if result is None or result[1] != 0:
        raise ValueError("Database distributions differ from admitted source counts")
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
    committed_id: int | None = None
    attempt = uuid4().hex
    reports = settings.data_dir / "reports" / "population-publication"
    reports.mkdir(parents=True, exist_ok=True)
    log = reports / f"{attempt}.log"

    def emit(message: str) -> None:
        line = f"Pubblicazione popolazione · {time.monotonic() - started:.1f}s · {message}"
        print(line, flush=True)
        with log.open("a") as stream:
            stream.write(line + "\n")

    try:
        emit("Audit indipendente dello snapshot prima di accedere al database")
        manifest = verify_population(directory)
        inputs = PopulationInput.model_validate_json((directory / "input.json").read_bytes())
        fixture = inputs.national.evidence_kind == "invented_load_fixture"
        if fixture and not allow_fixture:
            raise ValueError(
                "The application importer requires an official-input population snapshot"
            )
        provenance = (
            {
                "sources": [],
                "attribution": ["Fixture inventata CC0"],
                "country_labels": inputs.citizenship.country_labels,
            }
            if fixture
            else evidence(settings.data_dir, inputs)
        )
        provenance["model"] = manifest["descriptor"]["reference"]
        provenance["execution_order"] = manifest["descriptor"]["execution_order"]
        provenance["algorithm"] = manifest["descriptor"]["algorithm"]
        provenance["input_sha256"] = manifest["descriptor"]["input_sha256"]
        report = json.loads((directory / "report.json").read_bytes())
        checksum = sha256_file(directory / "manifest.json")
        with (
            psycopg.connect(settings.admin_database_url) as db,
            TemporaryDirectory(prefix="itadb-publish-") as temporary,
        ):
            db.execute("SELECT pg_advisory_xact_lock(%s)", (int(manifest["run_id"][:15], 16),))
            existing = db.execute(
                "SELECT id,manifest_sha256,status FROM population.snapshot WHERE run_id=%s",
                (manifest["run_id"],),
            ).fetchone()
            if existing:
                if existing[1:] != (checksum, "published"):
                    raise ValueError("Existing serving snapshot identity differs")
                emit(f"Esito: snapshot {existing[0]} già pubblicato, nessun duplicato")
                return int(existing[0])
            row = db.execute(
                """INSERT INTO population.snapshot(run_id,manifest_sha256,reference_date,
                household_reference,persons,households,municipalities,is_fixture,report,provenance)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    manifest["run_id"],
                    checksum,
                    inputs.national.population_reference,
                    inputs.national.household_reference,
                    report["persons"],
                    report["households"],
                    len(inputs.national.municipalities),
                    fixture,
                    Jsonb(report),
                    Jsonb(provenance),
                ),
            ).fetchone()
            assert row is not None
            sid = int(row[0])
            for kind in TABLES:
                db.execute(
                    sql.SQL("CREATE TABLE {} PARTITION OF {} FOR VALUES IN ({})").format(
                        partition(kind, sid), sql.Identifier("population", kind), sql.Literal(sid)
                    )
                )
                db.execute(
                    sql.SQL(
                        "CREATE TRIGGER immutable_partition BEFORE INSERT OR UPDATE OR "
                        "DELETE OR TRUNCATE ON {} FOR EACH STATEMENT EXECUTE FUNCTION "
                        "population.guard_partition({})"
                    ).format(partition(kind, sid), sql.Literal(str(sid)))
                )
            emit("Geografia e provenienza dello stesso riferimento della popolazione")
            _geography(db, sid, settings.data_dir, inputs)
            import_provinces(db, sid, settings.data_dir)
            folders = sorted(directory.glob("batch-*"))
            for index, folder in enumerate(folders, 1):
                emit(f"COPY batch {index}/{len(folders)}: famiglie e individui")
                _copy_parquet(db, sid, "household", folder / "households.parquet", Path(temporary))
                _copy_parquet(db, sid, "person", folder / "persons.parquet", Path(temporary))
            emit("Aggiornamento statistiche degli indici")
            for kind in ("person", "household"):
                db.execute(sql.SQL("ANALYZE {}").format(partition(kind, sid)))
            checks = _validate(db, sid, inputs, emit)
            # Reject source changes even if they occur between audit and COPY.
            check_files(directory, manifest["files"], "manifest.json")
            if sha256_file(directory / "manifest.json") != checksum:
                raise ValueError("Snapshot changed during publication")
            db.execute(
                (
                    "UPDATE population.snapshot SET publication_checks=%s,"
                    "status='published',published_at=now() WHERE id=%s"
                ),
                (Jsonb(checks), sid),
            )
            db.commit()
            committed_id = sid
            emit(
                f"Esito: snapshot {sid} pubblicato, {report['persons']:,} individui "
                f"e {report['households']:,} famiglie"
            )
            atomic_json(
                reports / f"{attempt}.json",
                {
                    "snapshot_id": sid,
                    "run_id": manifest["run_id"],
                    "persons": report["persons"],
                    "households": report["households"],
                    "elapsed_seconds": time.monotonic() - started,
                    "checks": checks,
                },
            )
            return sid
    except Exception as error:
        outcome = (
            "pubblicazione annullata"
            if committed_id is None
            else f"snapshot {committed_id} pubblicato; rapporto locale non completato"
        )
        emit(f"Esito: {outcome} ({type(error).__name__})")
        atomic_json(
            settings.data_dir / "quarantine" / f"population-publication-{attempt}.json",
            {
                "published": committed_id is not None,
                "snapshot_id": committed_id,
                "error_type": type(error).__name__,
            },
        )
        raise
