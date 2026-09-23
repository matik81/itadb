"""Offline admission of pinned municipal ISTAT counts with exact parent reconciliation."""

import csv
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from itadb.pipeline.geography import read_territories, shape_records
from itadb.pipeline.storage import archive_file, atomic_json
from itadb.synthesis.national_models import Municipality, NationalInput

REGIONS = dict(
    enumerate(
        [
            "ITC1",
            "ITC2",
            "ITC4",
            "ITDA",
            "ITD3",
            "ITD4",
            "ITC3",
            "ITD5",
            "ITE1",
            "ITE2",
            "ITE3",
            "ITE4",
            "ITF1",
            "ITF2",
            "ITF3",
            "ITF4",
            "ITF5",
            "ITF6",
            "ITG1",
            "ITG2",
        ],
        1,
    )
)
AGES = [f"Y{age}" for age in range(100)] + ["Y_GE100"]
SIZES = ["N1", "N2", "N3", "N4", "N5", "N6_GE"]


def read_posas(
    path: Path, profile: dict[str, Any]
) -> tuple[dict[tuple[str, str], list[int]], dict[str, int]]:
    cells: dict[str, dict[int, tuple[int, int, int]]] = {}
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if (
            len(entries) != 1
            or entries[0].filename != profile["member"]
            or entries[0].file_size != profile["uncompressed_bytes"]
            or entries[0].file_size > 60_000_000
        ):
            raise ValueError("Unexpected POSAS archive layout or expansion budget")
        with archive.open(entries[0]) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            if stream.readline().strip() != profile["title"]:
                raise ValueError("Unexpected POSAS reference title")
            reader = csv.DictReader(stream, delimiter=";")
            if reader.fieldnames != profile["columns"]:
                raise ValueError("Unexpected POSAS columns")
            count = 0
            for row in reader:
                if None in row or None in row.values():
                    raise ValueError("Malformed POSAS row")
                values = [row[k] for k in ["Età", "Totale maschi", "Totale femmine", "Totale"]]
                if any(not v.isascii() or not v.isdigit() for v in values):
                    raise ValueError("POSAS age and sex totals require observed integers")
                age, male, female, total = map(int, values)
                area = cells.setdefault(row[profile.get("code_column", "Codice comune")], {})
                if age not in [*range(101), 999] or age in area or male + female != total:
                    raise ValueError("Duplicate age, invalid domain or sex reconciliation failed")
                area[age] = (male, female, total)
                count += 1
            if count != profile["rows"]:
                raise ValueError("Unexpected POSAS row count")
    counts: dict[tuple[str, str], list[int]] = {}
    totals = {}
    for code, ages in cells.items():
        if set(ages) != {*range(101), 999}:
            raise ValueError("POSAS requires all ages including explicit zeros")
        for index, sex in enumerate(["1", "2", "9"]):
            age_counts = [ages[age][index] for age in range(101)]
            if sum(age_counts) != ages[999][index]:
                raise ValueError("POSAS age totals do not reconcile")
            if sex != "9":
                counts[code, sex] = age_counts
        totals[code] = ages[999][2]
    return counts, totals


def read_profile(path: Path, profile: dict[str, Any]) -> Iterator[dict[str, str]]:
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != profile["columns"]:
            raise ValueError("Unexpected SDMX columns")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError("Malformed SDMX row")
            if any(row[key] not in domain for key, domain in profile["domains"].items()):
                raise ValueError("Unreviewed dimension, note, status or unit")
            if not row["OBS_VALUE"].isascii() or not row["OBS_VALUE"].isdigit():
                raise ValueError("Only observed nonnegative integer counts are admitted")
            count += 1
            yield row
    if count != profile["rows"]:
        raise ValueError("Unexpected source row count")


