import csv
from pathlib import Path

import duckdb
import pytest

from itadb.pipeline.storage import archive_file
from itadb.pipeline.validate import QualityError, normalize_demo

FIXTURE = Path("tests/fixtures/population-demo.csv")
CONTRACT = Path("contracts/population-demo-v1.json")


def test_valid_fixture_preserves_values_and_types(tmp_path: Path) -> None:
    output = tmp_path / "data.parquet"
    report = normalize_demo(FIXTURE, output, CONTRACT)
    assert report["rows"] == 3
    assert all(report["checks"].values())
    with duckdb.connect() as db:
        assert db.execute(
            "SELECT sum(population) FROM read_parquet(?)", [str(output)]
        ).fetchone() == (4350,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("population", "-1"),
        ("population", "NaN"),
        ("population", "1.5"),
        ("population", "9223372036854775808"),
        ("period", "2025-02-30"),
        ("period", "2024-01-01"),
        ("territory_code", "001001"),
        ("territory_name", ""),
        ("population", ""),
    ],
)
def test_invalid_data_never_becomes_curated(tmp_path: Path, field: str, value: str) -> None:
    with FIXTURE.open() as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fields = reader.fieldnames
    assert fields is not None
    rows[0][field] = value
    source = tmp_path / "bad.csv"
    with source.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    output = tmp_path / "output.parquet"
    with pytest.raises(QualityError):
        normalize_demo(source, output, CONTRACT)
    assert not output.exists()


def test_duplicate_observations_rejected(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.csv"
    source.write_text(FIXTURE.read_text() + "DEMO001,Territorio Alfa,2025-01-01,1200\n")
    with pytest.raises(QualityError, match="unique_key"):
        normalize_demo(source, tmp_path / "output.parquet", CONTRACT)


def test_archive_is_content_addressed_and_detects_corruption(tmp_path: Path) -> None:
    path, digest = archive_file(FIXTURE, tmp_path)
    assert archive_file(FIXTURE, tmp_path) == (path, digest)
    path.write_bytes(b"corruption")
    with pytest.raises(ValueError, match="modified"):
        archive_file(FIXTURE, tmp_path)
