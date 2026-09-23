"""Independent SQL read-back; no import of the citizenship generator."""

from collections import Counter
from pathlib import Path
from typing import Any

import duckdb

from itadb.pipeline.storage import sha256_file
from itadb.pipeline.validate import QualityError
from itadb.synthesis.citizenship_models import CitizenshipMunicipality
from itadb.synthesis.national_models import ResourceBudget

AUDIT_VERSION = "citizenship-independent-audit/1.0.0"
BASE_COLUMNS = [
    "person_id",
    "household_id",
    "municipality",
    "province",
    "region",
    "birth_year",
    "birth_year_upper_bound",
    "sex",
    "reference_adult",
    "data_kind",
]


def audit_citizenship_batch(
    directory: Path,
    base: Path,
    municipalities: list[CitizenshipMunicipality],
    year: int,
    budget: ResourceBudget,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    def gate(name: str, passed: bool) -> None:
        checks[name] = passed
        if not passed:
            raise QualityError({"checks": checks, "published": False})

    gate(
        "household_file_unchanged",
        sha256_file(directory / "households.parquet") == sha256_file(base / "households.parquet"),
    )
    expected_age = Counter(
        {
            (m.code, sex, age): n
            for m in municipalities
            for sex, counts in [("M", m.foreign_male), ("F", m.foreign_female)]
            for age, n in enumerate(counts)
            if n
        }
    )
    expected_countries = Counter(
        {
            (m.code, sex, code): n
            for m in municipalities
            for code, values in m.countries.items()
            for sex, n in zip(["M", "F"], values, strict=True)
            if n
        }
    )
    with duckdb.connect() as con:
        con.execute(f"SET memory_limit='{budget.memory_mb}MB'")
        con.execute(f"SET threads={budget.threads}")
        con.execute("SET max_temp_directory_size='0B'")
        con.read_parquet(str(directory / "persons.parquet")).create_view("p")
        con.read_parquet(str(base / "persons.parquet")).create_view("b")
        source_schema = [(r[0], r[1]) for r in con.execute("DESCRIBE b").fetchall()]
        gate("base_columns", [n for n, _ in source_schema] == BASE_COLUMNS)
        gate(
            "citizenship_schema",
            [(r[0], r[1]) for r in con.execute("DESCRIBE p").fetchall()]
            == source_schema + [("citizenship_code", "VARCHAR")],
        )
        n, unique = con.execute("SELECT count(*),count(DISTINCT person_id) FROM p").fetchall()[0]
        gate("identity", n == unique == sum(expected_countries.values()))
        changed = " OR ".join(f"p.{c} IS DISTINCT FROM b.{c}" for c in BASE_COLUMNS[1:])
        gate(
            "all_base_attributes_unchanged",
            con.execute(
                f"SELECT count(*) FROM p FULL OUTER JOIN b USING(person_id) "
                f"WHERE p.person_id IS NULL OR b.person_id IS NULL OR {changed}"
            ).fetchall()[0][0]
            == 0,
        )
        gate(
            "citizenship_present",
            con.execute("SELECT count(*) FROM p WHERE citizenship_code IS NULL").fetchall()[0][0]
            == 0,
        )
        countries = Counter(
            {
                (m, s, c): n
                for m, s, c, n in con.execute(
                    "SELECT municipality,sex,citizenship_code,count(*) FROM p GROUP BY ALL"
                ).fetchall()
            }
        )
        gate("rcs_municipality_sex_country", countries == expected_countries)
        ages = Counter(
            {
                (m, s, a): n
                for m, s, a, n in con.execute(
                    "SELECT municipality,sex,coalesce(?-birth_year-1,100),count(*) "
                    "FROM p WHERE citizenship_code<>'100' GROUP BY ALL",
                    [year],
                ).fetchall()
            }
        )
        gate("str_municipality_sex_age", ages == expected_age)
        cells, persons = con.execute("""SELECT count(*),coalesce(sum(n),0) FROM (
            SELECT count(*) n FROM p
            GROUP BY municipality,sex,birth_year,birth_year_upper_bound,citizenship_code
            HAVING count(*)<5)""").fetchall()[0]
        totals: Counter[str] = Counter()
        for (_, _, code), count in countries.items():
            totals[code] += count
    return {
        "checks": checks,
        "persons": n,
        "foreign_persons": sum(expected_age.values()),
        "italian_persons": totals["100"],
        "stateless_persons": totals["999"],
        "str_cells_checked": len(municipalities) * 202,
        "rcs_nonzero_cells_checked": len(expected_countries),
        "country_totals": dict(sorted(totals.items())),
        "disclosure": {"cells_below_5": cells, "persons_in_cells_below_5": persons},
    }
