"""Independent read-back audit: SQL over exported Parquet, no generator imports."""

from pathlib import Path
from typing import Any

import duckdb

from itadb.pipeline.validate import QualityError
from itadb.synthesis.models import PilotInput

AUDIT_VERSION = "parquet-independent-audit/2.0.0"


def audit(directory: Path, inputs: PilotInput, large_size: int) -> dict[str, Any]:
    c = inputs.calibration
    checks: dict[str, bool] = {}

    def gate(name: str, passed: bool) -> None:
        checks[name] = passed
        if not passed:
            raise QualityError({"checks": checks, "published": False})

    with duckdb.connect() as con:
        con.execute("SET memory_limit='256MB'")
        con.execute("SET threads=1")
        con.read_parquet(str(directory / "persons.parquet")).create_view("persons")
        con.read_parquet(str(directory / "households.parquet")).create_view("households")
        for table, expected in [
            (
                "persons",
                [
                    ("person_id", "BIGINT"),
                    ("household_id", "BIGINT"),
                    ("age", "SMALLINT"),
                    ("sex", "VARCHAR"),
                    ("reference_adult", "BOOLEAN"),
                    ("data_kind", "VARCHAR"),
                ],
            ),
            (
                "households",
                [("household_id", "BIGINT"), ("size", "SMALLINT"), ("data_kind", "VARCHAR")],
            ),
        ]:
            gate(
                f"{table}_schema",
                [(row[0], row[1]) for row in con.execute(f"DESCRIBE {table}").fetchall()]
                == expected,
            )
        n, ids, lowest, highest = con.execute(
            "SELECT count(*),count(DISTINCT person_id),min(person_id),max(person_id) FROM persons"
        ).fetchall()[0]
        gate(
            "person_identity_and_total",
            n == ids == sum(c.age_counts) and lowest == 1 and highest == n,
        )
        h, ids, lowest, highest = con.execute(
            "SELECT count(*),count(DISTINCT household_id),min(household_id),"
            "max(household_id) FROM households"
        ).fetchall()[0]
        gate(
            "household_identity_and_total",
            h == ids == sum(c.household_counts) and lowest == 1 and highest == h,
        )
        invalid = con.execute("""SELECT count(*) FROM persons
            WHERE age IS NULL OR age NOT BETWEEN 0 AND 100
            OR sex IS NULL OR sex NOT IN ('M','F') OR reference_adult IS NULL
            OR data_kind IS DISTINCT FROM 'synthetic'
            OR (reference_adult AND (age < 18 OR household_id IS NULL))
            OR (age < 18 AND household_id IS NULL)""").fetchall()[0][0]
        gate("person_domains_and_minor_assignment", invalid == 0)
        gate(
            "household_domains",
            con.execute("""SELECT count(*) FROM households
            WHERE size IS NULL OR size NOT BETWEEN 1 AND 8
            OR data_kind IS DISTINCT FROM 'synthetic'""").fetchall()[0][0]
            == 0,
        )
        gate(
            "foreign_keys",
            con.execute("""SELECT count(*) FROM persons p LEFT JOIN households h
            USING(household_id)
            WHERE p.household_id IS NOT NULL AND h.household_id IS NULL""").fetchall()[0][0]
            == 0,
        )
        gate(
            "family_constraints",
            con.execute("""SELECT count(*) FROM (
            SELECT h.household_id FROM households h LEFT JOIN persons p USING(household_id)
            GROUP BY h.household_id,h.size HAVING count(p.person_id) <> h.size
            OR count(*) FILTER (WHERE p.reference_adult) <> 1
            OR count(*) FILTER (WHERE p.age>=18) < 1)""").fetchall()[0][0]
            == 0,
        )
        actual_sizes = dict(
            con.execute("SELECT size,count(*) FROM households GROUP BY size").fetchall()
        )
        expected_sizes = {
            size: count
            for size, count in zip([1, 2, 3, 4, 5, large_size], c.household_counts, strict=True)
            if count
        }
        gate("household_size_margins", actual_sizes == expected_sizes)
        counts = dict(con.execute("SELECT age,count(*) FROM persons GROUP BY age").fetchall())
        gate("age_margins", [counts.get(age, 0) for age in range(101)] == c.age_counts)
        residual = con.execute(
            "SELECT count(*) FROM persons WHERE household_id IS NULL"
        ).fetchall()[0][0]
        gate(
            "explicit_residual",
            residual == n - sum(size * count for size, count in expected_sizes.items()),
        )
        males = dict(
            con.execute("SELECT age,count(*) FROM persons WHERE sex='M' GROUP BY age").fetchall()
        )
        cell_errors = [
            abs(males.get(age, 0) - reference) for age, reference in enumerate(c.male_by_age)
        ]
        # Female errors have equal magnitude and opposite sign because age totals are fixed.
        cells = [
            {
                "sex": sex,
                "age": age,
                "reference": observed,
                "synthetic": synthetic,
                "error": synthetic - observed,
            }
            for age, reference in enumerate(c.male_by_age)
            for sex, observed, synthetic in [
                ("M", reference, males.get(age, 0)),
                ("F", c.age_counts[age] - reference, counts.get(age, 0) - males.get(age, 0)),
            ]
        ]
        gate("sex_age_joint_counts", all(cell["error"] == 0 for cell in cells))
        family = con.execute("""SELECT
            count(*) FILTER (WHERE youngest<18),
            count(*) FILTER (WHERE youngest>=65),
            count(*) FILTER (WHERE youngest<18 AND oldest>=65),
            count(*) FILTER (WHERE members=1 AND oldest>=65)
            FROM (SELECT household_id,min(age) youngest,max(age) oldest,count(*) members
            FROM persons WHERE household_id IS NOT NULL GROUP BY household_id)""").fetchall()[0]
    return {
        "audit_version": AUDIT_VERSION,
        "checks": checks,
        "persons": n,
        "households": h,
        "unassigned_adults": residual,
        "calibration_max_absolute_error": max(cell_errors),
        "calibration_joint": {
            "reference_evidence_kind": inputs.evidence_kind,
            "description": "Tabella sesso per singola età: 202 vincoli esatti di calibrazione",
            "total_variation_distance": sum(cell_errors) / n,
            "mean_absolute_cell_error": sum(cell_errors) / 101,
            "max_absolute_cell_error": max(cell_errors),
            "cells": cells,
        },
        "model_statistics": dict(
            zip(
                [
                    "households_with_minors",
                    "households_only_65_plus",
                    "households_minors_and_65_plus",
                    "single_65_plus",
                ],
                family,
                strict=True,
            )
        ),
        "statistical_acceptance": "experimental_not_certified",
    }
