import json
from pathlib import Path

import duckdb
import pytest

from itadb.pipeline.storage import sha256_file
from itadb.pipeline.validate import QualityError
from itadb.synthesis.citizenship_audit import audit_citizenship_batch
from itadb.synthesis.citizenship_generate import enrich_batch
from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipMunicipality
from itadb.synthesis.citizenship_runner import run_citizenship, verify_citizenship
from itadb.synthesis.national_models import Municipality, NationalInput, ResourceBudget
from itadb.synthesis.national_runner import run_national


@pytest.fixture
def constraints() -> tuple[NationalInput, CitizenshipInput]:
    municipalities, citizenships = [], []
    for code, province in [("900001", "900"), ("900002", "900"), ("901001", "901")]:
        male, female, fm, ff = [[0] * 101 for _ in range(4)]
        for age, m, f, foreign_m, foreign_f in [
            (0, 3, 2, 1, 0),
            (17, 1, 2, 0, 1),
            (40, 5, 5, 2, 0),
            (100, 1, 1, 0, 1),
        ]:
            male[age], female[age], fm[age], ff[age] = m, f, foreign_m, foreign_f
        municipalities.append(
            Municipality(
                code=code,
                province=province,
                region="90",
                male=male,
                female=female,
                households=[0, 2, 2, 1, 0, 0],
            )
        )
        citizenships.append(
            CitizenshipMunicipality(
                code=code,
                foreign_male=fm,
                foreign_female=ff,
                countries={"100": [7, 8], "201": [2, 1], "999": [1, 1]},
            )
        )
    base = NationalInput(
        evidence_kind="invented_load_fixture",
        population_reference="2025-01-01",
        household_reference="2024-12-31",
        geography_reference="2025-01-01",
        municipalities=municipalities,
        source_hashes={"fixture": "0" * 64},
        attribution="Invented CC0",
    )
    inputs = CitizenshipInput(
        population_reference=base.population_reference,
        evidence_kind=base.evidence_kind,
        municipalities=citizenships,
        country_labels={"100": "Italia", "201": "Albania", "999": "Apolide"},
        source_hashes={"fixture": "0" * 64},
        attribution="Invented CC0",
    )
    return base, inputs


def inventory(path: Path) -> dict[str, str]:
    return {p.relative_to(path).as_posix(): sha256_file(p) for p in path.rglob("*") if p.is_file()}


def test_enrichment_recovery_order_and_base_immutability(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput]
) -> None:
    base_inputs, inputs = constraints
    base = run_national(tmp_path / "base", base_inputs)
    original = inventory(base)
    with pytest.raises(InterruptedError):
        run_citizenship(tmp_path / "first", base, inputs, stop_after_batches=1)
    assert not list((tmp_path / "first/curated").rglob("manifest.json"))
    checkpoint = next((tmp_path / "first/state").rglob("checkpoint.json")).read_bytes()
    first = run_citizenship(tmp_path / "first", base, inputs)
    assert (first / "batch-0000/checkpoint.json").read_bytes() == checkpoint
    second = run_citizenship(tmp_path / "second", base, inputs, reverse_order=True)
    assert first.name == second.name
    assert inventory(first) == inventory(second)
    before = inventory(first)
    assert run_citizenship(tmp_path / "first", base, inputs) == first
    assert inventory(first) == before
    assert inventory(base) == original
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    assert report["persons"] == 60
    assert report["foreign_persons"] == 15
    assert report["stateless_persons"] == 6
    assert report["calibration"]["str_cells_checked"] == 606
    assert report["age_specific_country_joint"] == "synthetic_not_observed"
    verify_citizenship(first, base)


@pytest.mark.parametrize("kind", ["all_italian", "all_foreign", "zero_male_foreign"])
def test_empty_and_full_allocation(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput], kind: str
) -> None:
    base_inputs, inputs = constraints
    for m, population in zip(inputs.municipalities, base_inputs.municipalities, strict=True):
        if kind == "all_italian":
            m.foreign_male, m.foreign_female = [0] * 101, [0] * 101
            m.countries = {"100": [10, 10]}
        elif kind == "all_foreign":
            m.foreign_male, m.foreign_female = population.male[:], population.female[:]
            m.countries = {"201": [10, 10]}
        else:
            m.foreign_male = [0] * 101
            m.countries = {"100": [10, 8], "201": [0, 1], "999": [0, 1]}
    base = run_national(tmp_path / "base", base_inputs)
    result = run_citizenship(tmp_path, base, inputs)
    verify_citizenship(result, base)


