"""Immutable citizenship enrichment with bounded batches, recovery and independent audit."""

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
from itadb.synthesis.citizenship_audit import AUDIT_VERSION, audit_citizenship_batch
from itadb.synthesis.citizenship_generate import ALGORITHM_VERSION, enrich_batch
from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipReference
from itadb.synthesis.national_models import NationalInput, ResourceBudget, batches
from itadb.synthesis.national_runner import canonical, check_files, file_inventory, verify_national
from itadb.synthesis.national_runtime import RunMonitor
from itadb.synthesis.runner import _commit, implementation


def snapshot_files(count: int) -> set[str]:
    return {"input.json", "report.json"} | {
        f"batch-{i:04d}/{name}"
        for i in range(count)
        for name in ["persons.parquet", "households.parquet", "checkpoint.json"]
    }


def summarize_citizenship(inputs: CitizenshipInput, audits: list[dict[str, Any]]) -> dict[str, Any]:
    countries: Counter[str] = Counter()
    for audit in audits:
        countries.update(audit["country_totals"])
    expected: Counter[str] = Counter()
    for municipality in inputs.municipalities:
        expected.update({code: sum(n) for code, n in municipality.countries.items()})
    if countries != expected or sum(a["persons"] for a in audits) != sum(expected.values()):
        raise ValueError("Global citizenship reconciliation failed")
    return {
        "schema_version": "citizenship-report/1",
        "data_kind": "synthetic",
        "public_release": False,
        "reference_evidence_kind": inputs.evidence_kind,
        "persons": sum(countries.values()),
        "italian_persons": countries["100"],
        "foreign_persons": sum(n for c, n in countries.items() if c != "100"),
        "stateless_persons": countries["999"],
        "country_totals": dict(sorted(countries.items())),
        "municipalities": len(inputs.municipalities),
        "calibration": {
            "str_cells_checked": sum(a["str_cells_checked"] for a in audits),
            "rcs_nonzero_cells_checked": sum(a["rcs_nonzero_cells_checked"] for a in audits),
            "max_absolute_error": 0,
            "all_base_attributes": "unchanged",
            "household_files": "byte_identical",
        },
        "disclosure": {
            "quasi_identifiers": ["municipality", "sex", "age", "citizenship_code"],
            "cells_below_5": sum(a["disclosure"]["cells_below_5"] for a in audits),
            "persons_in_cells_below_5": sum(
                a["disclosure"]["persons_in_cells_below_5"] for a in audits
            ),
            "microdata_distribution": "blocked_pending_external_review",
            "interpretation": "Rarità sintetica, non una garanzia di anonimato",
        },
        "age_specific_country_joint": "synthetic_not_observed",
        "household_citizenship_relations": "not_calibrated",
        "external_scientific_review": "not_performed",
        "assumptions": [
            "Scambiabilità delle singole cittadinanze tra stranieri dello stesso comune e sesso",
            "Nessuna trasmissione della cittadinanza da genitori, partner o paese di nascita",
            "100: cittadinanza italiana; 999: apolidia; cittadinanza italiana prevalente se doppia",
            "Associazione età–singola cittadinanza sintetica; soli margini STR/RCS osservati",
        ],
    }


def base_groups(base: Path, budget: ResourceBudget) -> tuple[NationalInput, list[list[str]]]:
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    inputs = NationalInput.model_validate_json((base / "input.json").read_bytes())
    groups = batches(inputs, ResourceBudget.model_validate(manifest["descriptor"]["budget"]))
    if any(sum(m.population for m in g) > budget.max_batch_population for g in groups):
        raise ValueError("Base partition exceeds citizenship batch budget")
    return inputs, [[m.code for m in g] for g in groups]


