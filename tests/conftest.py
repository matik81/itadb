from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

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
)
from itadb.pipeline.publish_coverage import archive_json
from itadb.pipeline.storage import sha256_file


@pytest.fixture
def m2_bundle(tmp_path: Path) -> tuple[Bundle, Path]:
    """Only invented values, territories and polygons; source demo is mandatory."""
    territories = []
    observations = []
    coverage = []
    equations = []
    evidence = []
    boundaries = []
    series = [
        Series(
            code="m2_test_" + code,
            title="Fixture " + code,
            unit="persons",
            dimensions={"measure": "fixture", "sex": sex, "age": age},
        )
        for code, sex, age in [
            ("total", "TOTAL", "TOTAL"),
            ("male", "M", "TOTAL"),
            ("female", "F", "TOTAL"),
            ("young", "TOTAL", "0:15"),
            ("older", "TOTAL", "15:1000"),
        ]
    ]
    for year in [2020, 2021]:
        snapshot = date(year, 1, 1)
        scheme = f"ITADB_DEMO_M2:{year}"

        def key(code: str, snapshot: date = snapshot) -> str:
            return f"{snapshot}:{code}"

        members = [("IT", "country", None), ("R1", "region", "IT"), ("R2", "region", "IT")]
        members += (
            [("A", "municipality", "R1"), ("B", "municipality", "R1"), ("D", "municipality", "R2")]
            if year == 2020
            else [
                ("C", "municipality", "R1"),
                ("E", "municipality", "R2"),
                ("F", "municipality", "R2"),
            ]
        )
        features = []
        for code, level, parent in members:
            territories.append(
                Territory(
                    key=key(code),
                    scheme=scheme,
                    code=code,
                    name="Inventato " + code,
                    level=level,
                    valid_from=snapshot,
                    valid_to=snapshot + timedelta(days=1),
                    snapshot=snapshot,
                    parent_key=key(parent) if parent else None,
                )
            )
            if code == "IT":
                continue
            west, east = (10, 11) if code in ["R1", "A", "B", "C"] else (11, 12)
            if code == "A":
                east = 10.5
            if code == "B":
                west = 10.5
            if code == "E":
                east = 11.5
            if code == "F":
                west = 11.5
            features.append(
                {
                    "type": "Feature",
                    "properties": {"code": code},
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [[[west, 40], [east, 40], [east, 41], [west, 41], [west, 40]]]
                        ],
                    },
                }
            )
        path = archive_json(tmp_path, {"type": "FeatureCollection", "features": features})
        evidence.append(
            Evidence(
                name=f"boundary{year}",
                path=path.relative_to(tmp_path).as_posix(),
                sha256=sha256_file(path),
                url="https://example.org/invented",
                retrieved_at="2026-01-01T00:00:00Z",
            )
        )
        boundaries.append(
            BoundarySource(
                evidence_name=f"boundary{year}",
                snapshot=snapshot,
                format="fixture_geojson",
                source_srid=4326,
            )
        )
        for s, factor in zip(series, [100, 60, 40, 30, 70], strict=True):
            for code, total in [("IT", 100), ("R1", 60), ("R2", 40)]:
                observations.append(
                    Observation(
                        territory_key=key(code),
                        series_code=s.code,
                        period=snapshot,
                        value=Decimal(total * factor // 100),
                        status="demo",
                    )
                )
            coverage.append(
                Coverage(
                    series_code=s.code,
                    period=snapshot,
                    snapshot=snapshot,
                    scheme=scheme,
                    territory_keys=[key(c) for c in ["IT", "R1", "R2"]],
                )
            )
            equations.append(
                Equation(
                    name=f"{year}:geo:{s.code}",
                    total=[key("IT"), s.code, str(snapshot)],
                    parts=[[key(c), s.code, str(snapshot)] for c in ["R1", "R2"]],
                    dimension="territory",
                )
            )
        for code in ["IT", "R1", "R2"]:
            for dimension, parts in [("sex", ["male", "female"]), ("age", ["young", "older"])]:
                equations.append(
                    Equation(
                        name=f"{year}:{code}:{dimension}",
                        total=[key(code), "m2_test_total", str(snapshot)],
                        parts=[[key(code), "m2_test_" + p, str(snapshot)] for p in parts],
                        dimension=dimension,
                    )
                )
    license_path = archive_json(
        tmp_path, {"license": "CC0", "notice": "Dati interamente inventati"}
    )
    evidence.append(
        Evidence(
            name="license",
            path=license_path.relative_to(tmp_path).as_posix(),
            sha256=sha256_file(license_path),
            url="https://example.org/invented",
            retrieved_at="2026-01-01T00:00:00Z",
        )
    )
    changes = [
        Change(
            event_id="fixture-" + kind,
            kind=kind,
            effective_date=date(2020, 6, 1),
            source_url=evidence[-1].url,
            evidence_sha256=evidence[-1].sha256,
            description="Evento inventato",
            from_keys=["2020-01-01:" + c for c in old],
            to_keys=["2021-01-01:" + c for c in new],
            weight_basis=basis,
        )
        for kind, old, new, basis in [
            ("merger", ["A", "B"], ["C"], "exact"),
            ("split", ["D"], ["E", "F"], "structural"),
        ]
    ]
    bundle = Bundle(
        version="m2/1.0",
        dataset_id="demo_m2",
        is_demo=True,
        reference_period=date(2021, 1, 1),
        default_series="m2_test_total",
        attribution="Fixture inventata",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        license_evidence_name="license",
        territories=territories,
        series=series,
        observations=observations,
        coverage=coverage,
        equations=equations,
        changes=changes,
        evidence=evidence,
        boundaries=boundaries,
        reconciliations=[
            {"passed": True, "method": "Controllo fixture inventata", "evidence": ["license"]}
        ],
    )
    contract = archive_json(tmp_path, {"name": "m2-test", "is_demo": True})
    return bundle, contract
