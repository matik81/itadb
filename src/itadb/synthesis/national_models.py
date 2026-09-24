"""Versioned constraints for national territorial reconstruction."""

import hashlib
from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import Field, model_validator

from itadb.synthesis.models import StrictModel

Count = Annotated[int, Field(strict=True, ge=0, le=70_000_000)]
Code = Annotated[str, Field(pattern=r"^[0-9]{6}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Municipality(StrictModel):
    code: Code
    province: Annotated[str, Field(pattern=r"^[0-9]{3}$")]
    region: Annotated[str, Field(pattern=r"^[0-9]{2}$")]
    male: list[Count] = Field(min_length=101, max_length=101)
    female: list[Count] = Field(min_length=101, max_length=101)
    households: list[Count] = Field(min_length=6, max_length=6)

    @property
    def population(self) -> int:
        return sum(self.male) + sum(self.female)

    @property
    def household_total(self) -> int:
        return sum(self.households)

    @property
    def capacity(self) -> int:
        return sum(size * count for size, count in enumerate(self.households, 1))

    def check_feasibility(self) -> None:
        minors = sum(self.male[:18]) + sum(self.female[:18])
        if self.capacity > self.population:
            raise ValueError(f"{self.code}: household capacity exceeds residents")
        if self.population - minors < self.household_total:
            raise ValueError(f"{self.code}: too few adults for household reference persons")
        if minors > self.capacity - self.household_total:
            raise ValueError(f"{self.code}: too few household slots for minors")


class NationalInput(StrictModel):
    schema_version: Literal["m4-input/1"] = "m4-input/1"
    evidence_kind: Literal["official_aggregates", "invented_load_fixture"]
    population_reference: str
    household_reference: str
    geography_reference: str
    municipalities: list[Municipality] = Field(min_length=1, max_length=10_000)
    source_hashes: dict[str, Digest] = Field(min_length=1)
    attribution: str = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self) -> "NationalInput":
        reference = date.fromisoformat(self.population_reference)
        if (reference.month, reference.day) != (1, 1) or reference.year < 1901:
            raise ValueError("Population requires a January 1 reference after 1900")
        if date.fromisoformat(self.household_reference) != reference - timedelta(days=1):
            raise ValueError("Household reference must be the preceding December 31")
        if self.geography_reference != self.population_reference:
            raise ValueError("Geography and population snapshots must coincide")
        codes = [m.code for m in self.municipalities]
        if len(codes) != len(set(codes)):
            raise ValueError("Duplicate municipality")
        parents: dict[str, str] = {}
        for municipality in self.municipalities:
            fixture = int(municipality.region) >= 90 and int(municipality.province) >= 900
            if (self.evidence_kind == "invented_load_fixture") != fixture:
                raise ValueError("Invented fixtures require a separate geographic namespace")
            if (
                self.evidence_kind == "official_aggregates"
                and not 1 <= int(municipality.region) <= 20
            ):
                raise ValueError("Invalid official region")
            if (
                parents.setdefault(municipality.province, municipality.region)
                != municipality.region
            ):
                raise ValueError("Province belongs to multiple regions")
        if not 0 < sum(m.population for m in self.municipalities) <= 70_000_000:
            raise ValueError("Population outside national run budget")
        return self


class NationalReference(StrictModel):
    schema_version: Literal["m4-reference/1"] = "m4-reference/1"
    seed: Literal[1701] = 1701
    large_household_size: Literal[6] = 6
    priorities: list[str] = Field(default_factory=lambda: ["sex_age", "geography", "households"])
    distribution: Literal["local_microdata_aggregate_package", "local_only"] = (
        "local_microdata_aggregate_package"
    )

    @model_validator(mode="after")
    def fixed_priorities(self) -> "NationalReference":
        if self.priorities != ["sex_age", "geography", "households"]:
            raise ValueError("Changing model priorities requires an explicit new version")
        return self


class ResourceBudget(StrictModel):
    memory_mb: Annotated[int, Field(ge=128, le=2048)] = 2048
    threads: Literal[1, 2] = 2
    max_rss_mb: Annotated[int, Field(ge=256, le=8192)] = 8192
    max_disk_mb: Annotated[int, Field(ge=1, le=40960)] = 40960
    max_seconds: Annotated[int, Field(ge=1, le=7200)] = 7200
    max_batch_population: Annotated[int, Field(ge=1, le=5_000_000)] = 5_000_000


def territorial_seed(code: str, seed: int = 1701) -> int:
    """SHA-256 namespace v1; independent of batch ordering and Python hash salt."""
    payload = f"itadb:m4:territorial-seed:1:{seed}:{code}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def batches(inputs: NationalInput, budget: ResourceBudget) -> list[list[Municipality]]:
    """Pack sorted municipalities within provinces; never split a household locality."""
    result: list[list[Municipality]] = []
    current: list[Municipality] = []
    population = 0
    for municipality in sorted(inputs.municipalities, key=lambda m: (m.province, m.code)):
        municipality.check_feasibility()
        if municipality.population > budget.max_batch_population:
            raise ValueError("One municipality exceeds the measured batch budget")
        if current and (
            current[0].province != municipality.province
            or population + municipality.population > budget.max_batch_population
        ):
            result.append(current)
            current, population = [], 0
        current.append(municipality)
        population += municipality.population
    if current:
        result.append(current)
    return result
