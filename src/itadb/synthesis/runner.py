"""Immutable local experiments; completion is never a public microdata release."""

import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
from filelock import FileLock

from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError
from itadb.synthesis.audit import AUDIT_VERSION, audit
from itadb.synthesis.generate import ALGORITHM_VERSION, check_feasibility, generate
from itadb.synthesis.models import Experiment, PilotInput

REPORT_VERSION = "m3-report/2"


def implementation(root: Path) -> dict[str, str]:
    """Archive the executable source and dependency lock, including uncommitted changes."""
    source = Path(__file__).resolve().parents[1]
    files = sorted(source.rglob("*.py"))
    lock = Path("uv.lock")
    if not lock.is_file():
        raise ValueError("Run the pilot from the repository root with uv.lock")
    result = {}
    for path in [*files, lock]:
        _, digest = archive_file(path, root / "raw")
        result[path.relative_to(source).as_posix() if path != lock else "uv.lock"] = digest
    return result


def _commit() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = (
            subprocess.run(
                ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
            ).stdout
            != ""
        )
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"revision": None, "dirty": None}


def summarize(replicates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for size in sorted({r["large_household_size"] for r in replicates}):
        group = [r for r in replicates if r["large_household_size"] == size]
        metrics = {
            "unassigned_adults": [r["audit"]["unassigned_adults"] for r in group],
            **{
                name: [r["audit"]["model_statistics"][name] for r in group]
                for name in group[0]["audit"]["model_statistics"]
            },
        }
        result.append(
            {
                "large_household_size": size,
                "replicates": len(group),
                "metrics": {
                    name: {
                        "min": min(values),
                        "max": max(values),
                        "mean": statistics.mean(values),
                        "sample_sd": statistics.stdev(values),
                    }
                    for name, values in metrics.items()
                },
            }
        )
    return result


def verify_run(directory: Path) -> dict[str, Any]:
    """Fail closed on missing/tampered files and independently recompute every audit."""
    manifest: dict[str, Any] = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    descriptor = manifest["descriptor"]
    if descriptor.get("algorithm") != ALGORITHM_VERSION or descriptor.get("audit") != AUDIT_VERSION:
        raise ValueError(
            "Unsupported experiment version; verify historical runs with their recorded "
            "implementation. Generate a new run without overwriting existing evidence."
        )
    run_id = hashlib.sha256(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        manifest["run_id"] != run_id
        or directory.name != run_id
        or manifest["status"] != "completed_experiment"
    ):
        raise ValueError("Invalid experiment identity or state")
    files = manifest["files"]
    actual = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and p != directory / "manifest.json"
    }
    if set(files) != actual:
        raise ValueError("Experiment file inventory differs")
    for name, checksum in files.items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()) or sha256_file(path) != checksum:
            raise ValueError("Experiment artifact integrity failed")
    inputs = PilotInput.model_validate_json((directory / "input.json").read_bytes())
    experiment = Experiment.model_validate(descriptor["experiment"])
    if files["input.json"] != descriptor["input_sha256"]:
        raise ValueError("Input differs from experiment identity")
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if (
        manifest.get("data_kind") != "synthetic"
        or manifest.get("public_release") is not False
        or report.get("data_kind") != "synthetic"
        or report.get("public_release") is not False
        or report.get("schema_version") != REPORT_VERSION
        or report.get("out_of_calibration_validation") != "not_available"
        or report.get("external_scientific_review") != "not_performed"
        or report.get("microdata_distribution")
        != "blocked_pending_disclosure_and_scientific_review"
    ):
        raise ValueError("Experimental output must not claim observed data or public approval")
    expected = {(s, z) for s in experiment.seeds for z in experiment.large_household_sizes}
    replicates = report["replicates"]
    if (
        len(replicates) != len(expected)
        or {(r["seed"], r["large_household_size"]) for r in replicates} != expected
    ):
        raise ValueError("Missing or duplicate experiment replicates")
    for replicate in replicates:
        subdir = directory / f"size-{replicate['large_household_size']}-seed-{replicate['seed']}"
        result = audit(subdir, inputs, replicate["large_household_size"])
        if result != replicate["audit"]:
            raise ValueError("Independent audit differs from recorded report")
    if report["uncertainty"] != summarize(replicates):
        raise ValueError("Uncertainty report differs")
    return manifest


