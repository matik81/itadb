"""Current population reference: citizenship is fixed before household allocation."""

from typing import Literal

from pydantic import Field, model_validator

from itadb.synthesis.citizenship_models import CitizenshipInput
from itadb.synthesis.models import StrictModel
from itadb.synthesis.national_models import NationalInput

PRIORITY_ORDER = ("sex_age", "geography", "citizenship", "households")


class PopulationInput(StrictModel):
    schema_version: Literal["population-input/1"] = "population-input/1"
    national: NationalInput
    citizenship: CitizenshipInput

    @model_validator(mode="after")
    def coherent(self) -> "PopulationInput":
        self.citizenship.check_base(self.national)
        return self


class PopulationReference(StrictModel):
    schema_version: Literal["population-reference/1"] = "population-reference/1"
    fidelity_version: Literal[5] = 5
    seed: Literal[1701] = 1701
    large_household_size: Literal[6] = 6
    priorities: list[str] = Field(default_factory=lambda: list(PRIORITY_ORDER))
    household_allocation: Literal["random_within_municipality_adult_constraints"] = (
        "random_within_municipality_adult_constraints"
    )
    country_age_assumption: Literal["conditional_exchangeability"] = "conditional_exchangeability"
    household_age_citizenship_relations: Literal["not_calibrated"] = "not_calibrated"
    distribution: Literal["local_only"] = "local_only"

    @model_validator(mode="after")
    def fixed_order(self) -> "PopulationReference":
        if self.priorities != list(PRIORITY_ORDER):
            raise ValueError("Changing the population stage order requires a new reference")
        return self
