"""Offline onboarding gate for one reviewed ISTAT regional population slice."""

import csv
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from filelock import FileLock

from itadb.pipeline.storage import archive_file, atomic_json
from itadb.pipeline.validate import QualityError

TRANSFORM_VERSION = "istat-population-regions/onboarding-1.0.0"
BASE_URL = "https://esploradati.istat.it/SDMXWS/rest"
NS = {
    "s": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "c": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}


def _gate(report: dict[str, Any], name: str, passed: bool) -> None:
    report["checks"][name] = passed
    if not passed:
        raise QualityError(report)


def _xml(path: Path) -> ET.Element:
    if path.stat().st_size > 20_000_000:
        raise ValueError("Metadata exceeds the 20 MB limit")
    content = path.read_bytes()
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("DTD/entity declarations are not supported")
    return ET.fromstring(content)


def _identity(element: ET.Element, expected: dict[str, str]) -> bool:
    return all(
        element.get(attribute) == expected[key]
        for attribute, key in (("agencyID", "agency"), ("id", "id"), ("version", "version"))
    )


def _metadata(
    structure: Path, dataflow: Path, spec: dict[str, Any], report: dict[str, Any]
) -> dict[str, dict[str, str]]:
    flow = _xml(dataflow).findall(".//s:Dataflow", NS)
    _gate(report, "dataflow_identity", len(flow) == 1 and _identity(flow[0], spec["dataflow"]))
    ref = flow[0].find("s:Structure/Ref", NS)
    _gate(report, "dataflow_dsd", ref is not None and _identity(ref, spec["dsd"]))
    updates = flow[0].findall("c:Annotations/c:Annotation[@id='LAST_UPDATE']/c:AnnotationTitle", NS)
    report["upstream_last_update"] = updates[0].text if len(updates) == 1 else None
    # LAST_UPDATE refers to the whole dataflow, not the publication date of this slice.
    report["upstream_published_at"] = None

    tree = _xml(structure)
    structures = tree.findall(".//s:DataStructure", NS)
    _gate(report, "dsd_identity", len(structures) == 1 and _identity(structures[0], spec["dsd"]))
    dsd = structures[0]
    dimensions = dsd.findall("s:DataStructureComponents/s:DimensionList/s:Dimension", NS)
    actual = [(node.get("id"), node.get("position")) for node in dimensions]
    expected = [(item["id"], str(item["position"])) for item in spec["dimensions"]]
    _gate(report, "dimension_order", actual == expected)
    time = dsd.findall("s:DataStructureComponents/s:DimensionList/s:TimeDimension", NS)
    _gate(
        report,
        "time_dimension",
        len(time) == 1
        and time[0].get("id") == spec["time_dimension"]
        and time[0].get("position") == str(spec["time_position"]),
    )
    measures = dsd.findall("s:DataStructureComponents/s:MeasureList/s:PrimaryMeasure", NS)
    _gate(report, "measure", len(measures) == 1 and measures[0].get("id") == spec["measure"])
    attributes = dsd.findall("s:DataStructureComponents/s:AttributeList/s:Attribute", NS)
    _gate(report, "attributes", [a.get("id") for a in attributes] == list(spec["attributes"]))
    enumerations = {item["id"]: item["codelist"] for item in spec["dimensions"]}
    enumerations.update(spec["attributes"])
    for node in dimensions + attributes:
        enum = node.find("s:LocalRepresentation/s:Enumeration/Ref", NS)
        _gate(
            report,
            f"enumeration_{node.get('id')}",
            enum is not None
            and enum.get("id") == enumerations[node.get("id")]
            and enum.get("agencyID") == spec["codelist_agency"]
            and enum.get("version") == spec["codelist_version"],
        )
    domains: dict[str, dict[str, str]] = {}
    for identifier in sorted(set(enumerations.values())):
        lists = tree.findall(f".//s:Codelist[@id='{identifier}']", NS)
        _gate(
            report,
            f"codelist_{identifier}",
            len(lists) == 1
            and lists[0].get("agencyID") == spec["codelist_agency"]
            and lists[0].get("version") == spec["codelist_version"],
        )
        codes = lists[0].findall("s:Code", NS)
        domains[identifier] = {
            code.get("id", ""): next(
                (
                    name.text or ""
                    for name in code.findall("c:Name", NS)
                    if name.get("{http://www.w3.org/XML/1998/namespace}lang") == "it"
                ),
                "",
            )
            for code in codes
        }
        _gate(report, f"unique_codes_{identifier}", len(domains[identifier]) == len(codes))
    _gate(
        report,
        "territorial_labels",
        all(domains["CL_ITTER107"].get(code) == name for code, name in spec["territories"].items()),
    )
    _gate(
        report,
        "reviewed_code_meanings",
        all(
            domains[codelist].get(code) == label
            for codelist, codes in spec["reviewed_codes"].items()
            for code, label in codes.items()
        ),
    )
    for dim in spec["dimensions"]:
        if dim["id"] in spec["selection"]:
            _gate(
                report,
                f"selected_code_{dim['id']}",
                spec["selection"][dim["id"]] in domains[dim["codelist"]],
            )
    return domains