def run_pilot(root: Path, inputs: PilotInput, experiment: Experiment) -> Path:
    started = time.monotonic()
    attempt = uuid4().hex
    log_path = root / "reports" / "m3" / f"attempt-{attempt}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    run_id: str | None = None

    def progress(message: str) -> None:
        line = (
            f"{datetime.now(UTC).isoformat()} M3 {message}; "
            f"trascorsi {time.monotonic() - started:.1f}s"
        )
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    try:
        progress("Verifica input e fattibilità")
        # Revalidate even callers that used unchecked model construction/copy.
        inputs = PilotInput.model_validate(inputs.model_dump())
        experiment = Experiment.model_validate(experiment.model_dump())
        for size in experiment.large_household_sizes:
            check_feasibility(inputs.calibration, size)
        # Hash the exact bytes before staging: successful retries need no new attempt directory.
        input_bytes = (
            json.dumps(inputs.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        descriptor = {
            "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
            "experiment": experiment.model_dump(),
            "algorithm": ALGORITHM_VERSION,
            "audit": AUDIT_VERSION,
            "implementation": implementation(root),
            "runtime": {
                "python": platform.python_version(),
                "duckdb": duckdb.__version__,
                "platform": platform.system(),
                "machine": platform.machine(),
            },
        }
        run_id = hashlib.sha256(
            json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        target = root / "curated" / "m3" / run_id
        target.parent.mkdir(parents=True, exist_ok=True)
        state = root / "state"
        state.mkdir(parents=True, exist_ok=True)
        with FileLock(str(state / f"m3-{run_id}.lock"), timeout=60):
            if target.exists():
                progress("Retry: verifica integrale degli artefatti esistenti")
                verify_run(target)
                progress("Esito: esperimento identico riutilizzato")
                return target
            stage = state / f"m3-attempt-{attempt}"
            stage.mkdir()
            (stage / "input.json").write_bytes(input_bytes)
            replicates: list[dict[str, Any]] = []
            total = len(experiment.seeds) * len(experiment.large_household_sizes)
            for size in experiment.large_household_sizes:
                for seed in experiment.seeds:
                    progress(
                        f"Generazione {len(replicates) + 1}/{total}, classe 6+={size}, seed={seed}"
                    )
                    subdir = stage / f"size-{size}-seed-{seed}"
                    generate(inputs.calibration, seed, size, subdir)
                    progress(f"Verifica indipendente {len(replicates) + 1}/{total}")
                    result = audit(subdir, inputs, size)
                    replicates.append({"seed": seed, "large_household_size": size, "audit": result})
            report = {
                "schema_version": REPORT_VERSION,
                "data_kind": "synthetic",
                "public_release": False,
                "external_scientific_review": "not_performed",
                "out_of_calibration_validation": "not_available",
                "microdata_distribution": "blocked_pending_disclosure_and_scientific_review",
                "replicates": replicates,
                "uncertainty": summarize(replicates),
                "uncertainty_interpretation": (
                    "Variabilità algoritmica tra seed e sensibilità alla classe 6+; "
                    "non intervalli di confidenza"
                ),
                "limitations": [
                    "Sesso per singola età calibrato esattamente: "
                    "errore zero non costituisce validazione fuori calibrazione",
                    "Famiglie casuali con almeno un adulto; parentela e coppie non inferite",
                    "100 indica 100 anni e più; non è un'età puntuale",
                    "Tutti i minori assegnati a famiglie; "
                    "residuo adulto non identificato come convivenze",
                    "Dimensione 6+ ipotetica; nessuna stima della sua distribuzione reale",
                    "Nessuna statistica osservata non utilizzata disponibile "
                    "per validazione fuori calibrazione",
                    "Nessuna validazione osservata della composizione familiare "
                    "o misura del rischio disclosure",
                ],
            }
            atomic_json(stage / "report.json", report)
            (stage / "README.md").write_text(
                "# Esperimento sintetico M3 — uso locale\n\n"
                "Persone e famiglie virtuali, prive di corrispondenza con identità reali.\n"
                "Input, algoritmo, ambiente, seed e checksum: manifest.json e input.json.\n"
                "Controlli SQL indipendenti, 202 celle sesso/età calibrate esattamente, "
                "incertezza e limiti: report.json.\n"
                "Non sono disponibili statistiche osservate per validazione fuori calibrazione.\n"
                "Età 100 = 100+. household_id nullo = residuo non assegnato.\n"
                "La revisione scientifica esterna e la valutazione disclosure "
                "non sono state svolte.\n"
                "I microdati non sono autorizzati alla distribuzione.\n",
                encoding="utf-8",
            )
            files = {
                p.relative_to(stage).as_posix(): sha256_file(p)
                for p in sorted(stage.rglob("*"))
                if p.is_file()
            }
            atomic_json(
                stage / "manifest.json",
                {
                    "run_id": run_id,
                    "status": "completed_experiment",
                    "descriptor": descriptor,
                    "created_at": datetime.now(UTC).isoformat(),
                    "git": _commit(),
                    "files": files,
                    "data_kind": "synthetic",
                    "public_release": False,
                },
            )
            # Rename on the same filesystem is the only completion operation. Interrupted
            # attempts remain in state; no partially populated completed directory exists.
            stage.rename(target)
        progress(
            f"Esito: completato, {total}/{total} repliche; "
            f"{sum(inputs.calibration.age_counts)} persone virtuali/replica"
        )
        return target
    except Exception as error:
        atomic_json(
            root / "quarantine" / f"m3-{attempt}.json",
            {
                "run_id": run_id,
                "published": False,
                "error_code": type(error).__name__,
                "report": error.report if isinstance(error, QualityError) else None,
            },
        )
        progress(f"Esito: fallito ({type(error).__name__}); nessuna nuova pubblicazione")
        raise
