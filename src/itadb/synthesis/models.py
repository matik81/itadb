"""The generator receives calibration margins, never the held-out joint table."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Count = Annotated[int, Field(strict=True, ge=0, le=200_000)]
Seed = Annotated[int, Field(strict=True, ge=0, le=2**32 - 1)]
BANDS = ((0, 18), (18, 65), (65, 101))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Calibration(StrictModel):
    territory: Literal["ITC2", "DEMO_M3"]
    population_reference: Literal["2022-01-01"]
    household_reference: Literal["2021-12-31"]
    age_counts: list[Count] = Field(min_length=101, max_length=101)
    male_by_band: list[Count] = Field(min_length=3, max_length=3)
    household_counts: list[Count] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def coherent_margins(self) -> "Calibration":
        population = sum(self.age_counts)
        if not 0 < population <= 200_000 or not 0 < sum(self.household_counts) <= 100_000:
            raise ValueError("Pilot exceeds population/household limits or is empty")
        if any(
            male > sum(self.age_counts[start:end])
            for male, (start, end) in zip(self.male_by_band, BANDS, strict=True)
        ):
            raise ValueError("Sex margins exceed age band totals")
        return self


class PilotInput(StrictModel):
    schema_version: Literal["m3-input/1"]
    evidence_kind: Literal["official_aggregates", "invented_fixture"]
    calibration: Calibration
    heldout_male_by_age: list[Count] = Field(min_length=101, max_length=101)
    attribution: str = Field(min_length=1)
    source_hashes: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_holdout(self) -> "PilotInput":
        c = self.calibration
        if (c.territory == "DEMO_M3") != (self.evidence_kind == "invented_fixture"):
            raise ValueError("Fixture and official territory namespaces must be distinct")
        if any(
            len(h) != 64 or any(x not in "0123456789abcdef" for x in h)
            for h in self.source_hashes.values()
        ):
            raise ValueError("Evidence requires SHA-256 identities")
        if any(m > total for m, total in zip(self.heldout_male_by_age, c.age_counts, strict=True)):
            raise ValueError("Held-out cells exceed age totals")
        if [sum(self.heldout_male_by_age[a:b]) for a, b in BANDS] != c.male_by_band:
            raise ValueError("Held-out table and calibration must describe the same population")
        return self


class Experiment(StrictModel):
    schema_version: Literal["m3-experiment/1"] = "m3-experiment/1"
    seeds: list[Seed] = Field(
        default_factory=lambda: [1701, 1702, 1703, 1704, 1705], min_length=2, max_length=10
    )
    large_household_sizes: list[Annotated[int, Field(strict=True, ge=6, le=8)]] = Field(
        default_factory=lambda: [6, 7, 8], min_length=2, max_length=3
    )

    @model_validator(mode="after")
    def unique_runs(self) -> "Experiment":
        if len(set(self.seeds)) != len(self.seeds) or len(set(self.large_household_sizes)) != len(
            self.large_household_sizes
        ):
            raise ValueError("Duplicate seeds or scenarios do not measure uncertainty")
        return self