def household_partition(rows: Iterator[dict[str, str]]) -> tuple[dict[str, list[int]], int]:
    """Missing categories imply zero only after exact exhaustive-total reconciliation."""
    values: dict[str, dict[str, int]] = {}
    for row in rows:
        area = values.setdefault(row["REF_AREA"], {})
        key = row["NUM_MEMB"]
        if key not in [*SIZES, "TOT"] or key in area:
            raise ValueError("Duplicate/unreviewed household category")
        area[key] = int(row["OBS_VALUE"])
    result = {}
    derived_zeros = 0
    for code, categories in values.items():
        if (
            "TOT" not in categories
            or sum(v for k, v in categories.items() if k != "TOT") != categories["TOT"]
        ):
            raise ValueError(f"{code}: household categories do not reconcile")
        derived_zeros += len(set(SIZES) - set(categories))
        result[code] = [categories.get(k, 0) for k in SIZES]
    return result, derived_zeros


def prepare_national_inputs(root: Path, inventory: Path, contract: Path) -> NationalInput:
    try:
        return _prepare(root, inventory, contract)
    except Exception as error:
        atomic_json(
            root / "quarantine" / f"m4-input-{uuid4().hex}.json",
            {
                "published": False,
                "error_code": type(error).__name__,
            },
        )
        raise


