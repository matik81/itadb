import json
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
from itadb.synthesis.generate import check_feasibility, generate
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
        assert report["calibration_joint"]["total_variation_distance"] == 0
        cells = report["calibration_joint"]["cells"]
        assert len(cells) == 202 and all(cell["error"] == 0 for cell in cells)
        assert report["calibration_joint"]["reference_evidence_kind"] == "invented_fixture"
        assert all("reference" in cell and "observed" not in cell for cell in cells)
        assert (
            sum(abs(r["error"]) for r in cells) / 80
            == report["calibration_joint"]["total_variation_distance"]
        )
    for filename in ["persons.parquet", "households.parquet"]:
        assert (tmp_path / "a" / filename).read_bytes() == (tmp_path / "b" / filename).read_bytes()
    assert (tmp_path / "a/persons.parquet").read_bytes() != (
        tmp_path / "c/persons.parquet"
    ).read_bytes()


@pytest.mark.parametrize("composition", ["all_female", "all_male", "unbalanced", "zero_minors"])
def test_exact_joint_with_zeros_and_extreme_cells(
    tmp_path: Path, pilot: PilotInput, composition: str
) -> None:
    data = pilot.model_dump()
    c = data["calibration"]
    # Exercise the open 100+ category as well as empty ages and extreme sex ratios.
    c["age_counts"][100], c["age_counts"][80] = c["age_counts"][80], 0
    c["male_by_age"][100], c["male_by_age"][80] = c["male_by_age"][80], 0
    if composition == "all_female":
        c["male_by_age"] = [0] * 101
    elif composition == "all_male":
        c["male_by_age"] = list(c["age_counts"])
    elif composition == "unbalanced":
        c["male_by_age"][30], c["male_by_age"][40] = 12, 0
    else:
        c["age_counts"][30] += c["age_counts"][5]
        c["male_by_age"][30] += c["male_by_age"][5]
        c["age_counts"][5] = c["male_by_age"][5] = 0
    inputs = PilotInput.model_validate(data)
    for seed in [17, 18]:
        for size in [6, 8]:
            directory = tmp_path / f"{seed}-{size}"
            generate(inputs.calibration, seed, size, directory)
            report = audit(directory, inputs, size)
            assert report["checks"]["sex_age_joint_counts"]
            assert all(cell["error"] == 0 for cell in report["calibration_joint"]["cells"])


@pytest.mark.parametrize(
    "mutation",
    [
        "negative",
        "float",
        "bool",
        "excess",
        "extra",
        "period",
        "missing_age",
        "missing_male",
        "male_exceeds_age",
        "negative_male",
        "float_male",
        "bool_male",
    ],
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
    elif mutation == "missing_age":
        c["age_counts"].pop()
    elif mutation == "missing_male":
        c["male_by_age"].pop()
    elif mutation == "male_exceeds_age":
        c["male_by_age"][0] = 1
    elif mutation == "negative_male":
        c["male_by_age"][0] = -1
    elif mutation == "float_male":
        c["male_by_age"][30] = 1.2
    else:
        c["male_by_age"][30] = True
    with pytest.raises(ValidationError):
        Calibration.model_validate(c)


def test_namespace_schema_and_experiment_validation(pilot: PilotInput) -> None:
    for changes in [
        {"evidence_kind": "official_aggregates"},
        {"source_hashes": {"x": "bad"}},
        {"schema_version": "m3-input/1"},
    ]:
        with pytest.raises(ValidationError):
            PilotInput.model_validate({**pilot.model_dump(), **changes})
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


def test_joint_audit_detects_sex_swap_with_unchanged_broad_margins(
    tmp_path: Path, pilot: PilotInput
) -> None:
    directory = tmp_path / "run"
    generate(pilot.calibration, 17, 6, directory)
    with duckdb.connect() as con:

        def broad_counts() -> list[tuple[object, ...]]:
            return con.execute(
                "SELECT CASE WHEN age<18 THEN 0 WHEN age<65 THEN 1 ELSE 2 END, sex, count(*) "
                "FROM read_parquet(?) GROUP BY 1,2 ORDER BY 1,2",
                [str(directory / "persons.parquet")],
            ).fetchall()

        before = broad_counts()
        rewrite_persons(
            directory,
            """UPDATE p SET sex=CASE sex WHEN 'M' THEN 'F' ELSE 'M' END
            WHERE person_id IN (SELECT min(person_id) FROM p WHERE age=30 AND sex='M'
            UNION ALL SELECT min(person_id) FROM p WHERE age=40 AND sex='F')""",
        )
        assert broad_counts() == before
    with pytest.raises(QualityError) as error:
        audit(directory, pilot, 6)
    assert error.value.report["checks"]["age_margins"]
    assert error.value.report["checks"]["sex_age_joint_counts"] is False


def test_historical_run_requires_recorded_implementation(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "descriptor": {
                    "algorithm": "constrained-reconstruction/1.0.0",
                    "audit": "parquet-independent-audit/1.0.1",
                }
            }
        )
    )
    before = (tmp_path / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="verify historical runs with their recorded"):
        verify_run(tmp_path)
    assert (tmp_path / "manifest.json").read_bytes() == before


