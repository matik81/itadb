"""Vectorized bounded territorial reconstruction; no Python list of residents."""

import csv
from collections.abc import Callable
from pathlib import Path

import duckdb

from itadb.synthesis.demography import cohort_reference_year
from itadb.synthesis.national_models import Municipality, ResourceBudget, territorial_seed

ALGORITHM_VERSION = "territorial-reconstruction/1.0.0"


def configure(con: duckdb.DuckDBPyConnection, budget: ResourceBudget, scratch: Path) -> None:
    con.execute(f"SET memory_limit='{budget.memory_mb}MB'")
    con.execute(f"SET threads={budget.threads}")
    con.execute("SET temp_directory=?", [str(scratch)])
    con.execute(f"SET max_temp_directory_size='{budget.max_disk_mb}MB'")
    con.execute("SET preserve_insertion_order=false")


def generate_batch(
    municipalities: list[Municipality],
    population_reference: str,
    directory: Path,
    person_offset: int,
    household_offset: int,
    budget: ResourceBudget,
    progress: Callable[[str], None],
) -> None:
    for municipality in municipalities:
        municipality.check_feasibility()
    directory.mkdir(parents=True, exist_ok=False)
    cohort = cohort_reference_year(population_reference)
    with duckdb.connect() as con:
        configure(con, budget, directory / "scratch")
        con.execute("""CREATE TABLE locality(municipality VARCHAR, province VARCHAR,
            region VARCHAR, seed UBIGINT, households BIGINT, minors BIGINT)""")
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
        con.execute("CREATE TABLE cells(municipality VARCHAR, sex VARCHAR, age SMALLINT, n BIGINT)")
        cell_path = directory / "cells.csv"
        with cell_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerows(
                (m.code, sex, age, n)
                for m in municipalities
                for sex, counts in [("M", m.male), ("F", m.female)]
                for age, n in enumerate(counts)
                if n
            )
        con.execute(
            """INSERT INTO cells SELECT * FROM read_csv(?, header=false,
            columns={'municipality':'VARCHAR','sex':'VARCHAR','age':'SMALLINT','n':'BIGINT'})""",
            [str(cell_path)],
        )
        cell_path.unlink()  # Disposable aggregate expansion input created by this attempt.
        con.execute("CREATE TABLE sizes(municipality VARCHAR, size SMALLINT, n BIGINT)")
        size_rows = [
            (m.code, size, n) for m in municipalities for size, n in enumerate(m.households, 1) if n
        ]
        if size_rows:
            con.executemany("INSERT INTO sizes VALUES (?,?,?)", size_rows)
        progress("espansione vettoriale delle celle sesso/età")
        con.execute(
            """CREATE TABLE people AS SELECT
            ? + row_number() OVER (ORDER BY municipality,sex,age,i) AS person_id,
            municipality,sex,age,
            row_number() OVER (PARTITION BY municipality,age<18
                ORDER BY hash(seed,sex,age,i),sex,age,i) AS allocation_rank
            FROM cells JOIN locality USING(municipality), LATERAL range(n) t(i)""",
            [person_offset],
        )
        progress("famiglie e posti disponibili nello stesso comune")
        con.execute(
            """CREATE TABLE families AS SELECT
            ? + row_number() OVER (ORDER BY municipality,size,i) AS household_id,
            municipality,size,
            row_number() OVER (PARTITION BY municipality
                ORDER BY hash(seed,size,i),size,i) AS allocation_rank
            FROM sizes JOIN locality USING(municipality), LATERAL range(n) t(i)""",
            [household_offset],
        )
        # Municipality-local ordinals keep slot randomness independent of batching.
        con.execute("""CREATE TABLE slots AS SELECT municipality,household_id,
            row_number() OVER (PARTITION BY municipality
                ORDER BY hash(seed,local_id,i),local_id,i) AS allocation_rank
            FROM (SELECT *,row_number() OVER (PARTITION BY municipality
                ORDER BY household_id) local_id FROM families)
            JOIN locality USING(municipality), LATERAL range(size-1) t(i)""")
        progress("assegnazione vincolata e scrittura Parquet persone")
        con.execute(
            f"""COPY (
            SELECT p.person_id,
                CASE WHEN p.age>=18 AND p.allocation_rank<=l.households
                    THEN h.household_id ELSE s.household_id END AS household_id,
                p.municipality,l.province,l.region,
                CASE WHEN p.age<100 THEN {cohort}-p.age END::SMALLINT AS birth_year,
                CASE WHEN p.age=100 THEN {cohort}-p.age END::SMALLINT AS birth_year_upper_bound,
                p.sex,(p.age>=18 AND p.allocation_rank<=l.households) AS reference_adult,
                'synthetic'::VARCHAR AS data_kind
            FROM people p JOIN locality l USING(municipality)
            LEFT JOIN families h ON p.municipality=h.municipality
                AND h.allocation_rank=CASE WHEN p.age>=18 THEN p.allocation_rank END
            LEFT JOIN slots s ON p.municipality=s.municipality
                AND s.allocation_rank=CASE WHEN p.age<18 THEN p.allocation_rank
                    WHEN p.allocation_rank>l.households
                    THEN l.minors+p.allocation_rank-l.households END
            ORDER BY p.person_id
            ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)""",
            [str(directory / "persons.parquet")],
        )
        con.execute(
            """COPY (
            SELECT household_id,municipality,province,region,size,
                'synthetic'::VARCHAR AS data_kind
            FROM families JOIN locality USING(municipality) ORDER BY household_id
            ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)""",
            [str(directory / "households.parquet")],
        )
        progress("Parquet del batch scritti")
