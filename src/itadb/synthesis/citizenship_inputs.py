"""Bounded STR/RCS admission, including exact demographic and territorial reconciliation."""

import csv
import io
import json
import re
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from itadb.pipeline.geography import shape_records
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipMunicipality
from itadb.synthesis.national_models import NationalInput

MACRO_REGIONS = {
    "1": {"01", "02", "03", "07"},
    "2": {"04", "05", "06", "08"},
    "3": {"09", "10", "11", "12"},
    "4": {"13", "14", "15", "16", "17", "18"},
    "5": {"19", "20"},
}


def integer(value: str) -> int:
    if not value.isascii() or not value.isdigit() or int(value) > 70_000_000:
        raise ValueError("Only observed nonnegative integer counts are admitted")
    return int(value)


def zip_rows(path: Path, profile: dict[str, Any]) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if (
            len(entries) != 1
            or entries[0].filename != profile["member"]
            or entries[0].file_size != profile["uncompressed_bytes"]
            or entries[0].file_size > 60_000_000
        ):
            raise ValueError("Unreviewed ZIP layout or expansion budget")
        with archive.open(entries[0]) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            if "title" in profile and stream.readline().strip() != profile["title"]:
                raise ValueError("Unreviewed reference title")
            reader = csv.DictReader(stream, delimiter=";")
            if reader.fieldnames != profile["columns"]:
                raise ValueError("Unreviewed source columns")
            count = 0
            for row in reader:
                if None in row or None in row.values():
                    raise ValueError("Malformed source row")
                count += 1
                yield row
            if count != profile["rows"]:
                raise ValueError("Unexpected source row count")


def read_str(path: Path, profile: dict[str, Any]) -> dict[str, list[list[int]]]:
    result: dict[str, dict[int, list[int]]] = {}
    for row in zip_rows(path, profile):
        code = row[profile["code_column"]]
        age = integer(row["Età"])
        ages = result.setdefault(code, {})
        if age not in {*range(101), 999} or age in ages:
            raise ValueError("Duplicate or unsupported STR age")
        ages[age] = [integer(row["Maschi"]), integer(row["Femmine"])]
    counts = {}
    for code, ages in result.items():
        if set(ages) != {*range(101), 999}:
            raise ValueError("STR requires explicit cells including zeros")
        counts[code] = [[ages[age][s] for age in range(101)] for s in range(2)]
        if [sum(n) for n in counts[code]] != ages[999]:
            raise ValueError("STR ages do not reconcile to published totals")
    return counts


def read_rcs(path: Path, profile: dict[str, Any], year: str) -> dict[str, dict[str, list[int]]]:
    result: dict[str, dict[str, list[int]]] = {}
    labels = profile["citizenships"]
    for row in zip_rows(path, profile):
        code, country = row["Codice Istat"], row["Codice stato di cittadinanza"]
        if (
            row["Anno"] != year
            or country not in labels
            or row["Stato di cittadinanza"] != labels[country]
            or not re.fullmatch(r"[0-9]{1,6}|IT", code)
        ):
            raise ValueError("Unreviewed RCS reference, geography or citizenship")
        values = [integer(row["Maschi"]), integer(row["Femmine"])]
        if sum(values) != integer(row["Totale"]):
            raise ValueError("RCS sex totals disagree")
        area = result.setdefault(code, {})
        if country in area:
            raise ValueError("Duplicate RCS citizenship")
        area[country] = values
    return result


def reconcile_parents(
    rcs: dict[str, dict[str, list[int]]],
    base: NationalInput,
    provinces: dict[str, str],
) -> None:
    """Sparse RCS cells imply zero only after exhaustive independent reconciliation."""
    expected: dict[str, Counter[tuple[str, int]]] = {}
    for m in base.municipalities:
        macro = next(code for code, regions in MACRO_REGIONS.items() if m.region in regions)
        for parent in [provinces[m.province], m.region, macro, "IT"]:
            counts = expected.setdefault(parent, Counter())
            for country, values in rcs[m.code].items():
                counts.update({(country, s): n for s, n in enumerate(values) if n})
    if set(rcs) != {m.code for m in base.municipalities} | set(expected):
        raise ValueError("RCS territory coverage differs from the base hierarchy")
    for area, counts in expected.items():
        actual = Counter(
            {(c, s): n for c, values in rcs[area].items() for s, n in enumerate(values) if n}
        )
        if actual != counts:
            raise ValueError(f"RCS citizenship reconciliation failed for {area}")


