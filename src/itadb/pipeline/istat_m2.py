"""Reviewed ISTAT M2 adapter. Inputs are pinned originals, not arbitrary normalized records."""

import csv
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

from itadb.pipeline.coverage import (
    BoundarySource,
    Bundle,
    Change,
    Coverage,
    Equation,
    Evidence,
    Observation,
    Series,
    Territory,
    validate_bundle,
)
from itadb.pipeline.geography import read_territories, territory_key
from itadb.pipeline.publish_coverage import archive_json
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError


def build_istat_m2(root: Path, inputs: Path, contract: Path) -> Bundle:
    """All validation is offline; new upstream content requires a reviewed contract revision."""
    try:
        return _build(root, inputs, contract)
    except Exception as error:
        atomic_json(
            root / "quarantine" / f"m2-onboarding-{uuid4()}.json",
            {
                "published": False,
                "error_code": type(error).__name__,
                "report": error.report if isinstance(error, QualityError) else None,
            },
        )
        raise


def _build(root: Path, inputs: Path, contract: Path) -> Bundle:
    contract_path, _ = archive_file(contract, root / "raw")
    spec = json.loads(contract_path.read_text(encoding="utf-8"))
    if spec["name"] != "istat-m2" or spec["version"] != "1.0.0":
        raise ValueError("Unsupported M2 contract")
    paths = json.loads(inputs.read_text(encoding="utf-8"))
    if set(paths) != set(spec["sources"]):
        raise ValueError("Source inventory differs from the reviewed contract")
    evidence = []
    originals = {}
    for name, expected in spec["sources"].items():
        manifest_path, _ = archive_file(Path(paths[name]), root / "raw")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(manifest.get(k) != expected[k] for k in ("sha256", "url", "bytes")):
            raise ValueError(f"Unreviewed source manifest: {name}")
        payload_path = Path(paths[name]).parent / "payload"
        original, digest = archive_file(payload_path, root / "raw")
        if digest != expected["sha256"] or original.stat().st_size != expected["bytes"]:
            raise ValueError(f"Corrupt source: {name}")
        originals[name] = original
        for label, path in ((name, original), (name + "_manifest", manifest_path)):
            evidence.append(
                Evidence(
                    name=label,
                    path=path.relative_to(root).as_posix(),
                    sha256=sha256_file(path),
                    url=manifest["url"],
                    retrieved_at=manifest["retrieved_at"],
                )
            )
    territories: list[Territory] = []
    census: dict[str, dict[str, int]] = {}
    boundaries = []
    for name, geography in spec["geographies"].items():
        print(f"Geografia: {name}", flush=True)
        snapshot = date.fromisoformat(geography["snapshot"])
        ts, counts = read_territories(originals[name], snapshot, spec["sources"][name]["sha256"])
        actual = {
            level: sum(t.level == level for t in ts) for level in geography["expected_counts"]
        }
        if actual != geography["expected_counts"]:
            raise ValueError("Geographic coverage differs from reviewed counts")
        territories.extend(ts)
        census.update(counts)
        boundaries.append(
            BoundarySource(
                evidence_name=name, snapshot=snapshot, format="istat_shapefile", source_srid=32632
            )
        )
    by_key = {t.key: t for t in territories}
    series: dict[str, Series] = {}
    observations: dict[tuple[str, str, date], Observation] = {}
    reconciliations = []

    def add(
        key: str,
        code: str,
        title: str,
        unit: Literal["persons", "households", "dwellings"],
        dimensions: dict[str, str],
        period: date,
        value: int,
        attrs: dict[str, str] | None = None,
    ) -> None:
        item = Series(code=code, title=title, unit=unit, dimensions=dimensions)
        if code in series and series[code] != item:
            raise ValueError("Inconsistent series definition")
        series[code] = item
        identity = (key, code, period)
        if identity in observations:
            if observations[identity].value != value:
                raise QualityError(
                    {"checks": {"cross_source_reconciliation": False}, "cell": identity}
                )
            return
        attrs = attrs or {}
        observations[identity] = Observation(
            territory_key=key,
            series_code=code,
            period=period,
            value=Decimal(value),
            status="unflagged_upstream",
            upstream_status=attrs.get("OBS_STATUS", ""),
            upstream_note=json.dumps(
                {k: v for k, v in attrs.items() if k.startswith("NOTE_") and v}, sort_keys=True
            ),
            upstream_unit=attrs.get("UNIT_MEAS", ""),
            upstream_unit_multiplier=attrs.get("UNIT_MULT", ""),
        )

    census_date = date(2021, 12, 31)
    hh_title = "Famiglie al 31 dicembre — totale"
    hh_dims = {"measure": "households_dec31", "household_size": "TOTAL"}
    for key, census_counts in census.items():
        add(
            key,
            "census_population_total",
            "Popolazione al 31 dicembre — totale",
            "persons",
            {"measure": "population_dec31", "sex": "TOTAL", "age": "TOTAL"},
            census_date,
            census_counts["population"],
        )
        add(
            key,
            "census_households_total",
            hh_title,
            "households",
            hh_dims,
            census_date,
            census_counts["households"],
        )
    matched_households = 0
    for name, profile in spec["profiles"].items():
        print(f"Dati demografici: {name}", flush=True)
        with originals[name].open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != profile["columns"]:
                raise ValueError("Unexpected SDMX columns")
            rows = list(reader)
        if len(rows) != profile["expected_rows"] or any(
            None in r or None in r.values() for r in rows
        ):
            raise ValueError("Unexpected SDMX row count or shape")
        if any(r[k] not in allowed for r in rows for k, allowed in profile["domains"].items()):
            raise ValueError("Unreviewed dimensions, flags, notes or units")
        period = date.fromisoformat(profile["period"])
        seen = set()
        for r in rows:
            key = territory_key(period, spec["region_mapping"][r["REF_AREA"]])
            if not r["OBS_VALUE"].isdigit() or int(r["OBS_VALUE"]) >= 10**14:
                raise ValueError("Noninteger or missing count in reviewed complete slice")
            value = int(r["OBS_VALUE"])
            if name == "population":
                sex = {"1": "M", "2": "F", "9": "TOTAL"}[r["SEX"]]
                age = r["AGE"]
                age_range = (
                    "TOTAL"
                    if age == "TOTAL"
                    else ("100:1000" if age == "Y_GE100" else f"{int(age[1:])}:{int(age[1:]) + 1}")
                )
                code = f"population_jan1_{sex.lower()}_{age.lower()}"
                sex_label = {"M": "maschi", "F": "femmine", "TOTAL": "totale"}[sex]
                title = f"Popolazione al 1° gennaio — {sex_label}, " + (
                    "tutte le età"
                    if age == "TOTAL"
                    else ("100 anni e più" if age == "Y_GE100" else f"{age[1:]} anni")
                )
                add(
                    key,
                    code,
                    title,
                    "persons",
                    {"measure": "population_jan1", "sex": sex, "age": age_range},
                    period,
                    value,
                    r,
                )
            elif name == "households":
                size = r["NUM_MEMB"]
                code = (
                    "census_households_total"
                    if size == "TOT"
                    else f"census_households_{size.lower()}"
                )
                dims = {
                    "measure": "households_dec31",
                    "household_size": "TOTAL"
                    if size == "TOT"
                    else ("6:1000" if size == "N6_GE" else f"{size[1:]}:{int(size[1:]) + 1}"),
                }
                size_label = "6 e più" if size == "N6_GE" else size[1:]
                title = (
                    hh_title
                    if size == "TOT"
                    else f"Famiglie al 31 dicembre — {size_label} componenti"
                )
                if (key, code, period) in observations:
                    matched_households += 1
                add(key, code, title, "households", dims, period, value, r)
            else:
                occupancy = {
                    "NUM_DW_AV": "TOTAL",
                    "NUM_OCC_DW_AV": "occupied",
                    "NUM_UNOCC_DW_AV": "unoccupied",
                }[r["INDICATOR"]]
                code = "census_dwellings_" + occupancy.lower()
                title = (
                    "Abitazioni al 31 dicembre — "
                    + {"TOTAL": "totale", "occupied": "occupate", "unoccupied": "non occupate"}[
                        occupancy
                    ]
                )
                add(
                    key,
                    code,
                    title,
                    "dwellings",
                    {"measure": "dwellings_dec31", "occupancy": occupancy},
                    period,
                    value,
                    r,
                )
            identity = (key, code, period)
            if identity in seen:
                raise ValueError("Duplicate SDMX cell")
            seen.add(identity)
    if matched_households != 20:
        raise ValueError("Incomplete cross-source regional reconciliation")
    reconciliations.append(
        {
            "passed": True,
            "method": "Uguaglianza esatta delle 20 regioni: FAM21 geografico = totale famiglie "
            "SDMX 2021; due prodotti ISTAT, non due stime indipendenti.",
            "evidence": ["geo2021", "households"],
            "matched_regions": matched_households,
            "tolerance": 0,
        }
    )
    equations = []
    grouped: dict[tuple[str, date], list[str]] = defaultdict(list)
    for key, code, period in observations:
        grouped[code, period].append(key)
    for (code, period), keys in sorted(grouped.items()):
        for parent in keys:
            children = [k for k in keys if by_key[k].parent_key == parent]
            if len(children) >= 2:
                equations.append(
                    Equation(
                        name=f"geo:{code}:{parent}",
                        total=[parent, code, str(period)],
                        parts=[[child, code, str(period)] for child in sorted(children)],
                        dimension="territory",
                    )
                )
    dimensions: list[Literal["sex", "age", "household_size", "occupancy"]] = [
        "sex",
        "age",
        "household_size",
        "occupancy",
    ]
    for key in sorted(by_key):
        for dimension in dimensions:
            for total_code, total_series in series.items():
                if total_series.dimensions.get(dimension) != "TOTAL":
                    continue
                period = by_key[key].snapshot
                if (key, total_code, period) not in observations:
                    continue
                parts = [
                    s.code
                    for s in series.values()
                    if s.code != total_code
                    and s.dimensions.get(dimension) not in {None, "TOTAL"}
                    and {k: v for k, v in s.dimensions.items() if k != dimension}
                    == {k: v for k, v in total_series.dimensions.items() if k != dimension}
                    and (key, s.code, period) in observations
                ]
                if len(parts) >= 2:
                    equations.append(
                        Equation(
                            name=f"{dimension}:{key}:{total_code}",
                            total=[key, total_code, str(period)],
                            parts=[[key, c, str(period)] for c in sorted(parts)],
                            dimension=dimension,
                        )
                    )
    coverage = [
        Coverage(
            series_code=code,
            period=period,
            snapshot=by_key[keys[0]].snapshot,
            scheme=by_key[keys[0]].scheme,
            territory_keys=sorted(keys),
        )
        for (code, period), keys in sorted(grouped.items())
    ]
    changes = []
    event_source = spec["sources"]["events"]
    for item in spec["events"]:
        changes.append(
            Change(
                event_id=item["event_id"],
                kind=item["kind"],
                effective_date=item["effective_date"],
                source_url=event_source["url"],
                evidence_sha256=event_source["sha256"],
                description=item["description"],
                from_keys=[
                    territory_key(date.fromisoformat(item["from_snapshot"]), c)
                    for c in item["from_codes"]
                ],
                to_keys=[
                    territory_key(date.fromisoformat(item["to_snapshot"]), c)
                    for c in item["to_codes"]
                ],
                weight_basis=item["weight_basis"],
            )
        )
    # Every disappeared/new municipality between the reviewed snapshots must be explained.
    snapshots = sorted({t.snapshot for t in territories})
    for before, after in zip(snapshots, snapshots[1:], strict=False):
        old = {t.code for t in territories if t.snapshot == before and t.level == "municipality"}
        new = {t.code for t in territories if t.snapshot == after and t.level == "municipality"}
        events = [
            e
            for e in changes
            if by_key[e.from_keys[0]].snapshot == before and by_key[e.to_keys[0]].snapshot == after
        ]
        explained_old = {by_key[k].code for e in events for k in e.from_keys}
        explained_new = {by_key[k].code for e in events for k in e.to_keys}
        passed = (old - new) <= explained_old and (new - old) <= explained_new
        if not passed:
            raise ValueError(f"Unexplained geographic change: {before} to {after}")
        reconciliations.append(
            {
                "passed": passed,
                "method": "Codici comunali aggiunti e soppressi riconciliati con eventi ufficiali, "
                "senza allocazione demografica implicita.",
                "evidence": ["geo2020", "geo2021", "geo2024", "events"],
                "from": str(before),
                "to": str(after),
                "removed": sorted(old - new),
                "added": sorted(new - old),
            }
        )
    bundle = Bundle(
        version="m2/1.0",
        dataset_id="istat_m2",
        is_demo=False,
        reference_period=date(2024, 1, 1),
        default_series="population_jan1_total_total",
        attribution="Fonte: Istat, dati geografici e IstatData. Selezione, controlli e formati "
        "derivati: Itadb. Confini provinciali e regionali derivati dall'unione dei comuni.",
        derive_parent_boundaries=spec["derive_parent_boundaries"],
        license_url="https://creativecommons.org/licenses/by/4.0/",
        license_evidence_name="license",
        territories=territories,
        series=list(series.values()),
        observations=list(observations.values()),
        coverage=coverage,
        equations=equations,
        changes=changes,
        evidence=evidence,
        boundaries=boundaries,
        reconciliations=reconciliations,
        boundary_repair_keys=spec["boundary_repairs"]["keys"],
        boundary_area_tolerance=spec["boundary_repairs"]["max_relative_area_change"],
    )
    report = validate_bundle(bundle)
    report_path = archive_json(root, report)
    print(
        f"M2 verificata offline: {len(bundle.observations):,} osservazioni; "
        f"{len(territories):,} versioni territoriali; {len(equations):,} riconciliazioni; "
        f"rapporto {report_path}",
        flush=True,
    )
    return bundle