def validate_population_sample(
    raw: Path, structure: Path, dataflow: Path, contract: Path
) -> dict[str, Any]:
    """Validate 20 disjoint regions plus their national control; never publish."""
    spec = json.loads(contract.read_text(encoding="utf-8"))
    report: dict[str, Any] = {"checks": {}, "rows": 0, "status": "checking", "published": False}
    _gate(
        report,
        "supported_contract",
        spec["name"] == "istat-population-regions"
        and spec["version"] == "1.0.0"
        and spec["stage"] == "onboarding"
        and spec["is_demo"] is False,
    )
    _gate(report, "bounded_input", raw.stat().st_size <= 100_000)
    domains = _metadata(structure, dataflow, spec, report)
    with raw.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        _gate(report, "exact_columns", reader.fieldnames == spec["columns"])
        rows: list[dict[str, str]] = []
        for row in reader:
            _gate(report, "bounded_rows", len(rows) < spec["expected_rows"])
            _gate(report, "row_shape", None not in row and None not in row.values())
            rows.append(row)
    report["rows"] = len(rows)
    _gate(report, "row_count", len(rows) == spec["expected_rows"])
    flow = spec["dataflow"]
    flow_id = f"{flow['agency']}:{flow['id']}({flow['version']})"
    selection = {"DATAFLOW": flow_id, "TIME_PERIOD": spec["reference_year"], **spec["selection"]}
    _gate(report, "selected_slice", all(r[k] == v for r in rows for k, v in selection.items()))
    areas = [row["REF_AREA"] for row in rows]
    _gate(report, "unique_key", len(set(areas)) == len(areas))
    _gate(report, "territorial_coverage", set(areas) == set(spec["territories"]))
    _gate(
        report,
        "nonnegative_int64",
        all(
            re.fullmatch(r"[0-9]{1,19}", row["OBS_VALUE"]) is not None
            and int(row["OBS_VALUE"]) <= 2**63 - 1
            for row in rows
        ),
    )
    _gate(
        report, "reviewed_flags", all(r["OBS_STATUS"] in spec["allowed_obs_status"] for r in rows)
    )
    _gate(
        report,
        "reviewed_units",
        all(r[attr] in values for r in rows for attr, values in spec["unit_policy"].items()),
    )
    _gate(
        report,
        "reviewed_notes",
        all(
            row["NOTE_REF_AREA"] == spec["allowed_area_notes"][row["REF_AREA"]]
            and all(
                not row[key]
                for key in spec["attributes"]
                if key not in {"NOTE_REF_AREA", "OBS_STATUS", "UNIT_MEAS", "UNIT_MULT"}
            )
            for row in rows
        ),
    )
    _gate(
        report,
        "attribute_domains",
        all(
            not row[attr] or row[attr] in domains[codelist]
            for row in rows
            for attr, codelist in spec["attributes"].items()
        ),
    )
    values = {row["REF_AREA"]: int(row["OBS_VALUE"]) for row in rows}
    regional_sum = sum(values[code] for code in spec["regional_codes"])
    national = values[spec["national_code"]]
    report["reconciliation"] = {
        "regional_sum": regional_sum,
        "national_total": national,
        "difference": regional_sum - national,
        "tolerance": spec["reconciliation_tolerance"],
    }
    _gate(
        report,
        "national_reconciliation",
        abs(regional_sum - national) <= spec["reconciliation_tolerance"],
    )
    report.update(
        status="validated_sample",
        transform_version=TRANSFORM_VERSION,
        reference_period=spec["reference_date"],
        territory_scheme=spec["territory_scheme"],
        unit=spec["unit"],
        license=spec["license"],
        limitations=spec["limitations"],
        observations=[
            {
                "territory_code": row["REF_AREA"],
                "territory_name": spec["territories"][row["REF_AREA"]],
                "level": "country" if row["REF_AREA"] == spec["national_code"] else "region",
                "period": spec["reference_date"],
                "population": int(row["OBS_VALUE"]),
                "status": "unflagged_upstream",
                "upstream_attributes": {attr: row[attr] for attr in spec["attributes"]},
            }
            for row in sorted(rows, key=lambda row: row["REF_AREA"])
        ],
    )
    return report


