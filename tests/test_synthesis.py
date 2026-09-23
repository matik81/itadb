import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from itadb.cli import app
from itadb.pipeline.storage import sha256_file
from itadb.pipeline.validate import QualityError
from itadb.synthesis.audit import audit
from itadb.synthesis.generate import check_feasibility, generate, integer_joint
from itadb.synthesis.models import Calibration, Experiment, PilotInput
from itadb.synthesis.runner import run_pilot, verify_run


@pytest.fixture
def pilot() -> PilotInput:
    return PilotInput.model_validate_json(Path("tests/fixtures/m3-invented.json").read_bytes())


@pytest.fixture
def experiment() -> Experiment:
    return Experiment(seeds=[17, 18], large_household_sizes=[6, 8])


def test_reconstruction_margins_family_rules_and_repeatability(
    tmp_path: Path, pilot: PilotInput
) -> None:
    c = pilot.calibration
    for name, seed, size in [("a", 17, 6), ("b", 17, 6), ("c", 18, 6), ("d", 17, 8)]:
        generate(c, seed, size, tmp_path / name)
        report = audit(tmp_path / name, pilot, size)
        assert all(report["checks"].values())
        assert report["persons"] == 40 and report["households"] == 12
        assert report["unassigned_adults"] == (12 if size == 6 else 10)
        assert report["calibration_max_absolute_error"] == 0
        assert report["heldout"]["total_variation_distance"] in [0.15, 0.2]
        cells = report["heldout"]["cells"]
        assert report["heldout"]["reference_evidence_kind"] == "invented_fixture"
        assert all("reference" in cell and "observed" not in cell for cell in cells)
        assert (
            sum(abs(r["error"]) for r in cells) / 80
            == report["heldout"]["total_variation_distance"]
        )
    for filename in ["persons.parquet", "households.parquet"]:
        assert (tmp_path / "a" / filename).read_bytes() == (tmp_path / "b" / filename).read_bytes()
    assert (tmp_path / "a/persons.parquet").read_bytes() != (
        tmp_path / "c/persons.parquet"
    ).read_bytes()


def test_exact_rounding_with_zeros_and_extreme_sex_margins(pilot: PilotInput) -> None:
    for males in [[0, 0, 0], [6, 22, 12], [1, 21, 1], [3, 11, 5]]:
        c = Calibration.model_validate({**pilot.calibration.model_dump(), "male_by_band": males})
        for seed in range(20):
            actual = integer_joint(c, random.Random(seed))
            assert [sum(actual[:18]), sum(actual[18:65]), sum(actual[65:])] == males
            assert all(0 <= m <= n for m, n in zip(actual, c.age_counts, strict=True))
    c = pilot.calibration.model_dump()
    c["age_counts"][5] = 0
    c["male_by_band"][0] = 0
    assert integer_joint(Calibration.model_validate(c), random.Random(1))[5] == 0


@pytest.mark.parametrize(
    "mutation", ["negative", "float", "bool", "excess", "extra", "period", "missing_age"]
)
def test_invalid_margins_rejected(pilot: PilotInput, mutation: str) -> None:
    c = pilot.calibration.model_dump()
    if mutation == "negative":
        c["age_counts"][0] = -1
    elif mutation == "float":
        c["age_counts"][0] = 1.2
    elif mutation == "bool":
        c["age_counts"][0] = True
    elif mutation == "excess":
        c["age_counts"][0] = 200_000
    elif mutation == "extra":
        c["real_name"] = "forbidden"
    elif mutation == "period":
        c["household_reference"] = "2024-01-01"
    else:
        c["age_counts"].pop()
    with pytest.raises(ValidationError):
        Calibration.model_validate(c)


def test_holdout_namespace_and_experiment_validation(pilot: PilotInput) -> None:
    for changes in [{"evidence_kind": "official_aggregates"}, {"source_hashes": {"x": "bad"}}]:
        with pytest.raises(ValidationError):
            PilotInput.model_validate({**pilot.model_dump(), **changes})
    p = pilot.model_dump()
    p["heldout_male_by_age"][30] += 1
    with pytest.raises(ValidationError):
        PilotInput.model_validate(p)
    for changes in [
        {"seeds": [1]},
        {"seeds": [1, 1]},
        {"seeds": [-1, 2]},
        {"large_household_sizes": [6, 9]},
        {"large_household_sizes": [6, 6]},
    ]:
        with pytest.raises(ValidationError):
            Experiment.model_validate(changes)


def test_infeasible_constraints_fail_before_output(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment
) -> None:
    data = pilot.model_dump()
    data["calibration"]["household_counts"] = [35, 0, 0, 0, 0, 0]
    invalid = PilotInput.model_validate(data)
    with pytest.raises(ValueError, match="adult-per-household"):
        run_pilot(tmp_path, invalid, experiment)
    assert not list((tmp_path / "curated").rglob("manifest.json"))
    assert list((tmp_path / "quarantine").glob("m3-*.json"))
    c = Calibration.model_validate(
        {**pilot.calibration.model_dump(), "household_counts": [0, 0, 0, 0, 0, 7]}
    )
    with pytest.raises(ValueError, match="capacity"):
        check_feasibility(c, 6)
    with pytest.raises(ValueError, match="Unreviewed"):
        check_feasibility(pilot.calibration, 9)


