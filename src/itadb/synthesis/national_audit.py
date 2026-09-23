"""Independent SQL read-back of bounded national partitions, without generator imports."""

from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from itadb.pipeline.validate import QualityError
from itadb.synthesis.national_models import Municipality, ResourceBudget

AUDIT_VERSION = "territorial-independent-audit/1.0.0"


def audit_batch(
    directory: Path,
    municipalities: list[Municipality],
    population_reference: str,
    person_offset: int,
    household_offset: int,
    budget: ResourceBudget,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    def gate(name: str, passed: bool) -> None:
        checks[name] = passed
        if not passed:
            raise QualityError({"checks": checks, "published": False})

    cohort = date.fromisoformat(population_reference).year - 1
    with duckdb.connect() as con:
        con.execute(f"SET memory_limit='{budget.memory_mb}MB'")
        con.execute(f"SET threads={budget.threads}")
        con.execute(f"SET max_temp_directory_size='{budget.max_disk_mb}MB'")
        con.read_parquet(str(directory / "persons.parquet")).create_view("p")
        con.read_parquet(str(directory / "households.parquet")).create_view("h")
        geography = [("municipality", "VARCHAR"), ("province", "VARCHAR"), ("region", "VARCHAR")]
        for table, schema in [
            (
                "p",
                [
                    ("person_id", "BIGINT"),
                    ("household_id", "BIGINT"),
                    *geography,
                    ("birth_year", "SMALLINT"),
                    ("birth_year_upper_bound", "SMALLINT"),
                    ("sex", "VARCHAR"),
                    ("reference_adult", "BOOLEAN"),
                    ("data_kind", "VARCHAR"),
                ],
            ),
            (
                "h",
                [
                    ("household_id", "BIGINT"),
                    *geography,
                    ("size", "SMALLINT"),
                    ("data_kind", "VARCHAR"),
                ],
            ),
        ]:
            gate(
                f"{table}_schema",
                [(r[0], r[1]) for r in con.execute(f"DESCRIBE {table}").fetchall()] == schema,
            )
        for table, column, offset, total in [
            ("p", "person_id", person_offset, sum(m.population for m in municipalities)),
            ("h", "household_id", household_offset, sum(m.household_total for m in municipalities)),
        ]:
            n, distinct, lowest, highest = (
                con.execute(
                    f"SELECT count(*),count(DISTINCT {column}),"
                    f"min({column}),max({column}) FROM {table}"
                ).fetchone()
                or (None,) * 4
            )
            gate(
                f"{table}_identity",
                n == distinct == total
                and (
                    (lowest == offset + 1 and highest == offset + total)
                    if total
                    else lowest is None and highest is None
                ),
            )
        gate(
            "birth_domains",
            con.execute(
                """SELECT count(*) FROM p WHERE NOT coalesce(
            (birth_year BETWEEN ? AND ? AND birth_year_upper_bound IS NULL) OR
            (birth_year IS NULL AND birth_year_upper_bound=?),false)""",
                [cohort - 99, cohort, cohort - 100],
            ).fetchall()[0][0]
            == 0,
        )
        con.execute(
            f"CREATE TEMP VIEW persons AS SELECT *,{cohort}-"
            "coalesce(birth_year,birth_year_upper_bound) age FROM p",
        )
        gate(
            "person_domains",
            con.execute("""SELECT count(*) FROM persons WHERE
            sex IS NULL OR sex NOT IN ('M','F') OR reference_adult IS NULL
            OR data_kind IS DISTINCT FROM 'synthetic'
            OR (reference_adult AND (age<18 OR household_id IS NULL))
            OR (age<18 AND household_id IS NULL)""").fetchall()[0][0]
            == 0,
        )
        gate(
            "household_domains",
            con.execute("""SELECT count(*) FROM h WHERE size IS NULL
            OR size NOT BETWEEN 1 AND 6 OR data_kind IS DISTINCT FROM 'synthetic'""").fetchall()[0][
                0
            ]
            == 0,
        )
        gate(
            "family_integrity",
            con.execute("""SELECT count(*) FROM (
            SELECT h.household_id,h.size FROM h LEFT JOIN persons p USING(household_id)
            GROUP BY h.household_id,h.size,h.municipality,h.province,h.region
            HAVING count(p.person_id)<>h.size OR count(*) FILTER (WHERE p.reference_adult)<>1
            OR count(*) FILTER (WHERE p.age>=18)<1
            OR count(*) FILTER (WHERE p.municipality IS DISTINCT FROM h.municipality
                OR p.province IS DISTINCT FROM h.province OR p.region IS DISTINCT FROM h.region)>0
            )""").fetchall()[0][0]
            == 0,
        )
        gate(
            "foreign_keys",
            con.execute("""SELECT count(*) FROM p LEFT JOIN h USING(household_id)
            WHERE p.household_id IS NOT NULL AND h.household_id IS NULL""").fetchall()[0][0]
            == 0,
        )
        actual = {
            (code, sex, age): n
            for code, sex, age, n in con.execute(
                "SELECT municipality,sex,age,count(*) FROM persons GROUP BY ALL"
            ).fetchall()
        }
        expected = {
            (m.code, sex, age): n
            for m in municipalities
            for sex, counts in [("M", m.male), ("F", m.female)]
            for age, n in enumerate(counts)
            if n
        }
        gate("municipal_sex_age_joint", actual == expected)
        actual_h = {
            (code, size): n
            for code, size, n in con.execute(
                "SELECT municipality,size,count(*) FROM h GROUP BY ALL"
            ).fetchall()
        }
        gate(
            "municipal_household_sizes",
            actual_h
            == {
                (m.code, size): n
                for m in municipalities
                for size, n in enumerate(m.households, 1)
                if n
            },
        )
        expected_geo = {m.code: (m.province, m.region) for m in municipalities}
        for table in ["p", "h"]:
            rows = con.execute(
                f"SELECT DISTINCT municipality,province,region FROM {table}"
            ).fetchall()
            gate(f"{table}_geography", all(expected_geo.get(c) == (p, r) for c, p, r in rows))
        totals = con.execute("""SELECT municipality,count(*),
            count(*) FILTER (WHERE household_id IS NULL)
            FROM p GROUP BY municipality ORDER BY municipality""").fetchall()
        gate(
            "residual_by_municipality",
            {c: (n, r) for c, n, r in totals}
            == {
                m.code: (m.population, m.population - m.capacity)
                for m in municipalities
                if m.population
            },
        )
        region_cells = con.execute("""SELECT region,sex,age,count(*) FROM persons
            GROUP BY ALL ORDER BY region,sex,age""").fetchall()
        rare = con.execute("""SELECT count(*),coalesce(sum(n),0) FROM
            (SELECT count(*) n FROM persons
                GROUP BY municipality,sex,age HAVING n<5)""").fetchall()[0]
        family_stats = con.execute("""SELECT count(*) FILTER (WHERE youngest<18),
            count(*) FILTER (WHERE youngest>=65),count(*) FILTER (WHERE youngest<18 AND oldest>=65)
            FROM (SELECT household_id,min(age) youngest,max(age) oldest FROM persons
                WHERE household_id IS NOT NULL GROUP BY household_id)""").fetchall()[0]
    return {
        "audit_version": AUDIT_VERSION,
        "checks": checks,
        "persons": sum(m.population for m in municipalities),
        "households": sum(m.household_total for m in municipalities),
        "unassigned_adults": sum(m.population - m.capacity for m in municipalities),
        "calibration_cells": len(municipalities) * 202,
        "max_absolute_error": 0,
        "total_variation_distance": 0,
        "region_cells": region_cells,
        "municipal_totals": totals,
        "disclosure": {
            "quasi_identifiers": ["municipality", "sex", "age"],
            "cells_below_5": rare[0],
            "persons_in_cells_below_5": rare[1],
            "microdata_distribution": "blocked_pending_external_review",
        },
        "model_statistics": dict(
            zip(
                [
                    "households_with_minors",
                    "households_only_65_plus",
                    "households_minors_and_65_plus",
                ],
                family_stats,
                strict=True,
            )
        ),
        "out_of_calibration_validation": "not_available",
    }