def test_retry_identity_concurrency_and_cli(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment
) -> None:
    # Previous interrupted attempts are evidence, not retry scratch space to clean up.
    previous_attempt = tmp_path / "state" / "m3-attempt-interrupted" / "input.json"
    previous_attempt.parent.mkdir(parents=True)
    previous_attempt.write_bytes(b"preserved previous attempt")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_pilot(tmp_path, pilot, experiment), range(2)))
    assert results[0] == results[1]
    assert list((tmp_path / "state").glob("m3-attempt-*")) == [previous_attempt.parent]
    directory = results[0]
    before = {p: sha256_file(p) for p in directory.rglob("*") if p.is_file()}
    for _ in range(3):
        assert run_pilot(tmp_path, pilot, experiment) == directory
        assert list((tmp_path / "state").glob("m3-attempt-*")) == [previous_attempt.parent]
        assert previous_attempt.read_bytes() == b"preserved previous attempt"
    assert before == {p: sha256_file(p) for p in directory.rglob("*") if p.is_file()}
    manifest = verify_run(directory)
    assert manifest["public_release"] is False
    assert manifest["descriptor"]["input_sha256"] == sha256_file(directory / "input.json")
    result = CliRunner().invoke(app, ["verify-m3", "--run", str(directory)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["verified"] is True
    other = run_pilot(tmp_path, pilot, Experiment(seeds=[17, 19], large_household_sizes=[6, 8]))
    assert other != directory


def test_joint_changes_generation_and_preserves_previous_run(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment
) -> None:
    original = run_pilot(tmp_path, pilot, experiment)
    before = {p: sha256_file(p) for p in original.rglob("*") if p.is_file()}
    changed = pilot.model_dump()
    changed["calibration"]["male_by_age"][30] -= 2
    changed["calibration"]["male_by_age"][40] += 2
    alternate = run_pilot(tmp_path, PilotInput.model_validate(changed), experiment)
    assert original != alternate
    assert (original / "report.json").read_bytes() != (alternate / "report.json").read_bytes()
    assert before == {p: sha256_file(p) for p in original.rglob("*") if p.is_file()}
    for path in original.rglob("persons.parquet"):
        assert path.read_bytes() != (alternate / path.relative_to(original)).read_bytes()
    verify_run(original)
    verify_run(alternate)


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


@pytest.mark.parametrize(
    "damage", ["metric", "uncertainty", "replicates", "approval", "validation"]
)
def test_independent_recalculation_rejects_rehashed_report(
    tmp_path: Path, pilot: PilotInput, experiment: Experiment, damage: str
) -> None:
    directory = run_pilot(tmp_path, pilot, experiment)
    report_path = directory / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if damage == "metric":
        report["replicates"][0]["audit"]["calibration_joint"]["total_variation_distance"] = 1
    elif damage == "uncertainty":
        report["uncertainty"][0]["metrics"]["unassigned_adults"]["mean"] = 0
    elif damage == "replicates":
        report["replicates"].pop()
    elif damage == "validation":
        report["out_of_calibration_validation"] = "passed"
    else:
        report["public_release"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["report.json"] = sha256_file(report_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_run(directory)
