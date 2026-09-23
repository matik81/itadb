"""Exact demographic reconstruction and constrained random household allocation.

This is a deliberately limited baseline, not an implementation of a published IPU model.
All persons and household membership are virtual; no donor microdata are accepted.
"""

import csv
import random
from pathlib import Path

import duckdb

from itadb.synthesis.models import Calibration

ALGORITHM_VERSION = "constrained-reconstruction/2.0.0"


def check_feasibility(c: Calibration, large_size: int) -> None:
    if large_size not in {6, 7, 8}:
        raise ValueError("Unreviewed 6+ size assumption")
    sizes = [1, 2, 3, 4, 5, large_size]
    capacity = sum(n * size for n, size in zip(c.household_counts, sizes, strict=True))
    adults = sum(c.age_counts[18:])
    minors = sum(c.age_counts[:18])
    households = sum(c.household_counts)
    if capacity > sum(c.age_counts):
        raise ValueError("Household capacity exceeds residents; no silent margin adjustment")
    if adults < households or minors > capacity - households:
        raise ValueError("Infeasible adult-per-household or minor allocation constraints")


def generate(c: Calibration, seed: int, large_size: int, directory: Path) -> None:
    check_feasibility(c, large_size)
    directory.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed)
    male_counts = c.male_by_age
    adults: list[tuple[int, str]] = []
    minors: list[tuple[int, str]] = []
    for age, total in enumerate(c.age_counts):
        pool = minors if age < 18 else adults
        pool.extend((age, "M") for _ in range(male_counts[age]))
        pool.extend((age, "F") for _ in range(total - male_counts[age]))
    rng.shuffle(adults)
    rng.shuffle(minors)
    sizes = [
        size
        for size, count in zip([1, 2, 3, 4, 5, large_size], c.household_counts, strict=True)
        for _ in range(count)
    ]
    rng.shuffle(sizes)
    # Reserve one adult per household. Remaining slots accept all minors first;
    # the explicit unassigned residual therefore contains adults only (an assumption).
    slots = [household for household, size in enumerate(sizes, 1) for _ in range(size - 1)]
    rng.shuffle(slots)
    people_csv = directory / "persons.csv"
    households_csv = directory / "households.csv"
    with people_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["person_id", "household_id", "age", "sex", "reference_adult"])
        person_id = 0
        for household in range(1, len(sizes) + 1):
            age, sex = adults.pop()
            person_id += 1
            writer.writerow([person_id, household, age, sex, True])
        for age, sex in minors:
            person_id += 1
            writer.writerow([person_id, slots.pop(), age, sex, False])
        for age, sex in adults:
            person_id += 1
            writer.writerow([person_id, slots.pop() if slots else None, age, sex, False])
    with households_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["household_id", "size"])
        writer.writerows(enumerate(sizes, 1))
    with duckdb.connect() as con:
        con.execute("SET memory_limit='256MB'")
        con.execute("SET threads=1")
        con.execute(
            """CREATE TABLE p AS SELECT *, 'synthetic'::VARCHAR AS data_kind
            FROM read_csv(?, header=true, columns={'person_id':'BIGINT',
            'household_id':'BIGINT','age':'SMALLINT','sex':'VARCHAR',
            'reference_adult':'BOOLEAN'})""",
            [str(people_csv)],
        )
        con.execute(
            """CREATE TABLE h AS SELECT *, 'synthetic'::VARCHAR AS data_kind
            FROM read_csv(?, header=true, columns={'household_id':'BIGINT','size':'SMALLINT'})""",
            [str(households_csv)],
        )
        con.execute(
            "COPY (SELECT * FROM p ORDER BY person_id) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(directory / "persons.parquet")],
        )
        con.execute(
            "COPY (SELECT * FROM h ORDER BY household_id) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(directory / "households.parquet")],
        )
    # These are disposable intermediates created in this attempt, never archived evidence.
    people_csv.unlink()
    households_csv.unlink()
