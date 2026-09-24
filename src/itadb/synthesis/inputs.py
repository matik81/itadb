"""Offline adapter for the pinned Valle d'Aosta aggregate evidence."""

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from itadb.pipeline.geography import read_territories
from itadb.pipeline.storage import archive_file, atomic_json
from itadb.synthesis.models import Calibration, PilotInput


def prepare_inputs(root: Path, inventory: Path, contract: Path) -> PilotInput:
    try:
        return _prepare(root, inventory, contract)
    except Exception as error:
        atomic_json(
            root / "quarantine" / f"m3-input-{uuid4()}.json",
            {"published": False, "error_code": type(error).__name__},
        )
        raise


def _prepare(root: Path, inventory: Path, contract: Path) -> PilotInput:
    archived, contract_hash = archive_file(contract, root / "raw")
    spec = json.loads(archived.read_text(encoding="utf-8"))
    if spec["name"] != "istat-m3-valle-aosta" or spec["version"] != "1.0.0":
        raise ValueError("Unsupported regional input contract")
    paths = json.loads(inventory.read_text(encoding="utf-8"))
    if set(paths) != set(spec["sources"]):
        raise ValueError("Source inventory differs from the regional contract")
    originals: dict[str, Path] = {}
    hashes = {"contract": contract_hash}
    for name, expected in spec["sources"].items():
        manifest_path, manifest_hash = archive_file(Path(paths[name]), root / "raw")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(manifest.get(k) != expected[k] for k in ("sha256", "url", "bytes")):
            raise ValueError(f"Unreviewed source manifest: {name}")
        if datetime.fromisoformat(manifest["retrieved_at"]).tzinfo is None:
            raise ValueError("Acquisition timestamp requires timezone")
        original, digest = archive_file(Path(paths[name]).parent / "payload", root / "raw")
        if digest != expected["sha256"] or original.stat().st_size != expected["bytes"]:
            raise ValueError(f"Corrupt regional evidence: {name}")
        originals[name] = original
        hashes[name] = digest
        hashes[name + "_manifest"] = manifest_hash

    def rows(name: str) -> list[dict[str, Any]]:
        profile = spec["profiles"][name]
        with originals[name].open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != profile["columns"]:
                raise ValueError("Unexpected SDMX columns")
            result = list(reader)
        if len(result) != profile["expected_rows"] or any(
            None in r or None in r.values() for r in result
        ):
            raise ValueError("Unexpected SDMX row count or shape")
        if any(r[k] not in allowed for r in result for k, allowed in profile["domains"].items()):
            raise ValueError("Unreviewed SDMX dimension, status, note or unit")
        if any(not r["OBS_VALUE"].isdigit() for r in result):
            raise ValueError("Only observed nonnegative integer aggregates are admitted")
        return [r for r in result if r["REF_AREA"] == "ITC2"]

    pop_rows = rows("population")
    pop = {(r["SEX"], r["AGE"]): int(r["OBS_VALUE"]) for r in pop_rows}
    ages = [f"Y{age}" for age in range(100)] + ["Y_GE100"]
    if len(pop) != len(pop_rows) or set(pop) != {
        (s, a) for s in ["1", "2", "9"] for a in [*ages, "TOTAL"]
    }:
        raise ValueError("Population coverage or keys differ")
    for age in [*ages, "TOTAL"]:
        if pop["1", age] + pop["2", age] != pop["9", age]:
            raise ValueError("Sex reconciliation failed")
    for sex in ["1", "2", "9"]:
        if sum(pop[sex, a] for a in ages) != pop[sex, "TOTAL"]:
            raise ValueError("Age reconciliation failed")
    hh_rows = rows("households")
    hh = {r["NUM_MEMB"]: int(r["OBS_VALUE"]) for r in hh_rows}
    categories = ["N1", "N2", "N3", "N4", "N5", "N6_GE"]
    if (
        len(hh_rows) != len(hh)
        or set(hh) != {*categories, "TOT"}
        or sum(hh[k] for k in categories) != hh["TOT"]
    ):
        raise ValueError("Household reconciliation failed")
    # Daily snapshots remain distinct. This explicitly checked equal total bridges
    # census end-of-year and population at the next day's start, not general vintage equivalence.
    territories, census = read_territories(
        originals["geo2021"], date(2021, 12, 31), hashes["geo2021"]
    )
    region = next(t for t in territories if t.level == "region" and t.code == "02")
    if census[region.key] != {"population": pop["9", "TOTAL"], "households": hh["TOT"]}:
        raise ValueError("Adjacent reference dates do not reconcile with the census")
    if pop["9", "TOTAL"] != spec["expected_population"] or hh["TOT"] != spec["expected_households"]:
        raise ValueError("Pilot coverage differs from reviewed totals")
    male = [pop["1", age] for age in ages]
    return PilotInput(
        schema_version="m3-input/2",
        evidence_kind="official_aggregates",
        calibration=Calibration(
            territory="ITC2",
            population_reference="2022-01-01",
            household_reference="2021-12-31",
            age_counts=[pop["9", age] for age in ages],
            male_by_age=male,
            household_counts=[hh[k] for k in categories],
        ),
        attribution=spec["attribution"],
        source_hashes=hashes,
    )
