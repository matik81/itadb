"""Public population contract, separate from observed aggregate APIs."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel


class PopulationSnapshot(BaseModel):
    id: int
    run_id: str
    manifest_sha256: str
    reference_date: date
    household_reference: date
    persons: int
    households: int
    municipalities: int
    located_persons: int
    is_fixture: bool
    data_kind: Literal["synthetic"]
    published_at: datetime


class PopulationEvidence(PopulationSnapshot):
    report: dict[str, Any]
    provenance: dict[str, Any]
    publication_checks: dict[str, Any]


class PopulationMunicipality(BaseModel):
    code: str
    name: str
    province_code: str
    province_name: str
    region_code: str
    region_name: str
    persons: int
    households: int
    longitude: float | None
    latitude: float | None
    location_kind: Literal["municipality_representative_point"] = (
        "municipality_representative_point"
    )


class PopulationMunicipalityPage(BaseModel):
    items: list[PopulationMunicipality]
    next_cursor: int | None


class PopulationRegion(BaseModel):
    code: str
    name: str
    persons: int
    households: int
    geometry: dict[str, Any] | None


class PopulationBoundary(BaseModel):
    code: str
    geometry: dict[str, Any]


class PopulationMap(BaseModel):
    regions: list[PopulationRegion]
    municipalities: list[PopulationMunicipality]
    provinces: list[PopulationBoundary]
    municipality_boundaries: list[PopulationBoundary]
    representation: Literal["municipality_aggregates"] = "municipality_aggregates"
    individual_coordinates_available: Literal[False] = False


class SyntheticPerson(BaseModel):
    person_id: int
    household_id: int | None
    municipality_code: str
    sex: Literal["M", "F"]
    birth_year: int | None
    birth_year_upper_bound: int | None
    age: int
    age_is_lower_bound: bool
    citizenship_code: str
    reference_adult: bool
    data_kind: Literal["synthetic"]


class SyntheticPersonPage(BaseModel):
    items: list[SyntheticPerson]
    next_cursor: int | None


class SyntheticHousehold(BaseModel):
    household_id: int
    municipality_code: str
    size: int
    data_kind: Literal["synthetic"]


class SyntheticHouseholdPage(BaseModel):
    items: list[SyntheticHousehold]
    next_cursor: int | None


class SyntheticHouseholdDetail(SyntheticHousehold):
    members: list[SyntheticPerson]


class PopulationDistribution(BaseModel):
    age: int
    sex: Literal["M", "F"]
    persons: int


class PopulationValidation(BaseModel):
    kind: Literal["sex_age", "foreign_age", "citizenship", "household_size"]
    cells: int
    expected: int
    actual: int
    mismatched_cells: int
    max_absolute_error: int


class PopulationComparison(BaseModel):
    kind: str
    sex: str
    category: int
    expected: int
    actual: int
