"""Stable synthetic birth cohorts and ages at annual simulation boundaries."""

from dataclasses import dataclass
from datetime import date

PERSONS_SCHEMA_VERSION = "m3-persons/3"
BIRTH_YEAR_POLICY_VERSION = "year-start-cohort/1"


def cohort_reference_year(population_reference: str) -> int:
    """The last completed birth year at a January 1 boundary, before birthdays."""
    reference = date.fromisoformat(population_reference)
    if (reference.month, reference.day) != (1, 1) or reference.year <= 101:
        raise ValueError("Birth cohorts require a January 1 reference after year 101")
    return reference.year - 1


def person_model_metadata(population_reference: str) -> dict[str, str | int]:
    return {
        "schema_version": PERSONS_SCHEMA_VERSION,
        "birth_year_policy": BIRTH_YEAR_POLICY_VERSION,
        "population_reference": population_reference,
        "time_step": "annual",
        "age_reference": "january_1_before_birthdays",
        "age_formula": "year - birth_year - 1",
        "birth_year_kind": "synthetic",
        "open_age_class": 100,
        "open_birth_year_upper_bound": cohort_reference_year(population_reference) - 100,
        "rationale": (
            "Coorte stabile per passi annuali, senza inventare compleanni; "
            "100+ conserva solo un limite superiore all'anno di nascita"
        ),
    }


@dataclass(frozen=True, slots=True)
class AnnualAge:
    """Years at the start of a year; a lower bound is never an exact age."""

    years: int
    is_lower_bound: bool


def age_at_year_start(
    year: int, *, birth_year: int | None, birth_year_upper_bound: int | None = None
) -> AnnualAge:
    """Derive age before the year's birthdays without modifying the birth cohort.

    Exactly one birth field must be supplied. An open cohort advances as a lower
    bound (100+ becomes 101+), while exact ages may advance beyond 99. This does
    not model survival, birthdays within the year, or household evolution.
    """
    if (birth_year is None) == (birth_year_upper_bound is None):
        raise ValueError("Supply exactly one birth year or upper bound")
    cohort = birth_year if birth_year is not None else birth_year_upper_bound
    if type(year) is not int or not 1 <= year <= 9999:
        raise ValueError("Simulation year must be an integer from 1 to 9999")
    if type(cohort) is not int or not 1 <= cohort < year:
        raise ValueError("Birth year or upper bound must be a positive integer before the year")
    return AnnualAge(years=year - cohort - 1, is_lower_bound=birth_year is None)
