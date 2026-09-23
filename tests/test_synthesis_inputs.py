"""Tiny invented SDMX responses; no network and no official data copied into tests."""

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from itadb.connectors.m2 import acquire_inventory
from itadb.pipeline.storage import archive_file, atomic_json
from itadb.synthesis.inputs import prepare_inputs
from itadb.synthesis.models import PilotInput


def inventory(tmp_path: Path, problem: str = "") -> tuple[Path, Path]:
    spec = json.loads(Path("contracts/istat-m3-valle-aosta-v1.json").read_text(encoding="utf-8"))
    fixture = PilotInput.model_validate_json(Path("tests/fixtures/m3-invented.json").read_bytes())
    c = fixture.calibration
    spec.update(expected_population=40, expected_households=12)
    paths = {}
    for name in spec["sources"]:
        source = tmp_path / f"{name}.source"
        if name in {"population", "households"}:
            profile = spec["profiles"][name]
            rows = []
            if name == "population":
                for sex in ["1", "2", "9"]:
                    for age in [*range(101), None]:
                        row = {k: values[0] for k, values in profile["domains"].items()}
                        male = c.male_by_age[age] if age is not None else sum(c.male_by_age)
                        total = c.age_counts[age] if age is not None else 40
                        row.update(
                            SEX=sex,
                            AGE="TOTAL"
                            if age is None
                            else ("Y_GE100" if age == 100 else f"Y{age}"),
                            OBS_VALUE=str({"1": male, "2": total - male, "9": total}[sex]),
                        )
                        rows.append(row)
                if problem == "duplicate":
                    rows[1] = dict(rows[0])
                elif problem == "sum":
                    rows[0]["OBS_VALUE"] = "1"
                elif problem == "period":
                    rows[0]["TIME_PERIOD"] = "2024"
                elif problem == "status":
                    rows[0]["OBS_STATUS"] = "E"
                elif problem == "negative":
                    rows[0]["OBS_VALUE"] = "-1"
                elif problem == "missing":
                    rows.pop()
            else:
                for category, count in zip(
                    ["N1", "N2", "N3", "N4", "N5", "N6_GE", "TOT"],
                    [*c.household_counts, 12],
                    strict=True,
                ):
                    row = {k: values[0] for k, values in profile["domains"].items()}
                    row.update(REF_AREA="ITC2", NUM_MEMB=category, OBS_VALUE=str(count))
                    rows.append(row)
                profile["expected_rows"] = 7
                if problem == "household_sum":
                    rows[-1]["OBS_VALUE"] = "13"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=profile["columns"])
                writer.writeheader()
                writer.writerows(rows)
        else:
            source.write_text("invented metadata fixture", encoding="utf-8")
        payload, checksum = archive_file(source, tmp_path / "raw")
        expected = {
            "sha256": checksum,
            "url": spec["sources"][name]["url"],
            "bytes": payload.stat().st_size,
        }
        spec["sources"][name] = expected
        manifest = payload.parent / f"acquisition-{name}.json"
        atomic_json(manifest, {**expected, "retrieved_at": "2026-09-23T12:00:00+00:00"})
        paths[name] = str(manifest)
    contract = tmp_path / "contract.json"
    atomic_json(contract, spec)
    result = tmp_path / "inventory.json"
    atomic_json(result, paths)
    return result, contract


@pytest.fixture
def census(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "itadb.synthesis.inputs.read_territories",
        lambda *args: (
            [SimpleNamespace(level="region", code="02", key="region")],
            {"region": {"population": 40, "households": 12}},
        ),
    )


def test_offline_adapter_reconciles_and_archives(
    tmp_path: Path, census: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, contract = inventory(tmp_path)
    result = prepare_inputs(tmp_path, inputs, contract)
    assert sum(result.calibration.age_counts) == 40
    assert (
        result.calibration.male_by_age
        == PilotInput.model_validate_json(
            Path("tests/fixtures/m3-invented.json").read_bytes()
        ).calibration.male_by_age
    )
    assert sum(result.calibration.household_counts) == 12
    assert len(result.source_hashes) == 17
    monkeypatch.setattr(
        "itadb.connectors.m2.fetch_static",
        lambda *args, **kwargs: pytest.fail("No network on cache hit"),
    )
    cached = acquire_inventory(tmp_path, contract, "istat-m3-valle-aosta", "m3")
    assert prepare_inputs(tmp_path, cached, contract) == result


@pytest.mark.parametrize(
    "problem", ["duplicate", "sum", "period", "status", "negative", "missing", "household_sum"]
)
def test_adapter_refuses_bad_evidence(tmp_path: Path, census: None, problem: str) -> None:
    inputs, contract = inventory(tmp_path, problem)
    with pytest.raises(ValueError):
        prepare_inputs(tmp_path, inputs, contract)
    assert list((tmp_path / "quarantine").glob("m3-input-*.json"))


@pytest.mark.parametrize("problem", ["hash", "timestamp", "inventory", "census", "contract"])
def test_adapter_refuses_provenance_and_vintage_errors(
    tmp_path: Path, census: None, problem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, contract = inventory(tmp_path)
    paths = json.loads(inputs.read_text())
    if problem == "hash":
        (Path(paths["population"]).parent / "payload").write_text("corrupt")
    elif problem == "timestamp":
        path = Path(paths["population"])
        manifest = json.loads(path.read_text())
        manifest["retrieved_at"] = "2026-09-23T12:00:00"
        atomic_json(path, manifest)
    elif problem == "inventory":
        paths.pop("license")
        atomic_json(inputs, paths)
    elif problem == "census":
        monkeypatch.setattr(
            "itadb.synthesis.inputs.read_territories",
            lambda *args: (
                [SimpleNamespace(level="region", code="02", key="region")],
                {"region": {"population": 41, "households": 12}},
            ),
        )
    else:
        spec = json.loads(contract.read_text(encoding="utf-8"))
        spec["version"] = "2.0.0"
        atomic_json(contract, spec)
    with pytest.raises(ValueError):
        prepare_inputs(tmp_path, inputs, contract)
    assert list((tmp_path / "quarantine").glob("m3-input-*.json"))
