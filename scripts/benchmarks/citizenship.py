"""Citizenship enrichment benchmark; use scripts.benchmarks.population for the current reference."""

import argparse
import json
import time
from pathlib import Path

from itadb.pipeline.storage import atomic_json
from itadb.synthesis.citizenship_runner import run_citizenship, verify_citizenship
from itadb.synthesis.national_models import NationalInput
from itadb.synthesis.national_runtime import peak_rss_bytes

from .fixtures import citizenship_fixture as fixture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--recovery", action="store_true")
    parser.add_argument("--reverse-order", action="store_true")
    args = parser.parse_args()
    base = NationalInput.model_validate_json((args.base_run / "input.json").read_bytes())
    inputs = fixture(base)
    started = time.monotonic()
    interrupted = False
    if args.recovery:
        try:
            run_citizenship(args.root, args.base_run, inputs, stop_after_batches=1)
        except InterruptedError:
            interrupted = True
            print("Interruzione controllata; ripresa dai checkpoint", flush=True)
    directory = run_citizenship(args.root, args.base_run, inputs, reverse_order=args.reverse_order)
    audit_start = time.monotonic()
    verify_citizenship(directory, args.base_run)
    result = {
        "benchmark": "citizenship-load/1",
        "evidence_kind": inputs.evidence_kind,
        "persons": sum(m.population for m in base.municipalities),
        "base_run_id": args.base_run.name,
        "run_id": directory.name,
        "elapsed_seconds": time.monotonic() - started,
        "audit_seconds": time.monotonic() - audit_start,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "recovery_exercised": interrupted,
        "reverse_order": args.reverse_order,
        "status": "passed",
    }
    path = args.root / "reports/citizenship" / f"benchmark-{directory.name}-{time.time_ns()}.json"
    atomic_json(path, result)
    print(json.dumps({"snapshot": str(directory), "report": str(path), **result}), flush=True)


if __name__ == "__main__":
    main()
