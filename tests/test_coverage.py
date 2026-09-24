from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from itadb.pipeline.coverage import Bundle, reaggregate_exact, validate_bundle
from itadb.pipeline.validate import QualityError


def test_complete_disjoint_fixture(coverage_bundle: tuple[Bundle, Path]) -> None:
    report = validate_bundle(coverage_bundle[0])
    assert all(report["checks"].values())
    assert report["equations_checked"] == 22


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate",
        "missing",
        "wrong_value",
        "wrong_period",
        "wrong_vintage",
        "overlap_age",
        "overlap_total",
        "negative",
        "nan",
        "missing_zero",
        "cycle",
        "interval_overlap",
        "split_weight",
        "event_time",
        "event_duplicate",
        "unknown_source",
        "mixed_demo",
    ],
)
def test_invalid_evidence_fails_closed(coverage_bundle: tuple[Bundle, Path], problem: str) -> None:
    b = coverage_bundle[0].model_copy(deep=True)
    if problem == "duplicate":
        b.observations.append(b.observations[0])
    elif problem == "missing":
        b.observations.pop()
    elif problem == "wrong_value":
        b.observations[0].value += 1
    elif problem == "wrong_period":
        b.observations[0].period = date(2019, 1, 1)
    elif problem == "wrong_vintage":
        b.coverage[0].scheme = "OTHER"
    elif problem == "overlap_age":
        b.series[-1].dimensions["age"] = "14:1000"
    elif problem == "overlap_total":
        b.equations[0].parts[0] = b.equations[0].total
    elif problem == "negative":
        b.observations[0].value = Decimal(-1)
    elif problem == "nan":
        b.observations[0].value = Decimal("NaN")
    elif problem == "missing_zero":
        b.observations[0].status = "missing"
    elif problem == "cycle":
        b.territories[1].parent_key = b.territories[1].key
    elif problem == "interval_overlap":
        b.territories.append(b.territories[1].model_copy(update={"key": "duplicate_interval"}))
    elif problem == "split_weight":
        b.changes[1].weight_basis = "exact"
    elif problem == "event_time":
        b.changes[0].effective_date = date(2019, 1, 1)
    elif problem == "event_duplicate":
        b.changes.append(b.changes[0])
    elif problem == "unknown_source":
        b.changes[0].evidence_sha256 = "f" * 64
    elif problem == "mixed_demo":
        b.observations[0].status = "unflagged_upstream"
    with pytest.raises((QualityError, ValueError)):
        validate_bundle(b)


def test_exact_merge_conserves_counts_and_refuses_structural_split(
    coverage_bundle: tuple[Bundle, Path],
) -> None:
    merge, split = coverage_bundle[0].changes
    assert reaggregate_exact(
        dict(zip(merge.from_keys, [Decimal(7), Decimal(9)], strict=True)), [merge]
    ) == {merge.to_keys[0]: Decimal(16)}
    with pytest.raises(ValueError, match="structural"):
        reaggregate_exact({split.from_keys[0]: Decimal(16)}, [split])
    with pytest.raises(ValueError, match="Incomplete"):
        reaggregate_exact({merge.from_keys[0]: Decimal(7)}, [merge])
    with pytest.raises(ValueError, match="all input"):
        reaggregate_exact(
            {**dict.fromkeys(merge.from_keys, Decimal(1)), "unmapped": Decimal(2)}, [merge]
        )
