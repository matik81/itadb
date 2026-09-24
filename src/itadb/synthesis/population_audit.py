"""Independent read-back of demographics, citizenship and the final household stage."""

from collections import Counter
from pathlib import Path
from typing import Any

import duckdb

from itadb.pipeline.validate import QualityError
from itadb.synthesis.citizenship_models import CitizenshipMunicipality
from itadb.synthesis.national_audit import audit_batch
from itadb.synthesis.national_models import Municipality, ResourceBudget

AUDIT_VERSION = "ordered-population-independent-audit/1.0.0"
INDIVIDUAL_COLUMNS = [
    "person_id",
    "municipality",
    "province",
    "region",
    "birth_year",
    "birth_year_upper_bound",
    "sex",
    "data_kind",
    "citizenship_code",
]


def audit_population_batch(
    directory: Path,
    municipalities: list[Municipality],
    citizenships: list[CitizenshipMunicipality],
    reference: str,
    person_offset: int,
    household_offset: int,
    budget: ResourceBudget,
) -> dict[str, Any]:
    demographic = audit_batch(
        directory,
        municipalities,
        reference,
        person_offset,
        household_offset,
        budget,
        with_citizenship=True,
    )
    checks: dict[str, bool] = {}

    def gate(name: str, passed: bool) -> None:
        checks[name] = passed
        if not passed:
            raise QualityError({"checks": checks, "published": False})

    expected_countries = {
        (m.code, sex, code): n
        for m in citizenships
        for code, counts in m.countries.items()
        for sex, n in zip(["M", "F"], counts, strict=True)
        if n
    }
    expected_age = {
        (m.code, sex, age): n
        for m in citizenships
        for sex, counts in [("M", m.foreign_male), ("F", m.foreign_female)]
        for age, n in enumerate(counts)
        if n
    }
    with duckdb.connect() as con:
        con.execute(f"SET memory_limit='{budget.memory_mb}MB'")
        con.execute(f"SET threads={budget.threads}")
        con.execute("SET max_temp_directory_size='0B'")
        con.read_parquet(str(directory / "individuals.parquet")).create_view("individuals")
        con.read_parquet(str(directory / "persons.parquet")).create_view("p")
        final_schema = [(r[0], r[1]) for r in con.execute("DESCRIBE p").fetchall()]
        expected_schema = [(n, t) for n, t in final_schema if n in INDIVIDUAL_COLUMNS]
        gate(
            "pre_household_schema",
            [(r[0], r[1]) for r in con.execute("DESCRIBE individuals").fetchall()]
            == expected_schema,
        )
        n, unique = con.execute(
            "SELECT count(*),count(DISTINCT person_id) FROM individuals"
        ).fetchall()[0]
        gate("pre_household_identity", n == unique == demographic["persons"])
        changed = " OR ".join(f"p.{c} IS DISTINCT FROM i.{c}" for c in INDIVIDUAL_COLUMNS[1:])
        gate(
            "first_three_stages_unchanged",
            con.execute(
                "SELECT count(*) FROM p FULL OUTER JOIN individuals i USING(person_id) "
                f"WHERE p.person_id IS NULL OR i.person_id IS NULL OR {changed}"
            ).fetchall()[0][0]
            == 0,
        )
        # Both sides are checked, so exact final margins cannot hide stage-4 mutations.
        for table in ["individuals", "p"]:
            countries = {
                (m, s, c): n
                for m, s, c, n in con.execute(
                    f"SELECT municipality,sex,citizenship_code,count(*) FROM {table} GROUP BY ALL"
                ).fetchall()
            }
            gate(f"{table}_rcs", countries == expected_countries)
            ages = {
                (m, s, a): n
                for m, s, a, n in con.execute(
                    "SELECT municipality,sex,coalesce(?-birth_year-1,100),count(*) "
                    f"FROM {table} WHERE citizenship_code<>'100' GROUP BY ALL",
                    [int(reference[:4])],
                ).fetchall()
            }
            gate(f"{table}_str", ages == expected_age)
        rare = con.execute("""SELECT count(*),coalesce(sum(n),0) FROM (
            SELECT count(*) n FROM p GROUP BY municipality,sex,birth_year,
            birth_year_upper_bound,citizenship_code HAVING count(*)<5)""").fetchall()[0]
    totals: Counter[str] = Counter()
    for (_, _, code), n in countries.items():
        totals[code] += n
    return {
        "audit_version": AUDIT_VERSION,
        "demography": demographic,
        "checks": checks,
        "country_totals": dict(sorted(totals.items())),
        "str_cells_checked": len(citizenships) * 202,
        "rcs_nonzero_cells_checked": len(expected_countries),
        "disclosure": {"cells_below_5": rare[0], "persons_in_cells_below_5": rare[1]},
    }
