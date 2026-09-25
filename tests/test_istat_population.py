import csv
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from itadb.cli import app
from itadb.pipeline.istat_population import check_population_sample, validate_population_sample
from itadb.pipeline.storage import archive_file, atomic_json
from itadb.pipeline.validate import QualityError

FIXTURES = Path("tests/fixtures")
CONTRACT = Path("contracts/istat-population-regions-v1.json")
RAW = FIXTURES / "istat-population-invented.csv"
STRUCTURE = FIXTURES / "istat-population-structure.xml"
DATAFLOW = FIXTURES / "istat-population-dataflow.xml"


def _rows() -> list[dict[str, str]]:
    with RAW.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(_rows()[0]))
        writer.writeheader()
        writer.writerows(rows)


def _inputs(root: Path, raw: Path = RAW) -> tuple[Path, Path, Path]:
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    key = "A." + "+".join(spec["territories"]) + ".JAN.9.TOTAL.99"
    base = "https://esploradati.istat.it/SDMXWS/rest"
    sources = [
        (
            raw,
            f"{base}/data/IT1,22_289_DF_DCIS_POPRES1_1,1.0/{key}?startPeriod=2024-01-01&endPeriod=2024-01-01",
        ),
        (STRUCTURE, f"{base}/datastructure/IT1/DCIS_POPRES1/1.0?references=all"),
        (DATAFLOW, f"{base}/dataflow/IT1/22_289_DF_DCIS_POPRES1_1/1.0?references=none"),
    ]
    manifests = []
    for source, url in sources:
        path, checksum = archive_file(source, root / "raw")
        manifest = path.parent / "acquisition-test.json"
        atomic_json(
            manifest,
            {
                "source": "istat",
                "url": url,
                "retrieved_at": "2026-09-22T23:34:58+00:00",
                "sha256": checksum,
                "bytes": path.stat().st_size,
            },
        )
        manifests.append(manifest)
    return manifests[0], manifests[1], manifests[2]


def test_validates_invented_counts_with_official_metadata_excerpt() -> None:
    report = validate_population_sample(RAW, STRUCTURE, DATAFLOW, CONTRACT)
    assert report["status"] == "validated_sample"
    assert report["published"] is False
    assert report["rows"] == 21
    assert report["reconciliation"] == {
        "regional_sum": 210000,
        "national_total": 210000,
        "difference": 0,
        "tolerance": 0,
    }
    assert all(report["checks"].values())
    assert report["upstream_last_update"] == "2026-03-31T08:03:43.724Z"
    assert report["upstream_published_at"] is None
    piemont = next(row for row in report["observations"] if row["territory_code"] == "ITC1")
    assert piemont["status"] == "unflagged_upstream"
    assert piemont["upstream_attributes"]["NOTE_REF_AREA"] == "FILTER__ITC1"


def test_zero_is_a_valid_count(tmp_path: Path) -> None:
    rows = _rows()
    for row in rows:
        row["OBS_VALUE"] = "0"
    raw = tmp_path / "zero.csv"
    _write_rows(raw, rows)
    report = validate_population_sample(raw, STRUCTURE, DATAFLOW, CONTRACT)
    assert report["reconciliation"]["national_total"] == 0


def test_rejects_extra_columns(tmp_path: Path) -> None:
    raw = tmp_path / "changed.csv"
    raw.write_text(RAW.read_text().replace("OBS_VALUE,", "EXTRA,OBS_VALUE,", 1))
    with pytest.raises(QualityError, match="exact_columns"):
        validate_population_sample(raw, STRUCTURE, DATAFLOW, CONTRACT)


def test_rejects_dtd_in_metadata(tmp_path: Path) -> None:
    structure = tmp_path / "entities.xml"
    structure.write_text('<!DOCTYPE x [<!ENTITY x "example">]><x/>')
    with pytest.raises(ValueError, match="DTD/entity"):
        validate_population_sample(RAW, structure, DATAFLOW, CONTRACT)


def test_rejects_a_flow_pointing_to_another_dsd(tmp_path: Path) -> None:
    dataflow = tmp_path / "changed.xml"
    dataflow.write_text(
        DATAFLOW.read_text(encoding="utf-8").replace('id="DCIS_POPRES1"', 'id="OTHER"'),
        encoding="utf-8",
    )
    with pytest.raises(QualityError, match="dataflow_dsd"):
        validate_population_sample(RAW, STRUCTURE, dataflow, CONTRACT)


