import csv
import io
import zipfile
from pathlib import Path

import pytest

from itadb.synthesis.national_inputs import household_partition, read_posas, read_profile


def test_missing_household_category_needs_exhaustive_total() -> None:
    rows = [
        {"REF_AREA": "900001", "NUM_MEMB": key, "OBS_VALUE": str(n)}
        for key, n in [("N1", 2), ("N2", 3), ("TOT", 5)]
    ]
    assert household_partition(iter(rows)) == ({"900001": [2, 3, 0, 0, 0, 0]}, 4)
    rows[-1]["OBS_VALUE"] = "6"
    with pytest.raises(ValueError, match="reconcile"):
        household_partition(iter(rows))
    with pytest.raises(ValueError, match="Duplicate"):
        household_partition(iter(rows + [rows[0]]))


@pytest.mark.parametrize(
    "damage", [None, "missing", "duplicate", "sex", "total", "suppressed", "title", "layout"]
)
def test_posas_explicit_zeros_and_reconciliation(tmp_path: Path, damage: str | None) -> None:
    columns = ["Codice comune", "Comune", "Età", "Totale maschi", "Totale femmine", "Totale"]
    rows = [["900001", "Fixture", a, 1, 2, 3] for a in range(101)]
    rows.append(["900001", "Fixture", 999, 101, 202, 303])
    if damage == "missing":
        rows.pop(0)
    elif damage == "duplicate":
        rows.append(rows[0])
    elif damage == "sex":
        rows[0][-1] = 4
    elif damage == "total":
        rows[-1][-3:] = [102, 201, 303]
    elif damage == "suppressed":
        rows[0][-3] = ".."
    text = io.StringIO(newline="")
    text.write('"Fixture inventata"\n')
    writer = csv.writer(text, delimiter=";")
    writer.writerow(columns)
    writer.writerows(rows)
    data = text.getvalue().encode("utf-8")
    path = tmp_path / "input.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fixture.csv", data)
        if damage == "layout":
            archive.writestr("unexpected.csv", data)
    profile = {
        "member": "fixture.csv",
        "uncompressed_bytes": len(data),
        "rows": len(rows),
        "title": '"Fixture inventata"' if damage != "title" else "Wrong reference",
        "columns": columns,
    }
    if damage:
        with pytest.raises(ValueError):
            read_posas(path, profile)
    else:
        counts, totals = read_posas(path, profile)
        assert counts["900001", "1"] == [1] * 101
        assert counts["900001", "2"] == [2] * 101
        assert totals == {"900001": 303}


@pytest.mark.parametrize(
    "value,status", [("", ""), ("..", ""), ("1.2", ""), ("2", "e"), ("-1", "")]
)
def test_sdmx_unknown_missing_or_estimated_rejected(
    tmp_path: Path, value: str, status: str
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(f"OBS_VALUE,OBS_STATUS\n{value},{status}\n", encoding="utf-8")
    profile = {"columns": ["OBS_VALUE", "OBS_STATUS"], "rows": 1, "domains": {"OBS_STATUS": [""]}}
    with pytest.raises(ValueError):
        list(read_profile(path, profile))
