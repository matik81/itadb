"""Explicit demographic partitions and versioned territorial coverage."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from itadb.pipeline.validate import QualityError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Territory(StrictModel):
    key: str
    scheme: str
    code: str
    name: str
    level: Literal["country", "region", "province", "municipality"]
    valid_from: date
    valid_to: date
    snapshot: date
    parent_key: str | None


class Series(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str
    unit: Literal["persons", "households", "dwellings"]
    dimensions: dict[str, str]


class Observation(StrictModel):
    territory_key: str
    series_code: str
    period: date
    value: Decimal | None
    status: Literal["unflagged_upstream", "estimated", "missing", "suppressed", "demo"]
    upstream_status: str = ""
    upstream_note: str = ""
    upstream_unit: str = ""
    upstream_unit_multiplier: str = ""


class Coverage(StrictModel):
    series_code: str
    period: date
    snapshot: date
    scheme: str
    territory_keys: list[str]


class Equation(StrictModel):
    """Explicit equality of disjoint cells; the total is never one of its parts."""

    name: str
    total: list[str]  # [territory_key, series_code, ISO period]
    parts: list[list[str]]
    dimension: Literal["territory", "sex", "age", "household_size", "occupancy"]
    tolerance: Decimal = Decimal(0)


class Change(StrictModel):
    event_id: str
    kind: Literal["merger", "split", "recode", "transfer"]
    effective_date: date
    source_url: str
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    description: str
    from_keys: list[str]
    to_keys: list[str]
    weight_basis: Literal["exact", "structural"]


class Evidence(StrictModel):
    name: str
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    url: str
    retrieved_at: str


class BoundarySource(StrictModel):
    evidence_name: str
    snapshot: date
    format: Literal["istat_shapefile", "fixture_geojson"]
    source_srid: Literal[32632, 4326]


class Bundle(StrictModel):
    version: Literal["m2/1.0"]
    dataset_id: Literal["istat_m2", "demo_m2"]
    is_demo: bool
    reference_period: date
    default_series: str
    attribution: str
    license_url: str
    license_evidence_name: str
    territories: list[Territory]
    series: list[Series]
    observations: list[Observation]
    coverage: list[Coverage]
    equations: list[Equation]
    changes: list[Change]
    evidence: list[Evidence]
    boundaries: list[BoundarySource]
    reconciliations: list[dict[str, Any]]
    boundary_repair_keys: list[str] = Field(default_factory=list)
    boundary_area_tolerance: float = Field(default=0, ge=0, le=1e-10)
    derive_parent_boundaries: bool = False


def validate_bundle(bundle: Bundle) -> dict[str, Any]:
    report: dict[str, Any] = {"checks": {}, "rows": len(bundle.observations)}

    def gate(name: str, condition: bool) -> None:
        report["checks"][name] = condition
        if not condition:
            raise QualityError(report)

    gate(
        "bounded_bundle",
        0 < len(bundle.observations) <= 2_000_000
        and 0 < len(bundle.territories) <= 100_000
        and 0 < len(bundle.coverage) <= 500,
    )
    gate(
        "source_status",
        bundle.is_demo == (bundle.dataset_id == "demo_m2")
        and all((o.status == "demo") == bundle.is_demo for o in bundle.observations),
    )
    territories = {t.key: t for t in bundle.territories}
    series = {s.code: s for s in bundle.series}
    gate("unique_territories", len(territories) == len(bundle.territories))
    gate("unique_series", len(series) == len(bundle.series))
    gate(
        "default_selection",
        any(
            c.series_code == bundle.default_series and c.period == bundle.reference_period
            for c in bundle.coverage
        ),
    )
    ranks = {"country": 0, "region": 1, "province": 2, "municipality": 3}
    intervals: dict[tuple[str, str], list[Territory]] = defaultdict(list)
    for t in bundle.territories:
        gate(
            "territorial_validity", t.valid_from <= t.snapshot < t.valid_to and bool(t.name.strip())
        )
        intervals[t.scheme, t.code].append(t)
        if t.parent_key is None:
            gate("territorial_root", t.level == "country")
        else:
            p = territories.get(t.parent_key)
            gate(
                "hierarchy",
                p is not None
                and p.scheme == t.scheme
                and p.snapshot == t.snapshot
                and ranks[p.level] < ranks[t.level]
                and p.valid_from <= t.valid_from
                and t.valid_to <= p.valid_to,
            )
    for group in intervals.values():
        ordered = sorted(group, key=lambda t: t.valid_from)
        gate(
            "territorial_overlap",
            all(a.valid_to <= b.valid_from for a, b in zip(ordered, ordered[1:], strict=False)),
        )
    values: dict[tuple[str, ...], Decimal | None] = {}
    actual: dict[tuple[str, date], set[str]] = defaultdict(set)
    for o in bundle.observations:
        key = (o.territory_key, o.series_code, o.period.isoformat())
        gate("unique_observations", key not in values)
        observation_territory = territories.get(o.territory_key)
        gate(
            "observation_context",
            observation_territory is not None
            and o.series_code in series
            and observation_territory.valid_from <= o.period < observation_territory.valid_to,
        )
        gate("null_status", (o.value is None) == (o.status in {"missing", "suppressed"}))
        if o.value is not None:
            gate(
                "numeric_range",
                o.value.is_finite()
                and 0 <= o.value < 10**14
                and o.value == o.value.to_integral_value(),
            )
        values[key] = o.value
        actual[o.series_code, o.period].add(o.territory_key)
    expected: set[tuple[str, date]] = set()
    for c in bundle.coverage:
        coverage_key = (c.series_code, c.period)
        gate("coverage_unique", coverage_key not in expected)
        expected.add(coverage_key)
        gate(
            "coverage_exact",
            len(c.territory_keys) == len(set(c.territory_keys))
            and set(c.territory_keys) == actual.get(coverage_key),
        )
        gate(
            "coverage_vintage",
            all(
                territories[k].scheme == c.scheme and territories[k].snapshot == c.snapshot
                for k in c.territory_keys
            ),
        )
    gate("coverage_complete", expected == set(actual))
    equation_names: set[str] = set()
    for eq in bundle.equations:
        gate(
            "equation_identity",
            eq.name not in equation_names
            and len(eq.total) == 3
            and len(eq.parts) >= 2
            and all(len(k) == 3 for k in eq.parts),
        )
        equation_names.add(eq.name)
        total = tuple(eq.total)
        parts = [tuple(k) for k in eq.parts]
        gate("disjoint_keys", len(parts) == len(set(parts)) and total not in parts)
        gate(
            "equation_cells",
            total in values
            and all(k in values for k in parts)
            and values[total] is not None
            and all(values[k] is not None for k in parts),
        )
        ts = series[total[1]]
        gate(
            "comparable_units_periods",
            all(
                series[k[1]].unit == ts.unit
                and k[2] == total[2]
                and territories[k[0]].scheme == territories[total[0]].scheme
                for k in parts
            ),
        )
        if eq.dimension == "territory":
            gate(
                "disjoint_territories",
                all(k[1] == total[1] and territories[k[0]].parent_key == total[0] for k in parts),
            )
        else:
            gate("same_territory", all(k[0] == total[0] for k in parts))
            dims = [series[k[1]].dimensions for k in parts]
            gate("partition_total", ts.dimensions.get(eq.dimension) == "TOTAL")
            gate(
                "partition_dimensions",
                all(
                    {d: v for d, v in item.items() if d != eq.dimension}
                    == {d: v for d, v in ts.dimensions.items() if d != eq.dimension}
                    for item in dims
                ),
            )
            labels = [d.get(eq.dimension) for d in dims]
            gate(
                "partition_categories",
                None not in labels and "TOTAL" not in labels and len(set(labels)) == len(labels),
            )
            if eq.dimension in {"age", "household_size"}:
                # Intervals are canonical half-open integer ranges, not arbitrary labels.
                ranges = sorted(tuple(map(int, str(label).split(":"))) for label in labels)
                start = 0 if eq.dimension == "age" else 1
                gate(
                    "partition_ranges",
                    all(len(r) == 2 and r[0] < r[1] for r in ranges)
                    and ranges[0][0] == start
                    and ranges[-1][1] == 1000
                    and all(a[1] == b[0] for a, b in zip(ranges, ranges[1:], strict=False)),
                )
            else:
                gate(
                    "partition_labels",
                    set(labels)
                    == ({"M", "F"} if eq.dimension == "sex" else {"occupied", "unoccupied"}),
                )
        gate("equation_tolerance", eq.tolerance.is_finite() and eq.tolerance >= 0)
        difference = sum((values[k] or Decimal(0) for k in parts), Decimal(0)) - (
            values[total] or 0
        )
        report["last_equation"] = eq.name
        gate("equation_reconciliation", abs(difference) <= eq.tolerance)
    evidence = {e.name: e for e in bundle.evidence}
    gate(
        "evidence_identity",
        len(evidence) == len(bundle.evidence) and bundle.license_evidence_name in evidence,
    )
    events: set[str] = set()
    for e in bundle.changes:
        gate("event_identity", e.event_id not in events)
        events.add(e.event_id)
        gate(
            "event_evidence",
            any(a.sha256 == e.evidence_sha256 and a.url == e.source_url for a in bundle.evidence),
        )
        gate(
            "event_members",
            bool(e.from_keys)
            and bool(e.to_keys)
            and len(e.from_keys) == len(set(e.from_keys))
            and len(e.to_keys) == len(set(e.to_keys))
            and all(k in territories for k in e.from_keys + e.to_keys),
        )
        gate(
            "event_time",
            all(territories[k].snapshot < e.effective_date for k in e.from_keys)
            and all(e.effective_date <= territories[k].snapshot for k in e.to_keys),
        )
        gate("event_level", len({territories[k].level for k in e.from_keys + e.to_keys}) == 1)
        counts = (len(e.from_keys), len(e.to_keys))
        gate(
            "event_cardinality",
            (e.kind == "merger" and counts[0] > 1 and counts[1] == 1)
            or (e.kind == "split" and counts[0] == 1 and counts[1] > 1)
            or (e.kind in {"recode", "transfer"} and counts == (1, 1)),
        )
        gate(
            "no_invented_weights", e.weight_basis == "structural" or e.kind in {"merger", "recode"}
        )
    gate(
        "boundary_sources",
        len({b.snapshot for b in bundle.boundaries}) == len(bundle.boundaries)
        and all(b.evidence_name in evidence for b in bundle.boundaries)
        and {b.snapshot for b in bundle.boundaries} == {t.snapshot for t in bundle.territories}
        and (bundle.is_demo or all(b.format == "istat_shapefile" for b in bundle.boundaries)),
    )
    gate(
        "reviewed_repairs",
        len(bundle.boundary_repair_keys) == len(set(bundle.boundary_repair_keys))
        and all(k in territories for k in bundle.boundary_repair_keys),
    )
    gate(
        "reconciliations",
        bool(bundle.reconciliations)
        and all(
            r.get("passed") is True and r.get("method") and r.get("evidence")
            for r in bundle.reconciliations
        ),
    )
    report["equations_checked"] = len(bundle.equations)
    return report


def reaggregate_exact(values: dict[str, Decimal], changes: list[Change]) -> dict[str, Decimal]:
    """Only complete, unambiguous exact merges/recodes; never estimate split weights."""
    result: dict[str, Decimal] = {}
    used: set[str] = set()
    for event in changes:
        if event.weight_basis != "exact" or event.kind not in {"merger", "recode"}:
            raise ValueError("A structural crosswalk cannot allocate demographic values")
        if (
            len(event.to_keys) != 1
            or not event.from_keys
            or len(set(event.from_keys)) != len(event.from_keys)
        ):
            raise ValueError("Invalid exact crosswalk")
        if any(k not in values or k in used for k in event.from_keys):
            raise ValueError("Incomplete or overlapping source coverage")
        used.update(event.from_keys)
        target = event.to_keys[0]
        if target in result:
            raise ValueError("Overlapping target coverage")
        result[target] = sum((values[k] for k in event.from_keys), Decimal(0))
    if used != set(values):
        raise ValueError("Crosswalk does not cover all input territories")
    return result