def _acquisition(manifest: Path, root: Path, expected_url: str) -> tuple[Path, dict[str, Any]]:
    """Snapshot and verify the payload and its provenance before validation."""
    archived_manifest, manifest_hash = archive_file(manifest, root / "raw")
    content = json.loads(archived_manifest.read_text(encoding="utf-8"))
    actual, expected = urlsplit(content["url"]), urlsplit(expected_url)
    if (
        content["source"] != "istat"
        or actual[:3] != expected[:3]
        or parse_qs(actual.query) != parse_qs(expected.query)
        or actual.fragment
    ):
        raise ValueError("Acquisition source/query does not match the reviewed contract")
    if datetime.fromisoformat(content["retrieved_at"]).tzinfo is None:
        raise ValueError("Acquisition time must include a timezone")
    path, checksum = archive_file(manifest.parent / "payload", root / "raw")
    if checksum != content["sha256"] or path.stat().st_size != content["bytes"]:
        raise ValueError("Acquisition payload does not match its manifest")
    return path, {
        "sha256": checksum,
        "path": path.relative_to(root).as_posix(),
        "manifest_sha256": manifest_hash,
        "manifest_path": archived_manifest.relative_to(root).as_posix(),
        "url": content["url"],
        "retrieved_at": content["retrieved_at"],
    }


def check_population_sample(
    root: Path, acquisition: Path, structure: Path, dataflow: Path, contract: Path
) -> Path:
    """Produce an immutable local evidence report, or a quarantined failed attempt."""
    archived_contract, contract_hash = archive_file(contract, root / "raw")
    spec = json.loads(archived_contract.read_text(encoding="utf-8"))
    flow, dsd = spec["dataflow"], spec["dsd"]
    key = ".".join(
        "+".join(spec["territories"]) if dim["id"] == "REF_AREA" else spec["selection"][dim["id"]]
        for dim in spec["dimensions"]
    )
    data_url = (
        f"{BASE_URL}/data/{flow['agency']},{flow['id']},{flow['version']}/{key}"
        f"?startPeriod={spec['request_start']}&endPeriod={spec['request_end']}"
    )
    structure_url = (
        f"{BASE_URL}/datastructure/{dsd['agency']}/{dsd['id']}/{dsd['version']}?references=all"
    )
    flow_url = (
        f"{BASE_URL}/dataflow/{flow['agency']}/{flow['id']}/{flow['version']}?references=none"
    )
    evidence: dict[str, Any] = {
        "contract_sha256": contract_hash,
        "contract_path": archived_contract.relative_to(root).as_posix(),
        "transform_version": TRANSFORM_VERSION,
    }
    try:
        raw, evidence["data"] = _acquisition(acquisition, root, data_url)
        metadata, evidence["structure"] = _acquisition(structure, root, structure_url)
        flow_metadata, evidence["dataflow"] = _acquisition(dataflow, root, flow_url)
        report = validate_population_sample(raw, metadata, flow_metadata, archived_contract)
    except (ValueError, KeyError, ET.ParseError) as error:
        atomic_json(
            root / "quarantine" / f"istat-population-{uuid4().hex}.json",
            {
                "status": "failed",
                "published": False,
                "evidence": evidence,
                "error_code": type(error).__name__,
                "report": error.report if isinstance(error, QualityError) else None,
            },
        )
        raise
    report["evidence"] = evidence
    identity = str(uuid5(NAMESPACE_URL, json.dumps(evidence, sort_keys=True)))
    output = root / "reports" / f"istat-population-{identity}.json"
    state = root / "state"
    state.mkdir(parents=True, exist_ok=True)
    with FileLock(str(state / f"{identity}.lock"), timeout=60):
        if output.exists():
            if json.loads(output.read_text(encoding="utf-8")) != report:
                raise ValueError("Existing evidence report has been modified")
        else:
            atomic_json(output, report)
    return output
