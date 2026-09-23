import json
from pathlib import Path

import duckdb
import pytest

from itadb.pipeline.storage import sha256_file
from itadb.pipeline.validate import QualityError
from itadb.synthesis.national_audit import audit_batch
from itadb.synthesis.national_generate import generate_batch
from itadb.synthesis.national_models import (
    Municipality,
    NationalInput,
    ResourceBudget,
    batches,
    territorial_seed,
)
from itadb.synthesis.national_runner import run_national, verify_national


@pytest.fixture
def national() -> NationalInput:
    # Entirely invented aggregate constraints, not an observed Italian population.
    municipalities = []
    for code, province, region in [
        ("900001", "900", "90"),
        ("900002", "900", "90"),
        ("901001", "901", "91"),
    ]:
        male, female = [0] * 101, [0] * 101
        for age, n in [(0, 2), (17, 3), (18, 4), (40, 15), (99, 2), (100, 1)]:
            male[age] = n
            female[age] = n + 1
        municipalities.append(
            Municipality(
                code=code,
                province=province,
                region=region,
                male=male,
                female=female,
                households=[5, 4, 4, 3, 1, 1],
            )
        )
    return NationalInput(
        evidence_kind="invented_load_fixture",
        population_reference="2025-01-01",
        household_reference="2024-12-31",
        geography_reference="2025-01-01",
        municipalities=municipalities,
        source_hashes={"fixture": "0" * 64},
        attribution="Invented CC0",
    )


def test_multimunicipal_constraints_and_batch_order(
    tmp_path: Path, national: NationalInput
) -> None:
    first = run_national(tmp_path / "first", national)
    second = run_national(tmp_path / "second", national, reverse_order=True)
    assert first.name == second.name
    for path in first.rglob("*.parquet"):
        assert sha256_file(path) == sha256_file(second / path.relative_to(first))
    verify_national(first)
    report = json.loads((first / "report.json").read_text())
    assert report["calibration"]["cells"] == 606
    assert report["calibration"]["max_absolute_error"] == 0
    assert report["reference_evidence_kind"] == "invented_load_fixture"
    assert report["disclosure"]["persons_in_cells_below_5"] > 0
    assert not json.loads((first / "distribution/aggregates.json").read_text())["eligible"]


def test_recovery_preserves_checkpoints_and_retry(tmp_path: Path, national: NationalInput) -> None:
    with pytest.raises(InterruptedError):
        run_national(tmp_path, national, stop_after_batches=1)
    assert not list((tmp_path / "curated").rglob("manifest.json"))
    checkpoint = next((tmp_path / "state").rglob("checkpoint.json"))
    old = checkpoint.read_bytes()
    result = run_national(tmp_path, national)
    assert (result / "batch-0000/checkpoint.json").read_bytes() == old
    before = {p.relative_to(result): sha256_file(p) for p in result.rglob("*") if p.is_file()}
    assert run_national(tmp_path, national) == result
    assert before == {
        p.relative_to(result): sha256_file(p) for p in result.rglob("*") if p.is_file()
    }


def test_feasibility_and_seeds(national: NationalInput) -> None:
    assert territorial_seed("900001") != territorial_seed("900002")
    assert territorial_seed("900001") == territorial_seed("900001")
    broken = national.model_copy(deep=True)
    broken.municipalities[0].households = [0, 0, 0, 0, 0, 100]
    with pytest.raises(ValueError, match="capacity"):
        batches(broken, ResourceBudget())


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE p SET person_id=person_id+1 WHERE person_id=1",
        "UPDATE p SET municipality='901001' WHERE municipality='900001'",
        "UPDATE p SET birth_year=2024 WHERE birth_year_upper_bound IS NOT NULL",
        "UPDATE p SET sex='F' WHERE sex='M'",
        "UPDATE p SET household_id=NULL WHERE birth_year=2024",
        "UPDATE p SET data_kind='observed'",
    ],
)
def test_audit_rejects_corruption(tmp_path: Path, national: NationalInput, sql: str) -> None:
    group = batches(national, ResourceBudget())[0]
    folder = tmp_path / "batch"
    generate_batch(
        group, national.population_reference, folder, 0, 0, ResourceBudget(), lambda _: None
    )
    with duckdb.connect() as con:
        con.execute("CREATE TABLE p AS FROM read_parquet(?)", [str(folder / "persons.parquet")])
        con.execute(sql)
        con.execute("COPY p TO ? (FORMAT PARQUET)", [str(folder / "persons.parquet")])
    with pytest.raises(QualityError):
        audit_batch(folder, group, national.population_reference, 0, 0, ResourceBudget())


def test_corrupt_checkpoint_not_repaired(tmp_path: Path, national: NationalInput) -> None:
    with pytest.raises(InterruptedError):
        run_national(tmp_path, national, stop_after_batches=1)
    path = next((tmp_path / "state").rglob("persons.parquet"))
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="checksum"):
        run_national(tmp_path, national)
    assert path.read_bytes() == b"damaged"
    assert not list((tmp_path / "curated").rglob("manifest.json"))


@pytest.mark.parametrize("damage", ["approval", "package", "report", "extra", "checkpoint"])
def test_rehashed_tampering_rejected(tmp_path: Path, national: NationalInput, damage: str) -> None:
    directory = run_national(tmp_path, national)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if damage == "approval":
        manifest["public_release"] = True
    elif damage == "extra":
        (directory / "unknown.csv").write_text("unexpected")
        manifest["files"]["unknown.csv"] = sha256_file(directory / "unknown.csv")
    else:
        name = {
            "package": "distribution/aggregates.json",
            "report": "report.json",
            "checkpoint": "batch-0000/checkpoint.json",
        }[damage]
        path = directory / name
        data = json.loads(path.read_text(encoding="utf-8"))
        if damage == "package":
            data["cells"] = [{"persons": 1, "municipality": "900001"}]
        elif damage == "report":
            data["out_of_calibration_validation"] = "passed"
        else:
            data["batch"] = 45
        path.write_text(json.dumps(data), encoding="utf-8")
        manifest["files"][name] = sha256_file(path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_national(directory)


def test_resource_limit_prevents_completion(
    tmp_path: Path, national: NationalInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("itadb.synthesis.national_runtime.peak_rss_bytes", lambda: 9 * 2**30)
    with pytest.raises(RuntimeError, match="RSS budget"):
        run_national(tmp_path, national)
    assert not list((tmp_path / "curated").rglob("manifest.json"))