def _prepare(root: Path, inventory: Path, contract: Path) -> NationalInput:
    archived, digest = archive_file(contract, root / "raw")
    spec = json.loads(archived.read_text(encoding="utf-8"))
    if spec["name"] != "istat-m4-national" or spec["version"] != "1.0.0":
        raise ValueError("Unsupported M4 source contract")
    paths = json.loads(inventory.read_text(encoding="utf-8"))
    if set(paths) != set(spec["sources"]):
        raise ValueError("Inventory differs from the reviewed source contract")
    originals: dict[str, Path] = {}
    hashes = {"contract": digest}
    for name, expected in spec["sources"].items():
        print(f"Originale M4: {name}", flush=True)
        path = Path(paths[name])
        manifest_path, manifest_digest = archive_file(path, root / "raw")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(manifest.get(k) != expected[k] for k in ("sha256", "bytes", "url")):
            raise ValueError(f"Unreviewed source manifest: {name}")
        if datetime.fromisoformat(manifest["retrieved_at"]).tzinfo is None:
            raise ValueError("Acquisition timestamp requires timezone")
        original, payload_digest = archive_file(path.parent / "payload", root / "raw")
        if payload_digest != expected["sha256"] or original.stat().st_size != expected["bytes"]:
            raise ValueError(f"Corrupt original: {name}")
        originals[name] = original
        hashes[name] = payload_digest
        hashes[name + "_manifest"] = manifest_digest
    territories, _ = read_territories(
        originals["geography"],
        date.fromisoformat(spec["population_reference"]),
        hashes["geography"],
    )
    levels = dict(Counter(t.level for t in territories))
    if levels != spec["geography_counts"]:
        raise ValueError("Unexpected geographic coverage")
    by_key = {t.key: t for t in territories}
    if len(by_key) != len(territories):
        raise ValueError("Duplicate territory")
    for t in territories:
        if t.parent_key is not None:
            expected_level = {
                "region": "country",
                "province": "region",
                "municipality": "province",
            }[t.level]
            if t.parent_key not in by_key or by_key[t.parent_key].level != expected_level:
                raise ValueError("Invalid geographic hierarchy")
    municipalities = {t.code: t for t in territories if t.level == "municipality"}
    household, zeros = household_partition(
        read_profile(originals["households"], spec["profiles"]["households"])
    )
    if {c for c in household if len(c) == 6 and c.isdigit()} != set(municipalities):
        raise ValueError("Household municipality coverage differs from the snapshot")
    counts, totals = read_posas(originals["population_zip"], spec["posas"])
    if set(totals) != set(municipalities):
        raise ValueError("POSAS municipality coverage differs from the snapshot")
    result = []
    for code, territory in sorted(municipalities.items()):
        if sum(counts[code, "1"]) + sum(counts[code, "2"]) != totals[code]:
            raise ValueError("Municipal sex reconciliation failed")
        assert territory.parent_key is not None
        province = by_key[territory.parent_key]
        assert province.parent_key is not None
        region = by_key[province.parent_key]
        result.append(
            Municipality(
                code=code,
                province=province.code,
                region=region.code,
                male=counts[code, "1"],
                female=counts[code, "2"],
                households=household[code],
            )
        )
    # Reconcile two official coding systems through their municipal membership,
    # never by territory names or by assuming UTS codes equal province codes.
    namespace = {"s": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"}
    tree = ET.parse(originals["households_structure"])
    code_parents = {
        item.attrib["id"]: parent.attrib["id"]
        for item in tree.findall(".//s:Codelist[@id='CL_ITTER107']/s:Code", namespace)
        if (parent := item.find("s:Parent/Ref", namespace)) is not None
    }
    province_codes = {
        f"{int(row['COD_UTS']):03d}": f"{int(row['COD_PROV']):03d}"
        for level, row, _ in shape_records(originals["geography"])
        if level == "province"
    }
    province_counts, province_totals = read_posas(
        originals["province_zip"], spec["posas_provinces"]
    )
    if set(province_codes.values()) != set(province_totals):
        raise ValueError("Provincial population coverage differs")
    seen_sdmx = set()
    for uts, province_code in province_codes.items():
        group = [m for m in result if m.province == uts]
        sdmx_codes = {code_parents.get(m.code) for m in group}
        if len(sdmx_codes) != 1 or None in sdmx_codes:
            raise ValueError("SDMX and geography municipal membership disagree")
        sdmx_code = next(iter(sdmx_codes))
        if sdmx_code in seen_sdmx or sdmx_code not in household:
            raise ValueError("Ambiguous or missing SDMX province")
        seen_sdmx.add(sdmx_code)
        if [sum(m.households[i] for m in group) for i in range(6)] != household[sdmx_code]:
            raise ValueError("Provincial household reconciliation failed")
        for sex, attribute in [("1", "male"), ("2", "female")]:
            if [
                sum(getattr(m, attribute)[i] for m in group) for i in range(101)
            ] != province_counts[province_code, sex]:
                raise ValueError("Provincial sex/age reconciliation failed")
    parents: dict[tuple[str, str, str], int] = {}
    for row in read_profile(
        originals["population_parents"], spec["profiles"]["population_parents"]
    ):
        key = row["REF_AREA"], row["SEX"], row["AGE"]
        if key in parents:
            raise ValueError("Duplicate parent population key")
        parents[key] = int(row["OBS_VALUE"])
    if set(parents) != {
        (r, s, a)
        for r in ["IT", *REGIONS.values()]
        for s in ["1", "2", "9"]
        for a in [*AGES, "TOTAL"]
    }:
        raise ValueError("Incomplete country/region joint constraints")
    for area in ["IT", *REGIONS.values()]:
        group = [m for m in result if area == "IT" or REGIONS[int(m.region)] == area]
        for index, age in enumerate(AGES):
            male = sum(m.male[index] for m in group)
            female = sum(m.female[index] for m in group)
            if any(
                parents[area, sex, age] != n
                for sex, n in [("1", male), ("2", female), ("9", male + female)]
            ):
                raise ValueError(f"{area}/{age}: municipal/parent reconciliation failed")
        for sex in ["1", "2", "9"]:
            if sum(parents[area, sex, a] for a in AGES) != parents[area, sex, "TOTAL"]:
                raise ValueError("Parent age/total reconciliation failed")
        if [sum(m.households[i] for m in group) for i in range(6)] != household[area]:
            raise ValueError(f"{area}: municipal/parent household reconciliation failed")
    if sum(m.population for m in result) != spec["expected_population"]:
        raise ValueError("National population differs from reviewed total")
    inputs = NationalInput(
        evidence_kind="official_aggregates",
        population_reference=spec["population_reference"],
        household_reference=spec["household_reference"],
        geography_reference=spec["population_reference"],
        municipalities=result,
        attribution=spec["attribution"],
        source_hashes=hashes,
    )
    for m in inputs.municipalities:
        m.check_feasibility()
    atomic_json(
        root / "reports" / "m4" / f"admission-{uuid4().hex}.json",
        {
            "status": "admitted",
            "source_hashes": hashes,
            "persons": sum(totals.values()),
            "municipalities": len(result),
            "missing_household_categories_proved_zero": zeros,
            "zero_derivation": (
                "Nonnegative exhaustive categories sum exactly to the published total"
            ),
            "published": False,
        },
    )
    return inputs
