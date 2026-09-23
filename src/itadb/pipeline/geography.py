"""Read the reviewed ISTAT administrative shapefiles without extracting ZIP paths."""

import io
import json
import zipfile
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import shapefile

from itadb.pipeline.coverage import Territory


def shape_records(path: Path) -> Iterator[tuple[str, dict[str, Any], Any]]:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 200 or sum(e.file_size for e in entries) > 150_000_000:
            raise ValueError("Geography archive exceeds unpacked budget")
        layers: set[str] = set()
        for entry in entries:
            if not entry.filename.endswith(".shp"):
                continue
            filename = entry.filename.rsplit("/", 1)[-1]
            level = next(
                (
                    value
                    for prefix, value in (
                        ("Reg", "region"),
                        ("ProvCM", "province"),
                        ("Com", "municipality"),
                    )
                    if filename.startswith(prefix)
                ),
                None,
            )
            if level is None:
                continue
            if level in layers:
                raise ValueError("Duplicate geographic layer")
            layers.add(level)
            base = entry.filename[:-4]
            projection = archive.read(base + ".prj").decode("utf-8").strip()
            expected = (
                'PROJCS["WGS_1984_UTM_Zone_32N"',
                'DATUM["D_WGS_1984"',
                'PARAMETER["Central_Meridian",9.0]',
                'PARAMETER["Scale_Factor",0.9996]',
                'PARAMETER["False_Easting",500000.0]',
                'PARAMETER["False_Northing",0.0]',
                'UNIT["Meter",1.0]',
            )
            if not all(part in projection for part in expected):
                raise ValueError("Unreviewed coordinate reference system")
            with shapefile.Reader(
                shp=io.BytesIO(archive.read(entry.filename)),
                dbf=io.BytesIO(archive.read(base + ".dbf")),
                encoding="utf-8",
            ) as reader:
                if len(reader) > 10_000:
                    raise ValueError("Too many territories in one layer")
                for item in reader.iterShapeRecords():
                    yield level, item.record.as_dict(), item.shape
        if layers != {"region", "province", "municipality"}:
            raise ValueError("Incomplete geographic layers")


def admin_code(level: str, row: dict[str, Any]) -> str:
    if level == "region":
        return f"{int(row['COD_REG']):02d}"
    if level == "province":
        return f"{int(row['COD_UTS']):03d}"
    code = str(row["PRO_COM_T"])
    if len(code) != 6 or not code.isdigit() or int(code) != int(row["PRO_COM"]):
        raise ValueError("Invalid municipality code")
    return code


def territory_key(snapshot: date, code: str) -> str:
    return f"{snapshot}:{code}"


def read_territories(
    path: Path, snapshot: date, checksum: str
) -> tuple[list[Territory], dict[str, dict[str, int]]]:
    scheme = f"ISTAT_ADMIN:{snapshot}:{checksum}"
    common: dict[str, Any] = {
        "scheme": scheme,
        "valid_from": snapshot,
        "valid_to": snapshot + timedelta(days=1),
        "snapshot": snapshot,
    }
    result = [
        Territory(
            key=territory_key(snapshot, "IT"),
            code="IT",
            name="Italia",
            level="country",
            parent_key=None,
            **common,
        )
    ]
    census: dict[str, dict[str, int]] = {}
    for level, row, _ in shape_records(path):
        code = admin_code(level, row)
        if level == "region":
            parent, name = "IT", row["DEN_REG"]
        elif level == "province":
            parent, name = f"{int(row['COD_REG']):02d}", row["DEN_UTS"]
        else:
            parent, name = f"{int(row['COD_UTS']):03d}", row["COMUNE"]
        key = territory_key(snapshot, code)
        result.append(
            Territory(
                key=key,
                code=code,
                name=name,
                level=cast(Literal["country", "region", "province", "municipality"], level),
                parent_key=territory_key(snapshot, parent),
                **common,
            )
        )
        if "POP21" in row and "FAM21" in row:
            if any(
                row[f] is None or row[f] < 0 or row[f] != int(row[f]) for f in ("POP21", "FAM21")
            ):
                raise ValueError("Invalid census counts in geography")
            census[key] = {"population": int(row["POP21"]), "households": int(row["FAM21"])}
    return result, census


def boundary_rows(path: Path, snapshot: date, source_format: str) -> Iterator[tuple[str, str]]:
    if source_format == "fixture_geojson":
        if path.stat().st_size > 1_000_000:
            raise ValueError("Fixture geometry too large")
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            yield (
                territory_key(snapshot, feature["properties"]["code"]),
                json.dumps(feature["geometry"]),
            )
        return
    for level, row, shape in shape_records(path):
        yield territory_key(snapshot, admin_code(level, row)), json.dumps(shape.__geo_interface__)
