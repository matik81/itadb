"""Resumable immutable national snapshots; completed never means publicly released."""

import hashlib
import json
import platform
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
from filelock import FileLock

from itadb.pipeline.storage import atomic_json, sha256_file
from itadb.synthesis.demography import person_model_metadata
from itadb.synthesis.national_audit import AUDIT_VERSION, audit_batch
from itadb.synthesis.national_generate import ALGORITHM_VERSION, generate_batch
from itadb.synthesis.national_models import (
    NationalInput,
    NationalReference,
    ResourceBudget,
    batches,
)
from itadb.synthesis.national_runtime import RunMonitor
from itadb.synthesis.provenance import _commit, implementation


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def file_inventory(directory: Path, exclude: str) -> dict[str, str]:
    return {
        p.relative_to(directory).as_posix(): sha256_file(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.relative_to(directory).as_posix() != exclude
    }


def check_files(directory: Path, expected: dict[str, str], exclude: str) -> None:
    if any(
        not (directory / name).resolve().is_relative_to(directory.resolve()) for name in expected
    ):
        raise ValueError("Artifact path escapes the snapshot")
    if file_inventory(directory, exclude) != expected:
        raise ValueError(
            "Artifact inventory/checksum differs; preserve evidence and use a new archive"
        )


def summarize(inputs: NationalInput, audits: list[dict[str, Any]]) -> dict[str, Any]:
    observed: Counter[tuple[str, str, int]] = Counter()
    actual: Counter[tuple[str, str, int]] = Counter()
    for m in inputs.municipalities:
        for sex, counts in [("M", m.male), ("F", m.female)]:
            observed.update({(m.region, sex, age): n for age, n in enumerate(counts) if n})
    for audit in audits:
        actual.update({(r, s, a): n for r, s, a, n in audit["region_cells"]})
    if observed != actual or sum(a["persons"] for a in audits) != sum(
        m.population for m in inputs.municipalities
    ):
        raise ValueError("Global geography and demographic reconciliation failed")
    return {
        "schema_version": "m4-report/1",
        "data_kind": "synthetic",
        "public_release": False,
        "reference_evidence_kind": inputs.evidence_kind,
        "persons": sum(a["persons"] for a in audits),
        "households": sum(a["households"] for a in audits),
        "unassigned_adults": sum(a["unassigned_adults"] for a in audits),
        "geography": {
            "municipalities": len(inputs.municipalities),
            "provinces": len({m.province for m in inputs.municipalities}),
            "regions": len({m.region for m in inputs.municipalities}),
        },
        "calibration": {
            "cells": len(inputs.municipalities) * 202,
            "max_absolute_error": 0,
            "total_variation_distance": 0,
            "geographic_reconciliation": "passed",
            "household_sizes": "exact_at_municipality",
        },
        "disclosure": {
            "quasi_identifiers": ["municipality", "sex", "age"],
            "cells_below_5": sum(a["disclosure"]["cells_below_5"] for a in audits),
            "persons_in_cells_below_5": sum(
                a["disclosure"]["persons_in_cells_below_5"] for a in audits
            ),
            "interpretation": "Diagnostica di rarità sintetica, non una garanzia di anonimato",
            "microdata_distribution": "blocked_pending_external_review",
        },
        "model_statistics": {
            key: sum(a["model_statistics"][key] for a in audits)
            for key in audits[0]["model_statistics"]
        },
        "out_of_calibration_validation": "not_available",
        "external_scientific_review": "not_performed",
        "statistical_acceptance": "experimental_not_certified",
        "assumptions": [
            "Classe 6+ rappresentata con 6 componenti; nessuna stima della coda",
            "Famiglie casuali nello stesso comune; nessuna parentela inferita",
            "Un adulto di riferimento per famiglia e tutti i minori assegnati",
            "Residuo adulto esplicito, non classificato come popolazione in convivenze",
            "Sesso/età e geografia calibrati: errore zero non è validazione esterna",
        ],
    }


def aggregate_package(inputs: NationalInput, audits: list[dict[str, Any]]) -> dict[str, Any]:
    """Only regional sex/decade marginals, with 90+ pooled; no household microdata."""
    counts: Counter[tuple[str, str, int]] = Counter()
    for audit in audits:
        for region, sex, age, n in audit["region_cells"]:
            counts[region, sex, min(age // 10 * 10, 90)] += n
    # No cellwise suppression: if this fixed complete table has a rare cell,
    # withhold the entire table to avoid reconstruction from additive margins.
    eligible = inputs.evidence_kind == "official_aggregates" and all(
        n >= 10 for n in counts.values()
    )
    return {
        "schema_version": "m4-distribution/1",
        "data_kind": "synthetic_aggregates",
        "public_release": False,
        "attribution": inputs.attribution,
        "population_reference": inputs.population_reference,
        "minimum_cell": 10,
        "eligible": eligible,
        "scope": "region_sex_decade_90plus_only",
        "cells": [
            {"region": r, "sex": s, "age_lower": a, "persons": n}
            for (r, s, a), n in sorted(counts.items())
        ]
        if eligible
        else [],
        "limitations": (
            "Soli margini già pubblici calibrati; non include relazioni o ID sintetici"
        ),
    }


def verify_national(directory: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    descriptor = manifest["descriptor"]
    identity = hashlib.sha256(canonical(descriptor)).hexdigest()
    if (
        manifest.get("run_id") != identity
        or directory.name != identity
        or manifest.get("status") != "completed_snapshot"
        or manifest.get("public_release") is not False
        or manifest.get("data_kind") != "synthetic"
        or descriptor.get("algorithm") != ALGORITHM_VERSION
        or descriptor.get("audit") != AUDIT_VERSION
    ):
        raise ValueError("Unsupported snapshot identity, version or publication state")
    check_files(directory, manifest["files"], "manifest.json")
    if sha256_file(directory / "input.json") != descriptor["input_sha256"]:
        raise ValueError("Snapshot input differs from identity")
    inputs = NationalInput.model_validate_json((directory / "input.json").read_bytes())
    budget = ResourceBudget.model_validate(descriptor["budget"])
    reference = NationalReference.model_validate(descriptor["reference"])
    model = {**person_model_metadata(inputs.population_reference), "schema_version": "m4-persons/1"}
    if descriptor["person_model"] != model:
        raise ValueError("Invalid person model")
    groups = batches(inputs, budget)
    expected_files = {"input.json", "report.json"} | {
        f"batch-{i:04d}/{name}"
        for i in range(len(groups))
        for name in ["persons.parquet", "households.parquet", "checkpoint.json"]
    }
    if reference.distribution == "local_microdata_aggregate_package":
        expected_files.add("distribution/aggregates.json")
    if set(manifest["files"]) != expected_files:
        raise ValueError("Unexpected snapshot file layout")
    audits = []
    p_offset = h_offset = 0
    for index, group in enumerate(groups):
        print(f"Audit indipendente {index + 1}/{len(groups)}", flush=True)
        folder = directory / f"batch-{index:04d}"
        checkpoint = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
        if checkpoint.get("run_id") != identity or checkpoint.get("batch") != index:
            raise ValueError("Checkpoint identity differs")
        check_files(folder, checkpoint["files"], "checkpoint.json")
        audit = audit_batch(folder, group, inputs.population_reference, p_offset, h_offset, budget)
        if canonical(audit) != canonical(checkpoint["audit"]):
            raise ValueError("Recomputed checkpoint audit differs")
        audits.append(audit)
        p_offset += audit["persons"]
        h_offset += audit["households"]
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if canonical(report) != canonical(summarize(inputs, audits)):
        raise ValueError("Recomputed global statistical/disclosure report differs")
    if reference.distribution == "local_microdata_aggregate_package":
        package = json.loads(
            (directory / "distribution" / "aggregates.json").read_text(encoding="utf-8")
        )
        if canonical(package) != canonical(aggregate_package(inputs, audits)):
            raise ValueError("Invalid aggregate distribution package")
    return manifest


def run_national(
    root: Path,
    inputs: NationalInput,
    reference: NationalReference | None = None,
    budget: ResourceBudget | None = None,
    *,
    stop_after_batches: int | None = None,
    reverse_order: bool = False,
) -> Path:
    """Fault-injection options are for reproducible recovery tests, never completed output."""
    started = time.monotonic()
    attempt = uuid4().hex
    log_path = root / "reports" / "m4" / f"attempt-{attempt}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(message: str) -> None:
        line = (
            f"{datetime.now(UTC).isoformat()} Sintesi nazionale {message}; "
            f"trascorsi {time.monotonic() - started:.1f}s"
        )
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    monitor: RunMonitor | None = None
    try:
        inputs = NationalInput.model_validate(inputs.model_dump())
        inputs.municipalities.sort(key=lambda m: (m.province, m.code))
        reference = NationalReference.model_validate(
            (reference or NationalReference()).model_dump()
        )
        budget = ResourceBudget.model_validate((budget or ResourceBudget()).model_dump())
        groups = batches(inputs, budget)
        input_bytes = canonical(inputs.model_dump())
        descriptor = {
            "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
            "reference": reference.model_dump(),
            "budget": budget.model_dump(),
            "algorithm": ALGORITHM_VERSION,
            "audit": AUDIT_VERSION,
            "person_model": {
                **person_model_metadata(inputs.population_reference),
                "schema_version": "m4-persons/1",
            },
            "seed_derivation": "sha256:itadb:m4:territorial-seed:1:base:municipality:first64bits",
            "implementation": implementation(root),
            "runtime": {
                "python": platform.python_version(),
                "duckdb": duckdb.__version__,
                "platform": platform.system(),
                "machine": platform.machine(),
            },
        }
        identity = hashlib.sha256(canonical(descriptor)).hexdigest()
        state = root / "state"
        state.mkdir(parents=True, exist_ok=True)
        target = root / "curated" / "m4" / identity
        target.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(state / f"m4-{identity}.lock"), timeout=60):
            if target.exists():
                emit("Retry: verifica dello snapshot completato")
                verify_national(target)
                emit("Esito: snapshot identico riutilizzato")
                return target
            stage = state / f"m4-work-{identity}"
            stage.mkdir(exist_ok=True)
            input_path = stage / "input.json"
            if input_path.exists() and input_path.read_bytes() != input_bytes:
                raise ValueError("Resume input corrupted")
            if not input_path.exists():
                input_path.write_bytes(input_bytes)
            monitor = RunMonitor(stage, budget, emit)
            monitor.start()
            records: dict[int, dict[str, Any]] = {}
            offsets = []
            p_offset = h_offset = 0
            for group in groups:
                offsets.append((p_offset, h_offset))
                p_offset += sum(m.population for m in group)
                h_offset += sum(m.household_total for m in group)
            order = list(range(len(groups)))
            if reverse_order:
                order.reverse()
            for done, index in enumerate(order, 1):
                group = groups[index]
                p_offset, h_offset = offsets[index]
                folder = stage / f"batch-{index:04d}"
                monitor.check(
                    f"Batch {done}/{len(groups)}; {sum(m.population for m in group):,} persone"
                )
                if folder.exists():
                    checkpoint = json.loads(
                        (folder / "checkpoint.json").read_text(encoding="utf-8")
                    )
                    if checkpoint.get("run_id") != identity or checkpoint.get("batch") != index:
                        raise ValueError("Checkpoint identity differs")
                    check_files(folder, checkpoint["files"], "checkpoint.json")
                    audit = audit_batch(
                        folder, group, inputs.population_reference, p_offset, h_offset, budget
                    )
                    if canonical(audit) != canonical(checkpoint["audit"]):
                        raise ValueError("Resume audit differs")
                    emit(f"Checkpoint {index + 1} verificato e riutilizzato")
                else:
                    temporary = stage / f"pending-{index:04d}-{attempt}"
                    # Interrupted temporary batches remain evidence outside the completed tree.
                    for orphan in stage.glob(f"pending-{index:04d}-*"):
                        orphan.rename(state / f"m4-interrupted-{orphan.name}")
                    generate_batch(
                        group,
                        inputs.population_reference,
                        temporary,
                        p_offset,
                        h_offset,
                        budget,
                        monitor.check,
                    )
                    monitor.check(f"Audit del batch {index + 1}")
                    audit = audit_batch(
                        temporary, group, inputs.population_reference, p_offset, h_offset, budget
                    )
                    atomic_json(
                        temporary / "checkpoint.json",
                        {
                            "batch": index,
                            "run_id": identity,
                            "audit": audit,
                            "files": file_inventory(temporary, "checkpoint.json"),
                        },
                    )
                    temporary.rename(folder)
                records[index] = audit
                monitor.check(f"Completati {done}/{len(groups)} batch; audit passato")
                if stop_after_batches is not None and done >= stop_after_batches:
                    raise InterruptedError("Intentional checkpoint recovery exercise")
            audits = [records[i] for i in range(len(groups))]
            atomic_json(stage / "report.json", summarize(inputs, audits))
            if reference.distribution == "local_microdata_aggregate_package":
                atomic_json(
                    stage / "distribution" / "aggregates.json", aggregate_package(inputs, audits)
                )
            monitor.check("Riconciliazione globale e valutazione disclosure concluse")
            measurements = monitor.close()
            monitor = None
            if not measurements["budget_passed"]:
                raise RuntimeError("Measured resource budget exceeded")
            measurements["throughput_persons_per_second"] = (
                sum(a["persons"] for a in audits) / measurements["elapsed_seconds"]
            )
            atomic_json(
                root / "reports" / "m4" / f"measurement-{attempt}.json",
                {
                    "run_id": identity,
                    "attempt": attempt,
                    **measurements,
                },
            )
            atomic_json(
                stage / "manifest.json",
                {
                    "run_id": identity,
                    "status": "completed_snapshot",
                    "data_kind": "synthetic",
                    "public_release": False,
                    "descriptor": descriptor,
                    "git": _commit(),
                    "files": file_inventory(stage, "manifest.json"),
                },
            )
            stage.rename(target)
            emit(f"Esito: completato {sum(a['persons'] for a in audits):,} persone; {target}")
            return target
    except Exception as error:
        if monitor:
            atomic_json(root / "reports" / "m4" / f"measurement-{attempt}.json", monitor.close())
        atomic_json(
            root / "quarantine" / f"m4-{attempt}.json",
            {
                "published": False,
                "error_code": type(error).__name__,
            },
        )
        emit(f"Esito: {type(error).__name__}; checkpoint ed evidenze conservati")
        raise
