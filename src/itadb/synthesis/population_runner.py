"""Current immutable population snapshots, with citizenship before households."""

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
from itadb.synthesis.national_models import ResourceBudget, batches
from itadb.synthesis.national_runner import canonical, check_files, file_inventory, summarize
from itadb.synthesis.national_runtime import RunMonitor
from itadb.synthesis.population_audit import AUDIT_VERSION, audit_population_batch
from itadb.synthesis.population_generate import ALGORITHM_VERSION, generate_population_batch
from itadb.synthesis.population_models import PRIORITY_ORDER, PopulationInput, PopulationReference
from itadb.synthesis.runner import _commit, implementation


def snapshot_files(count: int) -> set[str]:
    return {"input.json", "report.json"} | {
        f"batch-{i:04d}/{name}"
        for i in range(count)
        for name in [
            "individuals.parquet",
            "persons.parquet",
            "households.parquet",
            "checkpoint.json",
        ]
    }


def summarize_population(inputs: PopulationInput, audits: list[dict[str, Any]]) -> dict[str, Any]:
    report = summarize(inputs.national, [a["demography"] for a in audits])
    countries: Counter[str] = Counter()
    expected: Counter[str] = Counter()
    for audit in audits:
        countries.update(audit["country_totals"])
    for m in inputs.citizenship.municipalities:
        expected.update({c: sum(n) for c, n in m.countries.items()})
    if countries != expected or sum(countries.values()) != report["persons"]:
        raise ValueError("Global citizenship reconciliation failed")
    report.update(
        {
            "schema_version": "population-report/1",
            "fidelity_version": 5,
            "priority_order": list(PRIORITY_ORDER),
            "execution_order": list(PRIORITY_ORDER),
            "country_totals": dict(sorted(countries.items())),
            "italian_persons": countries["100"],
            "foreign_persons": sum(n for c, n in countries.items() if c != "100"),
            "stateless_persons": countries["999"],
            "age_specific_country_joint": "synthetic_not_observed",
            "household_age_citizenship_relations": "random_constrained_not_calibrated",
        }
    )
    report["calibration"].update(
        {
            "str_cells_checked": sum(a["str_cells_checked"] for a in audits),
            "rcs_nonzero_cells_checked": sum(a["rcs_nonzero_cells_checked"] for a in audits),
            "first_three_stages_unchanged_by_households": True,
        }
    )
    report["disclosure"].update(
        {
            "quasi_identifiers": ["municipality", "sex", "age", "citizenship_code"],
            "cells_below_5": sum(a["disclosure"]["cells_below_5"] for a in audits),
            "persons_in_cells_below_5": sum(
                a["disclosure"]["persons_in_cells_below_5"] for a in audits
            ),
        }
    )
    report["assumptions"] += [
        "Cittadinanza fissata prima delle famiglie; incrocio età–singola cittadinanza sintetico",
        "Composizione familiare per età/cittadinanza casuale vincolata e non calibrata",
        "100: Italia; 999: apolidia, inclusa negli stranieri; una sola categoria statistica",
    ]
    return report


def person_model(inputs: PopulationInput) -> dict[str, Any]:
    return {
        **person_model_metadata(inputs.national.population_reference),
        "schema_version": "population-persons/1",
        "pre_household_schema": "population-individuals/1",
    }


def verify_population(directory: Path) -> dict[str, Any]:
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
        or descriptor.get("priority_order") != list(PRIORITY_ORDER)
        or descriptor.get("execution_order") != list(PRIORITY_ORDER)
    ):
        raise ValueError("Invalid population identity, version or stage order")
    PopulationReference.model_validate(descriptor["reference"])
    budget = ResourceBudget.model_validate(descriptor["budget"])
    check_files(directory, manifest["files"], "manifest.json")
    if sha256_file(directory / "input.json") != descriptor["input_sha256"]:
        raise ValueError("Population input differs from identity")
    inputs = PopulationInput.model_validate_json((directory / "input.json").read_bytes())
    if descriptor.get("person_model") != person_model(inputs):
        raise ValueError("Invalid population person model")
    groups = batches(inputs.national, budget)
    if set(manifest["files"]) != snapshot_files(len(groups)):
        raise ValueError("Unexpected population snapshot layout")
    citizenships = {m.code: m for m in inputs.citizenship.municipalities}
    audits = []
    p_offset = h_offset = 0
    for index, group in enumerate(groups):
        print(
            f"Audit popolazione {index + 1}/{len(groups)}: primi tre passaggi e famiglie",
            flush=True,
        )
        folder = directory / f"batch-{index:04d}"
        checkpoint = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
        if checkpoint.get("run_id") != identity or checkpoint.get("batch") != index:
            raise ValueError("Population checkpoint identity differs")
        check_files(folder, checkpoint["files"], "checkpoint.json")
        audit = audit_population_batch(
            folder,
            group,
            [citizenships[m.code] for m in group],
            inputs.national.population_reference,
            p_offset,
            h_offset,
            budget,
        )
        if canonical(audit) != canonical(checkpoint["audit"]):
            raise ValueError("Recomputed population checkpoint differs")
        audits.append(audit)
        p_offset += audit["demography"]["persons"]
        h_offset += audit["demography"]["households"]
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if canonical(report) != canonical(summarize_population(inputs, audits)):
        raise ValueError("Recomputed population report differs")
    return manifest


