"""Versioned citizenship constraints; existing demographic attributes are immutable."""

import re
from typing import Annotated, Literal

from pydantic import Field, model_validator

from itadb.synthesis.models import StrictModel
from itadb.synthesis.national_models import Code, Count, Digest, NationalInput

CountryCode = Annotated[str, Field(pattern=r"^[0-9]{3}$")]


class CitizenshipMunicipality(StrictModel):
    code: Code
    foreign_male: list[Count] = Field(min_length=101, max_length=101)
    foreign_female: list[Count] = Field(min_length=101, max_length=101)
    countries: dict[CountryCode, Annotated[list[Count], Field(min_length=2, max_length=2)]]


class CitizenshipInput(StrictModel):
    schema_version: Literal["citizenship-input/1"] = "citizenship-input/1"
    population_reference: str
    evidence_kind: Literal["official_aggregates", "invented_load_fixture"]
    municipalities: list[CitizenshipMunicipality] = Field(min_length=1, max_length=10_000)
    country_labels: dict[CountryCode, str] = Field(min_length=1, max_length=300)
    source_hashes: dict[str, Digest] = Field(min_length=1)
    attribution: str = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self) -> "CitizenshipInput":
        if len({m.code for m in self.municipalities}) != len(self.municipalities):
            raise ValueError("Duplicate citizenship municipality")
        if self.country_labels.get("100") != "Italia":
            raise ValueError("ISTAT code 100 must denote Italian citizenship")
        if "999" in self.country_labels and self.country_labels["999"] != "Apolide":
            raise ValueError("ISTAT code 999 must denote statelessness")
        for code, label in self.country_labels.items():
            if not re.fullmatch(r"[0-9]{3}", code) or not label.strip():
                raise ValueError("Invalid citizenship dictionary")
        for m in self.municipalities:
            if not m.countries or not set(m.countries) <= self.country_labels.keys():
                raise ValueError("Unclassified citizenship")
            for index, foreign in enumerate([m.foreign_male, m.foreign_female]):
                if sum(foreign) != sum(n[index] for c, n in m.countries.items() if c != "100"):
                    raise ValueError("STR and RCS foreign totals disagree")
        return self

    def check_base(self, base: NationalInput) -> None:
        if (
            self.population_reference != base.population_reference
            or self.evidence_kind != base.evidence_kind
        ):
            raise ValueError("Citizenship and base reference/universe differ")
        by_code = {m.code: m for m in self.municipalities}
        if set(by_code) != {m.code for m in base.municipalities}:
            raise ValueError("Citizenship municipal coverage differs from the base")
        for original in base.municipalities:
            m = by_code[original.code]
            for index, (foreign, population) in enumerate(
                [(m.foreign_male, original.male), (m.foreign_female, original.female)]
            ):
                if any(f > n for f, n in zip(foreign, population, strict=True)):
                    raise ValueError("Foreign age/sex count exceeds the base cell")
                if sum(n[index] for n in m.countries.values()) != sum(population):
                    raise ValueError("RCS and base sex totals disagree")


class CitizenshipReference(StrictModel):
    schema_version: Literal["citizenship-reference/1"] = "citizenship-reference/1"
    seed: Literal[1701] = 1701
    selection: Literal["hash_within_municipality_sex_age"] = "hash_within_municipality_sex_age"
    allocation: Literal["shuffle_countries_within_municipality_sex"] = (
        "shuffle_countries_within_municipality_sex"
    )
    country_age_assumption: Literal["conditional_exchangeability"] = "conditional_exchangeability"
    italian_code: Literal["100"] = "100"
    stateless_code: Literal["999"] = "999"
    distribution: Literal["local_only"] = "local_only"