def rewrite_persons(directory: Path, statement: str) -> None:
    path = directory / "persons.parquet"
    with duckdb.connect() as con:
        con.execute("CREATE TABLE p AS SELECT * FROM read_parquet(?)", [str(path)])
        con.execute(statement)
        con.execute("COPY p TO ? (FORMAT PARQUET)", [str(path)])


@pytest.mark.parametrize(
    "statement,gate",
    [
        ("UPDATE p SET household_id=999 WHERE person_id=1", "foreign_keys"),
        ("UPDATE p SET reference_adult=false WHERE person_id=1", "family_constraints"),
        ("UPDATE p SET person_id=2 WHERE person_id=1", "person_identity_and_total"),
        ("UPDATE p SET household_id=NULL WHERE age<18", "person_domains_and_minor_assignment"),
        ("UPDATE p SET sex='X' WHERE person_id=1", "person_domains_and_minor_assignment"),
        ("UPDATE p SET data_kind='observed'", "person_domains_and_minor_assignment"),
        ("UPDATE p SET age=31 WHERE age=30", "age_margins"),
        ("ALTER TABLE p ADD COLUMN real_identifier VARCHAR", "persons_schema"),
        ("ALTER TABLE p ALTER person_id TYPE DOUBLE", "persons_schema"),
    ],
)
def test_independent_audit_detects_corruption(
    tmp_path: Path, pilot: PilotInput, statement: str, gate: str
) -> None:
    directory = tmp_path / "run"
    generate(pilot.calibration, 17, 6, directory)
    rewrite_persons(directory, statement)
    with pytest.raises(QualityError) as error:
        audit(directory, pilot, 6)
    assert error.value.report["checks"][gate] is False


def test_retry_identity_concurrency_and_cli(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment
) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_pilot(tmp_path, pilot, experiment), range(2)))
    assert results[0] == results[1]
    directory = results[0]
    before = {p: sha256_file(p) for p in directory.rglob("*") if p.is_file()}
    assert run_pilot(tmp_path, pilot, experiment) == directory
    assert before == {p: sha256_file(p) for p in directory.rglob("*") if p.is_file()}
    manifest = verify_run(directory)
    assert manifest["public_release"] is False
    result = CliRunner().invoke(app, ["verify-m3", "--run", str(directory)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["verified"] is True
    other = run_pilot(tmp_path, pilot, Experiment(seeds=[17, 19], large_household_sizes=[6, 8]))
    assert other != directory


def test_holdout_never_changes_generation(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment
) -> None:
    original = run_pilot(tmp_path, pilot, experiment)
    changed = pilot.model_dump()
    changed["heldout_male_by_age"][30] -= 2
    changed["heldout_male_by_age"][40] += 2
    alternate = run_pilot(tmp_path, PilotInput.model_validate(changed), experiment)
    assert original != alternate
    assert (original / "report.json").read_bytes() != (alternate / "report.json").read_bytes()
    for path in original.rglob("*.parquet"):
        assert path.read_bytes() == (alternate / path.relative_to(original)).read_bytes()


def test_failure_never_completes_and_preserves_attempt(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object) -> None:
        raise QualityError({"checks": {"injected_failure": False}})

    monkeypatch.setattr("itadb.synthesis.runner.audit", fail)
    with pytest.raises(QualityError):
        run_pilot(tmp_path, pilot, experiment)
    assert not list((tmp_path / "curated").rglob("manifest.json"))
    assert list((tmp_path / "state").rglob("persons.parquet"))
    assert list((tmp_path / "quarantine").glob("*.json"))


@pytest.mark.parametrize("damage", ["parquet", "report", "missing", "extra", "manifest"])
def test_retry_rejects_tampered_experiment(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment, damage: str
) -> None:
    directory = run_pilot(tmp_path, pilot, experiment)
    if damage == "parquet":
        next(directory.rglob("persons.parquet")).write_bytes(b"corrupted")
    elif damage == "report":
        (directory / "report.json").write_text("{}")
    elif damage == "missing":
        (directory / "README.md").unlink()
    elif damage == "extra":
        (directory / "unexpected.txt").write_text("extra")
    else:
        path = directory / "manifest.json"
        meta = json.loads(path.read_text())
        meta["descriptor"]["algorithm"] = "changed"
        path.write_text(json.dumps(meta))
    with pytest.raises(ValueError):
        run_pilot(tmp_path, pilot, experiment)


@pytest.mark.parametrize("damage", ["metric", "uncertainty", "replicates", "approval"])
def test_independent_recalculation_rejects_rehashed_report(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment, damage: str
) -> None:
    directory = run_pilot(tmp_path, pilot, experiment)
    report_path = directory / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if damage == "metric":
        report["replicates"][0]["audit"]["heldout"]["total_variation_distance"] = 0
    elif damage == "uncertainty":
        report["uncertainty"][0]["metrics"]["unassigned_adults"]["mean"] = 0
    elif damage == "replicates":
        report["replicates"].pop()
    else:
        report["public_release"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["report.json"] = sha256_file(report_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_run(directory)
