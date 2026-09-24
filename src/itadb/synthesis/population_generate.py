"""Four ordered stages; household allocation reads already fixed individual attributes."""

import csv
from collections.abc import Callable
from pathlib import Path

import duckdb

from itadb.synthesis.citizenship_generate import assign_citizenship
from itadb.synthesis.citizenship_models import CitizenshipMunicipality
from itadb.synthesis.demography import cohort_reference_year
from itadb.synthesis.national_generate import configure
from itadb.synthesis.national_models import Municipality, ResourceBudget, territorial_seed

ALGORITHM_VERSION = "ordered-population/1.0.0"


def generate_individuals(
    municipalities: list[Municipality],
    citizenships: list[CitizenshipMunicipality],
    reference: str,
    directory: Path,
    person_offset: int,
    budget: ResourceBudget,
    progress: Callable[[str], None],
) -> None:
    """Stages 1–3 contain no household membership or allocation ranks."""
    cohort = cohort_reference_year(reference)
    with duckdb.connect() as con:
        configure(con, budget, directory / "scratch")
        con.execute(
            "CREATE TABLE demography(municipality VARCHAR,sex VARCHAR,age SMALLINT,n BIGINT)"
        )
        cells = directory / "demography.csv"
        with cells.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(
                (m.code, sex, age, n)
                for m in municipalities
                for sex, counts in [("M", m.male), ("F", m.female)]
                for age, n in enumerate(counts)
                if n
            )
        if cells.stat().st_size:
            con.execute("COPY demography FROM ? (HEADER false)", [str(cells)])
        cells.unlink()
        progress("Fase 1/4: espansione sesso/età e identità stabili")
        con.execute(
            """CREATE TABLE people AS SELECT
            ?+row_number() OVER (ORDER BY municipality,sex,age,i) AS person_id,
            municipality,sex,age FROM demography,LATERAL range(n) t(i)""",
            [person_offset],
        )
        progress("Fase 2/4: assegnazione della gerarchia geografica")
        con.execute("CREATE TABLE locality(municipality VARCHAR,province VARCHAR,region VARCHAR)")
        con.executemany(
            "INSERT INTO locality VALUES (?,?,?)",
            [(m.code, m.province, m.region) for m in municipalities],
        )
        con.execute(f"""CREATE VIEW base_persons AS SELECT person_id,municipality,province,region,
            CASE WHEN age<100 THEN {cohort}-age END::SMALLINT AS birth_year,
            CASE WHEN age=100 THEN {cohort}-age END::SMALLINT AS birth_year_upper_bound,
            sex,'synthetic'::VARCHAR AS data_kind FROM people JOIN locality USING(municipality)""")
        progress("Fase 3/4: cittadinanza STR/RCS prima delle famiglie")
        assign_citizenship(con, citizenships, cohort + 1, directory, progress)
        con.execute(
            """COPY (SELECT b.*,coalesce(a.code,'100')::VARCHAR AS citizenship_code
            FROM base_persons b LEFT JOIN assigned a USING(person_id) ORDER BY person_id)
            TO ? (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 122880)""",
            [str(directory / "individuals.parquet")],
        )
    progress("Fasi 1–3 completate: individui con cittadinanza salvati senza legami familiari")


