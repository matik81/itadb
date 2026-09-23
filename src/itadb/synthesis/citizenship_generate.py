"""Deterministic enrichment of immutable M4 persons from admitted STR/RCS margins."""

import csv
import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path

import duckdb

from itadb.synthesis.citizenship_models import CitizenshipMunicipality
from itadb.synthesis.national_generate import configure
from itadb.synthesis.national_models import ResourceBudget

ALGORITHM_VERSION = "citizenship-allocation/1.0.0"


def citizenship_seed(code: str) -> int:
    return int.from_bytes(hashlib.sha256(f"itadb:citizenship:1:1701:{code}".encode()).digest()[:8])


def enrich_batch(
    base: Path,
    output: Path,
    municipalities: list[CitizenshipMunicipality],
    year: int,
    budget: ResourceBudget,
    progress: Callable[[str], None],
) -> None:
    output.mkdir(parents=True, exist_ok=False)
    with duckdb.connect() as con:
        configure(con, budget, output / "scratch")
        con.read_parquet(str(base / "persons.parquet")).create_view("base_persons")
        cells = output / "cells.csv"
        with cells.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(
                (m.code, sex, age, n, citizenship_seed(m.code))
                for m in municipalities
                for sex, counts in [("M", m.foreign_male), ("F", m.foreign_female)]
                for age, n in enumerate(counts)
                if n
            )
        con.execute(
            "CREATE TABLE cells(municipality VARCHAR,sex VARCHAR,age INT,n BIGINT,seed UBIGINT)"
        )
        if cells.stat().st_size:
            con.execute("COPY cells FROM ? (HEADER false)", [str(cells)])
        cells.unlink()
        countries = output / "countries.csv"
        with countries.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(
                (m.code, sex, code, n, citizenship_seed(m.code))
                for m in municipalities
                for code, counts in sorted(m.countries.items())
                if code != "100"
                for sex, n in zip(["M", "F"], counts, strict=True)
                if n
            )
        con.execute(
            "CREATE TABLE countries(municipality VARCHAR,sex VARCHAR,"
            "code VARCHAR,n BIGINT,seed UBIGINT)"
        )
        if countries.stat().st_size:
            con.execute("COPY countries FROM ? (HEADER false)", [str(countries)])
        countries.unlink()
        progress("selezione stranieri per comune, sesso ed età")
        con.execute(
            """CREATE TABLE selected AS SELECT person_id,municipality,sex,seed FROM (
                SELECT b.person_id,c.*,row_number() OVER (
                    PARTITION BY c.municipality,c.sex,c.age
                    ORDER BY hash(c.seed,'selection/1',b.person_id),b.person_id) AS rank
                FROM base_persons b JOIN cells c ON b.municipality=c.municipality
                    AND b.sex=c.sex AND coalesce(?-b.birth_year-1,100)=c.age
            ) WHERE rank<=n""",
            [year],
        )
        progress("assegnazione delle singole cittadinanze entro comune e sesso")
        con.execute("""CREATE TABLE slots AS SELECT municipality,sex,code,
            row_number() OVER (PARTITION BY municipality,sex
                ORDER BY hash(seed,'countries/1',code,i),code,i) AS rank
            FROM countries,LATERAL range(n) t(i)""")
        con.execute("""CREATE TABLE assigned AS SELECT person_id,code FROM (
            SELECT person_id,municipality,sex,row_number() OVER (
                PARTITION BY municipality,sex
                ORDER BY hash(seed,'assignment/1',person_id),person_id) AS rank
            FROM selected) JOIN slots USING(municipality,sex,rank)""")
        progress("scrittura persone con cittadinanza; copia famiglie immutate")
        con.execute(
            """COPY (SELECT b.*,coalesce(a.code,'100')::VARCHAR AS citizenship_code
            FROM base_persons b LEFT JOIN assigned a USING(person_id) ORDER BY b.person_id)
            TO ? (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 122880)""",
            [str(output / "persons.parquet")],
        )
    shutil.copyfile(base / "households.parquet", output / "households.parquet")