def prepare_citizenship_inputs(
    root: Path, inventory: Path, contract: Path, base: NationalInput
) -> CitizenshipInput:
    try:
        return _prepare(root, inventory, contract, base)
    except Exception as error:
        atomic_json(
            root / "quarantine" / f"citizenship-input-{uuid4().hex}.json",
            {"published": False, "error_code": type(error).__name__},
        )
        raise


def _prepare(root: Path, inventory: Path, contract: Path, base: NationalInput) -> CitizenshipInput:
    archived, digest = archive_file(contract, root / "raw")
    spec = json.loads(archived.read_text(encoding="utf-8"))
    if spec["name"] != "istat-citizenship" or spec["version"] != "1.0.0":
        raise ValueError("Unsupported citizenship contract")
    if base.evidence_kind != "official_aggregates":
        raise ValueError("Official citizenship admission requires official base aggregates")
    paths = json.loads(inventory.read_text(encoding="utf-8"))
    if set(paths) != set(spec["sources"]):
        raise ValueError("Inventory differs from citizenship contract")
    originals = {}
    hashes = {"contract": digest}
    for name, source in spec["sources"].items():
        print(f"Originale cittadinanza: {name}", flush=True)
        path = Path(paths[name])
        manifest_path, manifest_digest = archive_file(path, root / "raw")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(manifest.get(k) != source[k] for k in ["sha256", "bytes", "url"]):
            raise ValueError("Unreviewed citizenship acquisition")
        if datetime.fromisoformat(manifest["retrieved_at"]).tzinfo is None:
            raise ValueError("Acquisition time requires timezone")
        payload, payload_hash = archive_file(path.parent / "payload", root / "raw")
        if payload_hash != source["sha256"] or payload.stat().st_size != source["bytes"]:
            raise ValueError("Citizenship source corrupted")
        originals[name] = payload
        hashes[name], hashes[name + "_manifest"] = payload_hash, manifest_digest
    print("Riconciliazione STR/RCS con tutte le celle demografiche nazionali", flush=True)
    foreign = read_str(originals["str"], spec["profiles"]["str"])
    rcs = read_rcs(originals["rcs"], spec["profiles"]["rcs"], spec["population_reference"][:4])
    if set(foreign) != {m.code for m in base.municipalities}:
        raise ValueError("STR municipality coverage differs from the base")
    inputs = CitizenshipInput(
        population_reference=spec["population_reference"],
        evidence_kind=base.evidence_kind,
        municipalities=[
            CitizenshipMunicipality(
                code=m.code,
                foreign_male=foreign[m.code][0],
                foreign_female=foreign[m.code][1],
                countries=rcs[m.code],
            )
            for m in sorted(base.municipalities, key=lambda m: m.code)
        ],
        country_labels=spec["profiles"]["rcs"]["citizenships"],
        source_hashes=hashes,
        attribution=spec["attribution"],
    )
    inputs.check_base(base)
    geography_hash = base.source_hashes["geography"]
    geography = root / "raw" / geography_hash[:2] / geography_hash / "payload"
    if sha256_file(geography) != geography_hash:
        raise ValueError("Base geography archive corrupted")
    provinces = {
        f"{int(row['COD_UTS']):03d}": f"{int(row['COD_PROV']):03d}"
        for level, row, _ in shape_records(geography)
        if level == "province"
    }
    reconcile_parents(rcs, base, provinces)
    regions = read_str(originals["str_regions"], spec["profiles"]["str_regions"])
    if set(regions) != {m.region for m in base.municipalities}:
        raise ValueError("STR region coverage differs")
    for region, expected in regions.items():
        members = [m for m in base.municipalities if m.region == region]
        if expected != [
            [sum(foreign[m.code][s][a] for m in members) for a in range(101)] for s in range(2)
        ]:
            raise ValueError("STR regional joint reconciliation failed")
    foreign_total = sum(sum(m.foreign_male) + sum(m.foreign_female) for m in inputs.municipalities)
    if foreign_total != spec["expected_foreign_population"]:
        raise ValueError("Unexpected national foreign total")
    atomic_json(
        root / "reports" / "citizenship" / f"admission-{uuid4().hex}.json",
        {
            "status": "admitted",
            "source_hashes": hashes,
            "foreign_persons": foreign_total,
            "municipalities": len(inputs.municipalities),
            "rcs_parent_areas": len(rcs) - len(inputs.municipalities),
            "missing_rcs_cells": "zero_only_after_exhaustive_base_STR_and_parent_reconciliation",
            "published": False,
        },
    )
    return inputs
