import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from typer.main import get_command
from typer.testing import CliRunner

from itadb.cli import app
from itadb.pipeline.storage import sha256_file
from itadb.pipeline.validate import QualityError
from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipMunicipality
from itadb.synthesis.citizenship_runner import run_citizenship, verify_citizenship
from itadb.synthesis.national_models import Municipality, NationalInput, ResourceBudget
from itadb.synthesis.national_runner import canonical, run_national, verify_national
from itadb.synthesis.population_audit import audit_population_batch
from itadb.synthesis.population_generate import assign_households
from itadb.synthesis.population_models import PRIORITY_ORDER, PopulationInput, PopulationReference
from itadb.synthesis.population_runner import run_population, verify_population


@pytest.fixture
def constraints() -> PopulationInput:
    national, citizenships = [], []
    for code, province in [("900001", "900"), ("900002", "900"), ("901001", "901")]:
        male, female, fm, ff = [[0] * 101 for _ in range(4)]
        for age, m, f, foreign_m, foreign_f in [
            (0, 3, 2, 1, 0),
            (17, 1, 2, 0, 1),
            (40, 5, 5, 2, 0),
            (100, 1, 1, 0, 1),
        ]:
            male[age], female[age], fm[age], ff[age] = m, f, foreign_m, foreign_f
        national.append(
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
    return PopulationInput(
        national=NationalInput(
            evidence_kind="invented_load_fixture",
            population_reference="2025-01-01",
            household_reference="2024-12-31",
            geography_reference="2025-01-01",
            municipalities=national,
            source_hashes={"fixture": "0" * 64},
            attribution="Invented CC0",
        ),
        citizenship=CitizenshipInput(
            evidence_kind="invented_load_fixture",
            population_reference="2025-01-01",
            municipalities=citizenships,
            source_hashes={"fixture": "0" * 64},
            attribution="Invented CC0",
            country_labels={"100": "Italia", "201": "Albania", "999": "Apolide"},
        ),
    )


def inventory(directory: Path) -> dict[str, str]:
    return {
        p.relative_to(directory).as_posix(): sha256_file(p)
        for p in directory.rglob("*")
        if p.is_file()
    }


def test_real_order_and_legacy_equivalence(
    tmp_path: Path,
    constraints: PopulationInput,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = []

    def household_stage(municipalities, reference, directory, offset, budget, progress):
        assert (directory / "individuals.parquet").is_file()
        assert not (directory / "persons.parquet").exists()
        assert not (directory / "households.parquet").exists()
        with duckdb.connect() as con:
            view = con.read_parquet(str(directory / "individuals.parquet"))
            assert "citizenship_code" in view.columns
            assert "household_id" not in view.columns
            assert view.filter("citizenship_code IS NULL").count("*").fetchone()[0] == 0
        original = sha256_file(directory / "individuals.parquet")
        assign_households(municipalities, reference, directory, offset, budget, progress)
        assert sha256_file(directory / "individuals.parquet") == original
        seen.append(directory)

    monkeypatch.setattr("itadb.synthesis.population_generate.assign_households", household_stage)
    result = run_population(tmp_path / "current", constraints)
    assert len(seen) == 2
    manifest = verify_population(result)
    assert manifest["descriptor"]["execution_order"] == list(PRIORITY_ORDER)
    base = run_national(tmp_path / "legacy", constraints.national)
    enriched = run_citizenship(tmp_path / "legacy", base, constraints.citizenship)
    verify_national(base)
    verify_citizenship(enriched, base)
    with duckdb.connect() as con:
        for batch in result.glob("batch-*"):
            for name in ["persons.parquet", "households.parquet"]:
                assert (
                    con.read_parquet(str(batch / name)).fetchall()
                    == con.read_parquet(str(enriched / batch.name / name)).fetchall()
                )


def test_recovery_retry_order_and_input_permutation(
    tmp_path: Path, constraints: PopulationInput
) -> None:
    with pytest.raises(InterruptedError):
        run_population(tmp_path, constraints, stop_after_batches=1)
    assert not list((tmp_path / "curated").rglob("manifest.json"))
    checkpoint = next((tmp_path / "state").rglob("checkpoint.json")).read_bytes()
    first = run_population(tmp_path, constraints)
    assert (first / "batch-0000/checkpoint.json").read_bytes() == checkpoint
    before = inventory(first)
    assert run_population(tmp_path, constraints) == first
    assert inventory(first) == before
    constraints.national.municipalities.reverse()
    constraints.citizenship.municipalities.reverse()
    second = run_population(tmp_path / "reverse", constraints, reverse_order=True)
    assert first.name == second.name
    assert inventory(first) == inventory(second)
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    assert report["persons"] == 60
    assert report["foreign_persons"] == 15
    assert report["calibration"]["first_three_stages_unchanged_by_households"]
    assert report["household_age_citizenship_relations"] == "random_constrained_not_calibrated"


def test_interruption_between_individuals_and_families(
    tmp_path: Path,
    constraints: PopulationInput,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(*args):
        raise InterruptedError("between stages")

    with monkeypatch.context() as context:
        context.setattr("itadb.synthesis.population_generate.assign_households", interrupt)
        with pytest.raises(InterruptedError):
            run_population(tmp_path, constraints)
    orphan = next((tmp_path / "state").rglob("individuals.parquet"))
    digest = sha256_file(orphan)
    assert not list((tmp_path / "curated").rglob("manifest.json"))
    result = run_population(tmp_path, constraints)
    evidence = next((tmp_path / "state").glob("population-interrupted-*/individuals.parquet"))
    assert sha256_file(evidence) == digest
    verify_population(result)


def test_final_margins_cannot_hide_household_stage_mutation(
    tmp_path: Path, constraints: PopulationInput
) -> None:
    result = run_population(tmp_path, constraints) / "batch-0000"
    with duckdb.connect() as con:
        con.execute("CREATE TABLE p AS FROM read_parquet(?)", [str(result / "persons.parquet")])
        foreign, italian, country = con.execute("""SELECT f.person_id,i.person_id,f.citizenship_code
            FROM p f JOIN p i USING(municipality,sex,birth_year)
            WHERE f.citizenship_code<>'100' AND i.citizenship_code='100' LIMIT 1""").fetchone()
        con.execute(
            "UPDATE p SET citizenship_code=CASE WHEN person_id=? THEN '100' ELSE ? END "
            "WHERE person_id IN (?,?)",
            [foreign, country, foreign, italian],
        )
        con.execute("COPY p TO ? (FORMAT PARQUET)", [str(result / "persons.parquet")])
    with pytest.raises(QualityError) as error:
        audit_population_batch(
            result,
            constraints.national.municipalities[:2],
            constraints.citizenship.municipalities[:2],
            "2025-01-01",
            0,
            0,
            ResourceBudget(),
        )
    assert not error.value.report["checks"]["first_three_stages_unchanged"]


@pytest.mark.parametrize("damage", ["corrupt", "extra", "budget"])
def test_failure_preserves_evidence_and_prevents_completion(
    tmp_path: Path,
    constraints: PopulationInput,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    with pytest.raises(InterruptedError):
        run_population(tmp_path, constraints, stop_after_batches=1)
    stage = next((tmp_path / "state").glob("population-work-*"))
    if damage == "corrupt":
        evidence = stage / "batch-0000/individuals.parquet"
        evidence.write_bytes(b"damaged")
    elif damage == "extra":
        evidence = stage / "unexpected.txt"
        evidence.write_bytes(b"preserve")
    else:
        evidence = stage / "input.json"
        monkeypatch.setattr("itadb.synthesis.national_runtime.peak_rss_bytes", lambda: 9 * 2**30)
    digest = sha256_file(evidence)
    with pytest.raises((ValueError, RuntimeError)):
        run_population(tmp_path, constraints)
    assert sha256_file(evidence) == digest
    assert not list((tmp_path / "curated").rglob("manifest.json"))


@pytest.mark.parametrize("field", ["priority_order", "execution_order", "reference"])
def test_rehashed_old_order_rejected(
    tmp_path: Path, constraints: PopulationInput, field: str
) -> None:
    result = run_population(tmp_path, constraints)
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    old_order = ["sex_age", "geography", "households", "citizenship"]
    if field == "reference":
        manifest["descriptor"][field]["priorities"] = old_order
    else:
        manifest["descriptor"][field] = old_order
    identity = hashlib.sha256(canonical(manifest["descriptor"])).hexdigest()
    target = result.with_name(identity)
    result.rename(target)
    manifest["run_id"] = identity
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_population(target)


@pytest.mark.parametrize("kind", ["all_italian", "all_foreign", "zero_households"])
def test_empty_and_full_constraints(
    tmp_path: Path, constraints: PopulationInput, kind: str
) -> None:
    for base, citizenship in zip(
        constraints.national.municipalities, constraints.citizenship.municipalities, strict=True
    ):
        if kind == "all_italian":
            citizenship.foreign_male, citizenship.foreign_female = [0] * 101, [0] * 101
            citizenship.countries = {"100": [10, 10]}
        elif kind == "all_foreign":
            citizenship.foreign_male, citizenship.foreign_female = base.male[:], base.female[:]
            citizenship.countries = {"201": [10, 10]}
        else:
            base.households = [0] * 6
            for counts in [base.male, base.female]:
                counts[40] += sum(counts[:18])
                counts[:18] = [0] * 18
            citizenship.foreign_male, citizenship.foreign_female = [0] * 101, [0] * 101
            citizenship.countries = {"100": [10, 10]}
    result = run_population(tmp_path, constraints)
    verify_population(result)


def test_contract_and_cli() -> None:
    reference = PopulationReference.model_validate_json(
        Path("contracts/population-reference-v1.json").read_bytes()
    )
    assert reference == PopulationReference()
    result = CliRunner().invoke(
        app,
        ["synthesize-population", "--help"],
        terminal_width=60,
        color=True,
    )
    assert result.exit_code == 0
    command = get_command(app).commands["synthesize-population"]
    options = {option for parameter in command.params for option in parameter.opts}
    assert "--base-run" not in options
    assert "--citizenship-inputs" in options


@pytest.mark.parametrize("damage", ["age_exceeds_cell", "coverage", "date", "household_capacity"])
def test_incompatible_inputs_never_complete(
    tmp_path: Path,
    constraints: PopulationInput,
    damage: str,
) -> None:
    if damage == "age_exceeds_cell":
        foreign = constraints.citizenship.municipalities[0].foreign_male
        foreign[0], foreign[1] = 0, 1
    elif damage == "coverage":
        constraints.citizenship.municipalities.pop()
    elif damage == "date":
        constraints.citizenship.population_reference = "2024-01-01"
    else:
        constraints.national.municipalities[0].households = [100, 0, 0, 0, 0, 0]
    with pytest.raises(ValueError):
        run_population(tmp_path, constraints)
    assert not list(tmp_path.rglob("manifest.json"))
    assert list((tmp_path / "quarantine").glob("population-*.json"))