def verify_citizenship(directory: Path, base: Path) -> dict[str, Any]:
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
        or descriptor.get("persons_schema") != "citizenship-persons/1"
        or descriptor.get("priority_order") != ["sex_age", "geography", "households", "citizenship"]
        or descriptor.get("seed_derivation")
        != "sha256:itadb:citizenship:1:1701:municipality:first64bits"
        or descriptor.get("base_run_id") != base.name
        or descriptor.get("base_manifest_sha256") != sha256_file(base / "manifest.json")
    ):
        raise ValueError("Invalid citizenship snapshot identity, version or base")
    CitizenshipReference.model_validate(descriptor["reference"])
    budget = ResourceBudget.model_validate(descriptor["budget"])
    check_files(directory, manifest["files"], "manifest.json")
    if sha256_file(directory / "input.json") != descriptor["input_sha256"]:
        raise ValueError("Citizenship input differs from identity")
    inputs = CitizenshipInput.model_validate_json((directory / "input.json").read_bytes())
    original, groups = base_groups(base, budget)
    inputs.check_base(original)
    expected = snapshot_files(len(groups))
    if set(manifest["files"]) != expected:
        raise ValueError("Unexpected citizenship snapshot layout")
    print("Audit della base M4", flush=True)
    verify_national(base)
    by_code = {m.code: m for m in inputs.municipalities}
    audits = []
    for index, group in enumerate(groups):
        print(f"Audit cittadinanza {index + 1}/{len(groups)}", flush=True)
        folder = directory / f"batch-{index:04d}"
        checkpoint = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
        if checkpoint.get("run_id") != identity or checkpoint.get("batch") != index:
            raise ValueError("Citizenship checkpoint identity differs")
        check_files(folder, checkpoint["files"], "checkpoint.json")
        audit = audit_citizenship_batch(
            folder,
            base / folder.name,
            [by_code[c] for c in group],
            int(inputs.population_reference[:4]),
            budget,
        )
        if canonical(audit) != canonical(checkpoint["audit"]):
            raise ValueError("Recomputed citizenship checkpoint differs")
        audits.append(audit)
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if canonical(report) != canonical(summarize_citizenship(inputs, audits)):
        raise ValueError("Recomputed citizenship report differs")
    return manifest


