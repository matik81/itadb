import pytest

from itadb.synthesis.demography import AnnualAge, age_at_year_start, cohort_reference_year


@pytest.mark.parametrize(
    "year,birth_year,upper_bound",
    [
        (2022, None, None),
        (2022, 1991, 1921),
        (2022, 2022, None),
        (2022, 2023, None),
        (2022, None, 2022),
        (2022, 0, None),
        (2022, None, -1),
        (2022, True, None),
        (2022, 1991.0, None),
        (2022, None, 1921.0),
        (True, 1991, None),
        (2022.0, 1991, None),
        (0, 1991, None),
        (10000, 1991, None),
    ],
)
def test_invalid_annual_age_inputs_are_rejected(
    year: int, birth_year: int | None, upper_bound: int | None
) -> None:
    with pytest.raises(ValueError):
        age_at_year_start(year, birth_year=birth_year, birth_year_upper_bound=upper_bound)


def test_birth_years_are_not_limited_to_pilot_cohorts() -> None:
    assert age_at_year_start(2031, birth_year=2030) == AnnualAge(0, False)
    assert age_at_year_start(2032, birth_year=2030) == AnnualAge(1, False)
    assert cohort_reference_year("2031-01-01") == 2030


@pytest.mark.parametrize("reference", ["2022-07-01", "2022-01-02", "0101-01-01"])
def test_non_annual_calibration_requires_another_policy(reference: str) -> None:
    with pytest.raises(ValueError, match="January 1"):
        cohort_reference_year(reference)
