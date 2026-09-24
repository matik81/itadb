"""Invented load constraints shared by synthesis benchmarks."""

import hashlib

from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipMunicipality
from itadb.synthesis.national_models import Municipality, NationalInput


def national_fixture(population: int) -> NationalInput:
    if population not in {1_000_000, 10_000_000}:
        raise ValueError("Choose the prescribed 1M or 10M load fixture")
    municipalities = []
    for index in range(20):
        n = population // 20
        q, remainder = divmod(n, 202)
        cells = [q + int(i < remainder) for i in range(202)]
        municipalities.append(
            Municipality(
                code=f"{900 + index // 10:03d}{index + 1:03d}",
                province=f"{900 + index // 10:03d}",
                region="90",
                male=cells[:101],
                female=cells[101:],
                households=[
                    n // 5,
                    n // 10,
                    n * 6 // 100,
                    n * 3 // 100,
                    n * 8 // 1000,
                    n * 2 // 1000,
                ],
            )
        )
    return NationalInput(
        evidence_kind="invented_load_fixture",
        population_reference="2025-01-01",
        household_reference="2024-12-31",
        geography_reference="2025-01-01",
        municipalities=municipalities,
        source_hashes={"fixture_specification": hashlib.sha256(b"m4-load/1").hexdigest()},
        attribution="Fixture di carico interamente inventata, CC0; non popolazione ISTAT",
    )


def citizenship_fixture(base: NationalInput) -> CitizenshipInput:
    if base.evidence_kind != "invented_load_fixture":
        raise ValueError("Citizenship load fixtures cannot be applied to official aggregates")
    municipalities = []
    for m in base.municipalities:
        fm, ff = [[n // 5 for n in counts] for counts in [m.male, m.female]]
        countries: dict[str, list[int]] = {c: [] for c in ["100", "201", "235", "999"]}
        for foreign, population in [(fm, m.male), (ff, m.female)]:
            n = sum(foreign)
            stateless = int(n > 0)
            countries["100"].append(sum(population) - n)
            countries["201"].append(n // 2)
            countries["235"].append(n - n // 2 - stateless)
            countries["999"].append(stateless)
        municipalities.append(
            CitizenshipMunicipality(
                code=m.code, foreign_male=fm, foreign_female=ff, countries=countries
            )
        )
    return CitizenshipInput(
        population_reference=base.population_reference,
        evidence_kind="invented_load_fixture",
        municipalities=municipalities,
        country_labels={"100": "Italia", "201": "Albania", "235": "Romania", "999": "Apolide"},
        source_hashes={"fixture_specification": hashlib.sha256(b"citizenship-load/1").hexdigest()},
        attribution="Fixture di carico inventata, CC0; non dati osservati ISTAT",
    )
