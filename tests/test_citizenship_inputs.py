import csv
import io
import zipfile
from pathlib import Path
from typing import Any

import pytest

from itadb.synthesis.citizenship_inputs import read_rcs, read_str, reconcile_parents
from itadb.synthesis.national_models import Municipality, NationalInput


def source(
    path: Path, columns: list[str], rows: list[list[Any]], title: str | None = None
) -> dict[str, Any]:
    stream = io.StringIO(newline="")
    if title:
        stream.write(title + "\n")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(columns)
    writer.writerows(rows)
    data = stream.getvalue().encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fixture.csv", data)
    profile: dict[str, Any] = {
        "member": "fixture.csv",
        "uncompressed_bytes": len(data),
        "columns": columns,
        "rows": len(rows),
    }
    if title:
        profile["title"] = title
    return profile


@pytest.mark.parametrize(
    "damage",
    [None, "missing", "duplicate", "total", "suppressed", "negative", "age", "title", "layout"],
)
def test_str_admission(tmp_path: Path, damage: str | None) -> None:
    rows: list[list[Any]] = [["900001", "Inventato", a, 1, 2] for a in range(101)]
    rows.append(["900001", "Inventato", 999, 101, 202])
    if damage == "missing":
        rows.pop(0)
    elif damage == "duplicate":
        rows.append(rows[0])
    elif damage == "total":
        rows[-1][-1] = 203
    elif damage == "suppressed":
        rows[0][-1] = ".."
    elif damage == "negative":
        rows[0][-1] = -1
    elif damage == "age":
        rows[0][2] = 105
    path = tmp_path / "str.zip"
    profile = source(
        path, ["Codice comune", "Comune", "Età", "Maschi", "Femmine"], rows, '"Fixture inventata"'
    )
    profile["code_column"] = "Codice comune"
    if damage == "title":
        profile["title"] = '"Wrong date"'
    if damage == "layout":
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("extra.csv", "bad")
    if damage:
        with pytest.raises(ValueError):
            read_str(path, profile)
    else:
        assert read_str(path, profile) == {"900001": [[1] * 101, [2] * 101]}


@pytest.mark.parametrize(
    "damage", [None, "year", "label", "duplicate", "total", "missing", "negative", "unknown"]
)
def test_rcs_admission(tmp_path: Path, damage: str | None) -> None:
    columns = [
        "Anno",
        "Codice Istat",
        "Denominazione",
        "Codice stato di cittadinanza",
        "Stato di cittadinanza",
        "Zona",
        "Continente",
        "Maschi",
        "Femmine",
        "Totale",
    ]
    row: list[Any] = [2025, "900001", "Inventato", "100", "Italia", "", "", 3, 4, 7]
    if damage == "year":
        row[0] = 2026
    elif damage == "label":
        row[4] = "Wrong"
    elif damage == "total":
        row[-1] = 8
    elif damage == "missing":
        row[-2] = ""
    elif damage == "negative":
        row[-2] = -1
    elif damage == "unknown":
        row[3] = "777"
    rows = [row, row] if damage == "duplicate" else [row]
    path = tmp_path / "rcs.zip"
    profile = source(path, columns, rows)
    profile["citizenships"] = {"100": "Italia"}
    if damage:
        with pytest.raises(ValueError):
            read_rcs(path, profile, "2025")
    else:
        assert read_rcs(path, profile, "2025") == {"900001": {"100": [3, 4]}}


@pytest.mark.parametrize("damage", [None, "parent", "extra", "missing"])
def test_parent_reconciliation(tmp_path: Path, damage: str | None) -> None:
    # Invented counts under official-shaped codes solely for hierarchy validation.
    m = Municipality(
        code="001001",
        province="201",
        region="01",
        male=[1] * 101,
        female=[2] * 101,
        households=[1, 0, 0, 0, 0, 0],
    )
    base = NationalInput(
        evidence_kind="official_aggregates",
        population_reference="2025-01-01",
        household_reference="2024-12-31",
        geography_reference="2025-01-01",
        municipalities=[m],
        source_hashes={"fixture": "0" * 64},
        attribution="Invented test fixture, not observed data",
    )
    rcs = {area: {"100": [100, 200], "201": [1, 2]} for area in ["001001", "001", "01", "1", "IT"]}
    if damage == "parent":
        rcs["IT"]["201"][0] = 2
    elif damage == "extra":
        rcs["02"] = {"100": [1, 2]}
    elif damage == "missing":
        del rcs["001"]
    if damage:
        with pytest.raises(ValueError):
            reconcile_parents(rcs, base, {"201": "001"})
    else:
        reconcile_parents(rcs, base, {"201": "001"})