def assign_households(
    municipalities: list[Municipality],
    reference: str,
    directory: Path,
    household_offset: int,
    budget: ResourceBudget,
    progress: Callable[[str], None],
) -> None:
    """Stage 4 adds membership only; age and citizenship remain fixed."""
    progress("Fase 4/4: composizione familiare casuale vincolata; età/cittadinanza non calibrate")
    cohort = cohort_reference_year(reference)
    with duckdb.connect() as con:
        configure(con, budget, directory / "scratch")
        con.read_parquet(str(directory / "individuals.parquet")).create_view("individuals")
        con.execute("""CREATE TABLE locality(municipality VARCHAR,province VARCHAR,
            region VARCHAR,seed UBIGINT,households BIGINT,minors BIGINT)""")
        con.executemany(
            "INSERT INTO locality VALUES (?,?,?,?,?,?)",
            [
                (
                    m.code,
                    m.province,
                    m.region,
                    territorial_seed(m.code),
                    m.household_total,
                    sum(m.male[:18]) + sum(m.female[:18]),
                )
                for m in municipalities
            ],
        )
        # Reconstruct the original cell ordinal to retain the documented random rule.
        con.execute(f"""CREATE TABLE people AS SELECT *,row_number() OVER (
            PARTITION BY municipality,age<18 ORDER BY hash(seed,sex,age,i),sex,age,i
            ) AS allocation_rank FROM (
                SELECT *,row_number() OVER (PARTITION BY municipality,sex,age
                    ORDER BY person_id)-1 AS i FROM (
                    SELECT *,({cohort}-coalesce(birth_year,birth_year_upper_bound))::SMALLINT age
                    FROM individuals)) JOIN locality USING(municipality,province,region)""")
        con.execute("CREATE TABLE sizes(municipality VARCHAR,size SMALLINT,n BIGINT)")
        size_rows = [
            (m.code, size, n) for m in municipalities for size, n in enumerate(m.households, 1) if n
        ]
        if size_rows:
            con.executemany("INSERT INTO sizes VALUES (?,?,?)", size_rows)
        con.execute(
            """CREATE TABLE families AS SELECT
            ?+row_number() OVER (ORDER BY municipality,size,i) AS household_id,municipality,size,
            row_number() OVER (PARTITION BY municipality ORDER BY hash(seed,size,i),size,i)
                AS allocation_rank
            FROM sizes JOIN locality USING(municipality),LATERAL range(n) t(i)""",
            [household_offset],
        )
        con.execute("""CREATE TABLE slots AS SELECT municipality,household_id,
            row_number() OVER (PARTITION BY municipality
                ORDER BY hash(seed,local_id,i),local_id,i) AS allocation_rank
            FROM (SELECT *,row_number() OVER (PARTITION BY municipality
                ORDER BY household_id) local_id FROM families)
            JOIN locality USING(municipality),LATERAL range(size-1) t(i)""")
        con.execute(
            """COPY (SELECT p.person_id,
                CASE WHEN p.age>=18 AND p.allocation_rank<=p.households
                    THEN h.household_id ELSE s.household_id END AS household_id,
                p.municipality,p.province,p.region,p.birth_year,p.birth_year_upper_bound,p.sex,
                (p.age>=18 AND p.allocation_rank<=p.households) AS reference_adult,
                p.data_kind,p.citizenship_code
            FROM people p LEFT JOIN families h ON p.municipality=h.municipality
                AND h.allocation_rank=CASE WHEN p.age>=18 THEN p.allocation_rank END
            LEFT JOIN slots s ON p.municipality=s.municipality
                AND s.allocation_rank=CASE WHEN p.age<18 THEN p.allocation_rank
                    WHEN p.allocation_rank>p.households
                    THEN p.minors+p.allocation_rank-p.households END ORDER BY p.person_id)
            TO ? (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 122880)""",
            [str(directory / "persons.parquet")],
        )
        con.execute(
            """COPY (SELECT household_id,municipality,province,region,size,
                'synthetic'::VARCHAR AS data_kind FROM families JOIN locality USING(municipality)
                ORDER BY household_id)
            TO ? (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 122880)""",
            [str(directory / "households.parquet")],
        )


def generate_population_batch(
    municipalities: list[Municipality],
    citizenships: list[CitizenshipMunicipality],
    reference: str,
    directory: Path,
    person_offset: int,
    household_offset: int,
    budget: ResourceBudget,
    progress: Callable[[str], None],
) -> None:
    for m in municipalities:
        m.check_feasibility()
    directory.mkdir(parents=True, exist_ok=False)
    generate_individuals(
        municipalities, citizenships, reference, directory, person_offset, budget, progress
    )
    assign_households(municipalities, reference, directory, household_offset, budget, progress)