@pytest.mark.parametrize(
    "damage",
    [
        "age_exceeds_base",
        "rcs_disagrees",
        "coverage",
        "unknown_country",
        "date",
        "universe",
        "duplicate",
    ],
)
def test_incompatible_inputs(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput], damage: str
) -> None:
    base_inputs, inputs = constraints
    m = inputs.municipalities[0]
    if damage == "age_exceeds_base":
        m.foreign_male[1], m.foreign_male[0] = 1, 0
    elif damage == "rcs_disagrees":
        m.countries["100"][0] -= 1
    elif damage == "coverage":
        inputs.municipalities.pop()
    elif damage == "unknown_country":
        m.countries["777"] = [0, 0]
    elif damage == "date":
        inputs.population_reference = "2024-01-01"
    elif damage == "universe":
        inputs.evidence_kind = "official_aggregates"
    else:
        inputs.municipalities.append(m)
    base = run_national(tmp_path / "base", base_inputs)
    with pytest.raises(ValueError):
        run_citizenship(tmp_path, base, inputs)
    assert not list((tmp_path / "curated").rglob("manifest.json"))


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE p SET citizenship_code='100' WHERE citizenship_code='201'",
        "UPDATE p SET citizenship_code=NULL WHERE person_id=1",
        "UPDATE p SET birth_year=2000 WHERE person_id=1",
        "UPDATE p SET household_id=NULL WHERE reference_adult",
        "UPDATE p SET person_id=2 WHERE person_id=1",
        "UPDATE p SET citizenship_code='777' WHERE citizenship_code='999'",
    ],
)
def test_independent_audit_rejects_corruption(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput], sql: str
) -> None:
    base_inputs, inputs = constraints
    base = run_national(tmp_path / "base", base_inputs) / "batch-0000"
    output = tmp_path / "enriched"
    group = inputs.municipalities[:2]
    enrich_batch(base, output, group, 2025, ResourceBudget(), lambda _: None)
    with duckdb.connect() as con:
        con.execute("CREATE TABLE p AS FROM read_parquet(?)", [str(output / "persons.parquet")])
        con.execute(sql)
        con.execute("COPY p TO ? (FORMAT PARQUET)", [str(output / "persons.parquet")])
    with pytest.raises(QualityError):
        audit_citizenship_batch(output, base, group, 2025, ResourceBudget())


def test_corrupt_resume_preserved(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput]
) -> None:
    base_inputs, inputs = constraints
    base = run_national(tmp_path / "base", base_inputs)
    with pytest.raises(InterruptedError):
        run_citizenship(tmp_path, base, inputs, stop_after_batches=1)
    path = next((tmp_path / "state").rglob("persons.parquet"))
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="checksum"):
        run_citizenship(tmp_path, base, inputs)
    assert path.read_bytes() == b"damaged"
    assert not list((tmp_path / "curated").rglob("manifest.json"))


@pytest.mark.parametrize("damage", ["report", "approval", "extra", "base", "checkpoint"])
def test_rehashed_metadata_tampering(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput], damage: str
) -> None:
    base_inputs, inputs = constraints
    base = run_national(tmp_path / "base", base_inputs)
    result = run_citizenship(tmp_path, base, inputs)
    manifest = json.loads((result / "manifest.json").read_text())
    if damage == "approval":
        manifest["public_release"] = True
    elif damage == "base":
        (base / "report.json").write_text("corrupted")
    else:
        name = {
            "report": "report.json",
            "extra": "unknown.json",
            "checkpoint": "batch-0000/checkpoint.json",
        }[damage]
        path = result / name
        contents = {} if damage == "extra" else json.loads(path.read_text(encoding="utf-8"))
        contents["batch" if damage == "checkpoint" else "age_specific_country_joint"] = "wrong"
        path.write_text(json.dumps(contents), encoding="utf-8")
        manifest["files"][name] = sha256_file(path)
    (result / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_citizenship(result, base)


def test_budget_failure_no_snapshot(
    tmp_path: Path,
    constraints: tuple[NationalInput, CitizenshipInput],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_inputs, inputs = constraints
    base = run_national(tmp_path / "base", base_inputs)
    monkeypatch.setattr("itadb.synthesis.national_runtime.peak_rss_bytes", lambda: 9 * 2**30)
    with pytest.raises(RuntimeError, match="RSS budget"):
        run_citizenship(tmp_path, base, inputs)
    assert not list((tmp_path / "curated").rglob("manifest.json"))


def test_country_totals_cannot_hide_wrong_age_distribution(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput]
) -> None:
    base_inputs, inputs = constraints
    base = run_national(tmp_path / "base", base_inputs) / "batch-0000"
    output = tmp_path / "enriched"
    group = inputs.municipalities[:2]
    enrich_batch(base, output, group, 2025, ResourceBudget(), lambda _: None)
    with duckdb.connect() as con:
        con.execute("CREATE TABLE p AS FROM read_parquet(?)", [str(output / "persons.parquet")])
        foreign, italian, country = con.execute("""SELECT f.person_id,i.person_id,f.citizenship_code
            FROM p f JOIN p i USING(municipality,sex)
            WHERE f.citizenship_code<>'100' AND i.citizenship_code='100'
            AND f.birth_year IS DISTINCT FROM i.birth_year LIMIT 1""").fetchall()[0]
        con.execute(
            "UPDATE p SET citizenship_code=CASE WHEN person_id=? THEN '100' ELSE ? END "
            "WHERE person_id IN (?,?)",
            [foreign, country, foreign, italian],
        )
        con.execute("COPY p TO ? (FORMAT PARQUET)", [str(output / "persons.parquet")])
    with pytest.raises(QualityError) as error:
        audit_citizenship_batch(output, base, group, 2025, ResourceBudget())
    assert error.value.report["checks"]["rcs_municipality_sex_country"]
    assert not error.value.report["checks"]["str_municipality_sex_age"]


def test_unknown_staging_file_prevents_completion(
    tmp_path: Path, constraints: tuple[NationalInput, CitizenshipInput]
) -> None:
    base_inputs, inputs = constraints
    base = run_national(tmp_path / "base", base_inputs)
    with pytest.raises(InterruptedError):
        run_citizenship(tmp_path, base, inputs, stop_after_batches=1)
    stage = next((tmp_path / "state").glob("citizenship-work-*"))
    (stage / "unknown.txt").write_text("preserve evidence")
    with pytest.raises(ValueError, match="staging artifacts"):
        run_citizenship(tmp_path, base, inputs)
    assert (stage / "unknown.txt").read_text() == "preserve evidence"
    assert not list((tmp_path / "curated").rglob("manifest.json"))