@pytest.mark.parametrize(
    "field,value,gate",
    [
        ("TIME_PERIOD", "2025", "selected_slice"),
        ("FREQ", "M", "selected_slice"),
        ("SEX", "1", "selected_slice"),
        ("DATA_TYPE", "JAN_C", "selected_slice"),
        ("DATAFLOW", "IT1:OTHER(1.0)", "selected_slice"),
        ("REF_AREA", "ITD1", "territorial_coverage"),
        ("REF_AREA", "IT", "unique_key"),
        ("OBS_VALUE", "", "nonnegative_int64"),
        ("OBS_VALUE", "-1", "nonnegative_int64"),
        ("OBS_VALUE", "1.5", "nonnegative_int64"),
        ("OBS_VALUE", "NaN", "nonnegative_int64"),
        ("OBS_VALUE", str(2**63), "nonnegative_int64"),
        ("OBS_VALUE", "1001", "national_reconciliation"),
        ("OBS_STATUS", "P", "reviewed_flags"),
        ("OBS_STATUS", "E", "reviewed_flags"),
        ("OBS_STATUS", "C", "reviewed_flags"),
        ("UNIT_MULT", "3", "reviewed_units"),
        ("UNIT_MEAS", "EUR", "reviewed_units"),
        ("NOTE_REF_AREA", "UNREVIEWED", "reviewed_notes"),
        ("NOTE_DS", "NEW_NOTE", "reviewed_notes"),
    ],
)
def test_rejects_unreviewed_or_inconsistent_data(
    tmp_path: Path, field: str, value: str, gate: str
) -> None:
    rows = _rows()
    rows[1][field] = value
    raw = tmp_path / "invalid.csv"
    _write_rows(raw, rows)
    with pytest.raises(QualityError) as error:
        validate_population_sample(raw, STRUCTURE, DATAFLOW, CONTRACT)
    assert error.value.report["checks"][gate] is False


@pytest.mark.parametrize("count,gate", [(0, "row_count"), (20, "row_count"), (22, "bounded_rows")])
def test_rejects_incomplete_and_excess_responses(tmp_path: Path, count: int, gate: str) -> None:
    raw = tmp_path / "invalid.csv"
    _write_rows(raw, (_rows() + [_rows()[0]])[:count])
    with pytest.raises(QualityError) as error:
        validate_population_sample(raw, STRUCTURE, DATAFLOW, CONTRACT)
    assert error.value.report["checks"][gate] is False


@pytest.mark.parametrize(
    "before,after,gate",
    [
        ('position="1"', 'position="8"', "dimension_order"),
        ('id="DCIS_POPRES1"', 'id="OTHER"', "dsd_identity"),
        (
            '<common:Name xml:lang="it">Piemonte</common:Name>',
            '<common:Name xml:lang="it">Changed</common:Name>',
            "territorial_labels",
        ),
        ('id="CL_FREQ" version="1.0"', 'id="CL_FREQ" version="2.0"', "enumeration_FREQ"),
        (">annuale</common:Name>", ">mensile</common:Name>", "reviewed_code_meanings"),
    ],
)
def test_rejects_changed_dsd(tmp_path: Path, before: str, after: str, gate: str) -> None:
    text = STRUCTURE.read_text(encoding="utf-8")
    assert before in text
    structure = tmp_path / "changed.xml"
    structure.write_text(text.replace(before, after, 1), encoding="utf-8")
    with pytest.raises(QualityError) as error:
        validate_population_sample(RAW, structure, DATAFLOW, CONTRACT)
    assert error.value.report["checks"][gate] is False


def test_evidence_is_repeatable_and_preserves_provenance(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    report_path = check_population_sample(tmp_path, *inputs, CONTRACT)
    original = report_path.read_bytes()
    original_time = report_path.stat().st_mtime_ns
    assert check_population_sample(tmp_path, *inputs, CONTRACT) == report_path
    assert report_path.read_bytes() == original
    assert report_path.stat().st_mtime_ns == original_time
    report = json.loads(original)
    assert report["evidence"]["data"]["retrieved_at"] == "2026-09-22T23:34:58+00:00"
    assert (
        tmp_path / report["evidence"]["structure"]["path"]
    ).read_bytes() == STRUCTURE.read_bytes()
    assert report["published"] is False


def test_failure_is_quarantined_without_success_report(tmp_path: Path) -> None:
    rows = _rows()
    rows[1]["OBS_VALUE"] = "1"
    raw = tmp_path / "invalid.csv"
    _write_rows(raw, rows)
    inputs = _inputs(tmp_path, raw)
    with pytest.raises(QualityError):
        check_population_sample(tmp_path, *inputs, CONTRACT)
    assert not list((tmp_path / "reports").glob("*.json"))
    failed = json.loads(next((tmp_path / "quarantine").glob("*.json")).read_text())
    assert failed["published"] is False
    assert failed["report"]["checks"]["national_reconciliation"] is False
    assert (inputs[0].parent / "payload").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "0" * 64),
        ("source", "eurostat"),
        ("url", "https://example.org/data"),
        ("bytes", 1),
        ("retrieved_at", "2026-09-23"),
    ],
)
def test_rejects_mismatched_provenance(tmp_path: Path, field: str, value: Any) -> None:
    inputs = _inputs(tmp_path)
    manifest = json.loads(inputs[0].read_text())
    manifest[field] = value
    atomic_json(inputs[0], manifest)
    with pytest.raises(ValueError):
        check_population_sample(tmp_path, *inputs, CONTRACT)
    assert not list((tmp_path / "reports").glob("*.json"))
    assert len(list((tmp_path / "quarantine").glob("*.json"))) == 1


def test_refuses_overwriting_modified_evidence(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    output = check_population_sample(tmp_path, *inputs, CONTRACT)
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="modified"):
        check_population_sample(tmp_path, *inputs, CONTRACT)
    assert output.read_text() == "{}"


def test_cli_checks_sample_without_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    monkeypatch.setenv("ITADB_DATA_DIR", str(tmp_path))
    result = CliRunner().invoke(
        app,
        [
            "check-istat-population",
            "--acquisition",
            str(inputs[0]),
            "--structure",
            str(inputs[1]),
            "--dataflow",
            str(inputs[2]),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["published"] is False