def run_citizenship(
    root: Path,
    base: Path,
    inputs: CitizenshipInput,
    reference: CitizenshipReference | None = None,
    budget: ResourceBudget | None = None,
    *,
    stop_after_batches: int | None = None,
    reverse_order: bool = False,
) -> Path:
    started = time.monotonic()
    attempt = uuid4().hex
    identity: str | None = None
    report_root = root / "reports" / "citizenship"
    report_root.mkdir(parents=True, exist_ok=True)
    log = report_root / f"attempt-{attempt}.log"

    def emit(message: str) -> None:
        line = (
            f"{datetime.now(UTC).isoformat()} Cittadinanza {message}; "
            f"trascorsi {time.monotonic() - started:.1f}s"
        )
        print(line, flush=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    monitor: RunMonitor | None = None
    try:
        inputs = CitizenshipInput.model_validate(inputs.model_dump())
        inputs.municipalities.sort(key=lambda m: m.code)
        reference = CitizenshipReference.model_validate(
            (reference or CitizenshipReference()).model_dump()
        )
        budget = ResourceBudget.model_validate((budget or ResourceBudget()).model_dump())
        original, groups = base_groups(base, budget)
        inputs.check_base(original)
        input_bytes = canonical(inputs.model_dump())
        descriptor = {
            "base_run_id": base.name,
            "base_manifest_sha256": sha256_file(base / "manifest.json"),
            "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
            "reference": reference.model_dump(),
            "budget": budget.model_dump(),
            "algorithm": ALGORITHM_VERSION,
            "audit": AUDIT_VERSION,
            "persons_schema": "citizenship-persons/1",
            "priority_order": ["sex_age", "geography", "households", "citizenship"],
            "seed_derivation": "sha256:itadb:citizenship:1:1701:municipality:first64bits",
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
        target = root / "curated" / "citizenship" / identity
        target.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(state / f"citizenship-{identity}.lock"), timeout=60):
            if target.exists():
                emit("Retry: rilettura dello snapshot completato")
                verify_citizenship(target, base)
                emit("Esito: snapshot identico riutilizzato")
                return target
            stage = state / f"citizenship-work-{identity}"
            stage.mkdir(exist_ok=True)
            input_path = stage / "input.json"
            if input_path.exists() and input_path.read_bytes() != input_bytes:
                raise ValueError("Citizenship resume input corrupted")
            if not input_path.exists():
                input_path.write_bytes(input_bytes)
            monitor = RunMonitor(stage, budget, emit)
            monitor.start()
            monitor.check("verifica completa dello snapshot M4 di partenza")
            verify_national(base)
            by_code = {m.code: m for m in inputs.municipalities}
            audits = {}
            order = list(range(len(groups)))
            if reverse_order:
                order.reverse()
            for done, index in enumerate(order, 1):
                group = [by_code[c] for c in groups[index]]
                folder = stage / f"batch-{index:04d}"
                base_folder = base / folder.name
                population = sum(sum(n) for m in group for n in m.countries.values())
                monitor.check(f"batch {done}/{len(groups)}; {population:,} persone")
                if folder.exists():
                    checkpoint = json.loads(
                        (folder / "checkpoint.json").read_text(encoding="utf-8")
                    )
                    if checkpoint.get("run_id") != identity or checkpoint.get("batch") != index:
                        raise ValueError("Citizenship checkpoint identity differs")
                    check_files(folder, checkpoint["files"], "checkpoint.json")
                    audit = audit_citizenship_batch(
                        folder, base_folder, group, int(inputs.population_reference[:4]), budget
                    )
                    if canonical(audit) != canonical(checkpoint["audit"]):
                        raise ValueError("Citizenship resume audit differs")
                    emit(f"checkpoint {index + 1} verificato e riutilizzato")
                else:
                    for orphan in stage.glob(f"pending-{index:04d}-*"):
                        orphan.rename(state / f"citizenship-interrupted-{orphan.name}")
                    pending = stage / f"pending-{index:04d}-{attempt}"
                    enrich_batch(
                        base_folder,
                        pending,
                        group,
                        int(inputs.population_reference[:4]),
                        budget,
                        monitor.check,
                    )
                    monitor.check(f"audit indipendente batch {index + 1}")
                    audit = audit_citizenship_batch(
                        pending, base_folder, group, int(inputs.population_reference[:4]), budget
                    )
                    atomic_json(
                        pending / "checkpoint.json",
                        {
                            "run_id": identity,
                            "batch": index,
                            "audit": audit,
                            "files": file_inventory(pending, "checkpoint.json"),
                        },
                    )
                    pending.rename(folder)
                audits[index] = audit
                monitor.check(f"completati {done}/{len(groups)} batch; vincoli verificati")
                if stop_after_batches is not None and done >= stop_after_batches:
                    raise InterruptedError("Intentional citizenship recovery exercise")
            atomic_json(
                stage / "report.json",
                summarize_citizenship(inputs, [audits[i] for i in range(len(groups))]),
            )
            monitor.check("riconciliazione globale e valutazione disclosure completate")
            measurement = monitor.close()
            monitor = None
            atomic_json(
                report_root / f"measurement-{attempt}.json",
                {"run_id": identity, "attempt": attempt, **measurement},
            )
            if not measurement["budget_passed"]:
                raise RuntimeError("Citizenship resource budget exceeded")
            files = file_inventory(stage, "manifest.json")
            if set(files) != snapshot_files(len(groups)):
                raise ValueError("Unexpected citizenship staging artifacts")
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
            measurement = monitor.close()
            atomic_json(
                report_root / f"measurement-{attempt}.json",
                {"run_id": identity, "attempt": attempt, **measurement},
            )
        atomic_json(
            root / "quarantine" / f"citizenship-{attempt}.json",
            {
                "run_id": identity,
                "attempt": attempt,
                "published": False,
                "error_code": type(error).__name__,
            },
        )
        emit(f"Esito: {type(error).__name__}; evidenze conservate")
        raise