def run_population(
    root: Path,
    inputs: PopulationInput,
    reference: PopulationReference | None = None,
    budget: ResourceBudget | None = None,
    *,
    stop_after_batches: int | None = None,
    reverse_order: bool = False,
) -> Path:
    started = time.monotonic()
    attempt = uuid4().hex
    identity: str | None = None
    report_root = root / "reports" / "population"
    report_root.mkdir(parents=True, exist_ok=True)
    log = report_root / f"attempt-{attempt}.log"

    def emit(message: str) -> None:
        line = (
            f"{datetime.now(UTC).isoformat()} Popolazione {message}; "
            f"trascorsi {time.monotonic() - started:.1f}s"
        )
        print(line, flush=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    monitor: RunMonitor | None = None
    try:
        inputs = PopulationInput.model_validate(inputs.model_dump())
        inputs.national.municipalities.sort(key=lambda m: (m.province, m.code))
        inputs.citizenship.municipalities.sort(key=lambda m: m.code)
        reference = PopulationReference.model_validate(
            (reference or PopulationReference()).model_dump()
        )
        budget = ResourceBudget.model_validate((budget or ResourceBudget()).model_dump())
        groups = batches(inputs.national, budget)
        input_bytes = canonical(inputs.model_dump())
        descriptor = {
            "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
            "reference": reference.model_dump(),
            "budget": budget.model_dump(),
            "algorithm": ALGORITHM_VERSION,
            "audit": AUDIT_VERSION,
            "priority_order": list(PRIORITY_ORDER),
            "execution_order": list(PRIORITY_ORDER),
            "person_model": person_model(inputs),
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
        target = root / "curated" / "population" / identity
        target.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(state / f"population-{identity}.lock"), timeout=60):
            if target.exists():
                emit("Retry: audit dello snapshot completato")
                verify_population(target)
                emit("Esito: snapshot identico riutilizzato")
                return target
            stage = state / f"population-work-{identity}"
            stage.mkdir(exist_ok=True)
            input_path = stage / "input.json"
            if input_path.exists() and input_path.read_bytes() != input_bytes:
                raise ValueError("Population resume input corrupted")
            if not input_path.exists():
                input_path.write_bytes(input_bytes)
            monitor = RunMonitor(stage, budget, emit)
            monitor.start()
            offsets = []
            p_offset = h_offset = 0
            for group in groups:
                offsets.append((p_offset, h_offset))
                p_offset += sum(m.population for m in group)
                h_offset += sum(m.household_total for m in group)
            citizenships = {m.code: m for m in inputs.citizenship.municipalities}
            records = {}
            order = list(range(len(groups)))
            if reverse_order:
                order.reverse()
            for done, index in enumerate(order, 1):
                group = groups[index]
                citizens = [citizenships[m.code] for m in group]
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
                        raise ValueError("Population checkpoint identity differs")
                    check_files(folder, checkpoint["files"], "checkpoint.json")
                    audit = audit_population_batch(
                        folder,
                        group,
                        citizens,
                        inputs.national.population_reference,
                        p_offset,
                        h_offset,
                        budget,
                    )
                    if canonical(audit) != canonical(checkpoint["audit"]):
                        raise ValueError("Population resume audit differs")
                    emit(f"Checkpoint {index + 1} verificato e riutilizzato")
                else:
                    for orphan in stage.glob(f"pending-{index:04d}-*"):
                        orphan.rename(state / f"population-interrupted-{orphan.name}")
                    pending = stage / f"pending-{index:04d}-{attempt}"
                    generate_population_batch(
                        group,
                        citizens,
                        inputs.national.population_reference,
                        pending,
                        p_offset,
                        h_offset,
                        budget,
                        monitor.check,
                    )
                    monitor.check(f"Audit indipendente del batch {index + 1}")
                    audit = audit_population_batch(
                        pending,
                        group,
                        citizens,
                        inputs.national.population_reference,
                        p_offset,
                        h_offset,
                        budget,
                    )
                    atomic_json(
                        pending / "checkpoint.json",
                        {
                            "batch": index,
                            "run_id": identity,
                            "audit": audit,
                            "files": file_inventory(pending, "checkpoint.json"),
                        },
                    )
                    pending.rename(folder)
                records[index] = audit
                monitor.check(f"Completati {done}/{len(groups)} batch; quattro passaggi verificati")
                if stop_after_batches is not None and done >= stop_after_batches:
                    raise InterruptedError("Intentional population recovery exercise")
            atomic_json(
                stage / "report.json",
                summarize_population(inputs, [records[i] for i in range(len(groups))]),
            )
            monitor.check("Riconciliazione globale completata")
            measurement = monitor.close()
            monitor = None
            atomic_json(
                report_root / f"measurement-{attempt}.json",
                {
                    "run_id": identity,
                    "attempt": attempt,
                    **measurement,
                },
            )
            if not measurement["budget_passed"]:
                raise RuntimeError("Population resource budget exceeded")
            files = file_inventory(stage, "manifest.json")
            if set(files) != snapshot_files(len(groups)):
                raise ValueError("Unexpected population staging artifacts")
            atomic_json(
                stage / "manifest.json",
                {
                    "run_id": identity,
                    "status": "completed_snapshot",
                    "data_kind": "synthetic",
                    "public_release": False,
                    "descriptor": descriptor,
                    "git": _commit(),
                    "files": files,
                },
            )
            stage.rename(target)
            emit(f"Esito: completato; {target}")
            return target
    except Exception as error:
        if monitor:
            atomic_json(
                report_root / f"measurement-{attempt}.json",
                {
                    "run_id": identity,
                    "attempt": attempt,
                    **monitor.close(),
                },
            )
        atomic_json(
            root / "quarantine" / f"population-{attempt}.json",
            {
                "run_id": identity,
                "attempt": attempt,
                "published": False,
                "error_code": type(error).__name__,
            },
        )
        emit(f"Esito: {type(error).__name__}; evidenze conservate")
        raise
