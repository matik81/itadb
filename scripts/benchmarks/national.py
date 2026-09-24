"""National synthesis benchmark without citizenship; the product uses population.py."""

import argparse
import json
import time
from pathlib import Path

from itadb.pipeline.storage import atomic_json
from itadb.synthesis.national_models import ResourceBudget
from itadb.synthesis.national_runner import run_national, verify_national
from itadb.synthesis.national_runtime import peak_rss_bytes

from .fixtures import national_fixture as fixture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=int, choices=[1_000_000, 10_000_000], required=True)
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--recovery", action="store_true")
    args = parser.parse_args()
    inputs = fixture(args.population)
    budget = ResourceBudget()
    started = time.monotonic()
    print(
        f"Fixture inventata: {args.population:,} persone; budget {budget.model_dump()}", flush=True
    )
    interrupted = False
    if args.recovery:
        try:
            run_national(args.root, inputs, budget=budget, stop_after_batches=1)
        except InterruptedError:
            interrupted = True
            print("Interruzione controllata dopo il primo checkpoint; ripresa", flush=True)
    resume_start = time.monotonic()
    directory = run_national(args.root, inputs, budget=budget)
    resume_elapsed = time.monotonic() - resume_start
    audit_start = time.monotonic()
    verify_national(directory)
    result = {
        "benchmark": "m4-load/1",
        "evidence_kind": inputs.evidence_kind,
        "persons": args.population,
        "run_id": directory.name,
        "elapsed_seconds": time.monotonic() - started,
        "audit_seconds": time.monotonic() - audit_start,
        "resume_or_generation_seconds": resume_elapsed,
        "recovery_exercised": interrupted,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "budget": budget.model_dump(),
        "status": "passed",
    }
    output = args.root / "reports" / "m4" / f"benchmark-{directory.name}-{time.time_ns()}.json"
    atomic_json(output, result)
    print(json.dumps({"snapshot": str(directory), "report": str(output), **result}), flush=True)


if __name__ == "__main__":
    main()
