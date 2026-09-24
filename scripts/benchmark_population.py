"""Measure the current ordered population pipeline using invented 1M/10M constraints."""

import argparse
import json
import time
from pathlib import Path

from benchmark_citizenship import fixture as citizenship_fixture
from benchmark_m4 import fixture as national_fixture

from itadb.pipeline.storage import atomic_json
from itadb.synthesis.national_runtime import peak_rss_bytes
from itadb.synthesis.population_models import PopulationInput
from itadb.synthesis.population_runner import run_population, verify_population


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=int, choices=[1_000_000, 10_000_000], required=True)
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--recovery", action="store_true")
    parser.add_argument("--reverse-order", action="store_true")
    args = parser.parse_args()
    national = national_fixture(args.population)
    inputs = PopulationInput(national=national, citizenship=citizenship_fixture(national))
    started = time.monotonic()
    print(
        f"Fixture inventata: {args.population:,} individui; cittadinanza prima delle famiglie",
        flush=True,
    )
    interrupted = False
    if args.recovery:
        try:
            run_population(args.root, inputs, stop_after_batches=1)
        except InterruptedError:
            interrupted = True
            print("Interruzione controllata: ripresa dai checkpoint", flush=True)
    directory = run_population(args.root, inputs, reverse_order=args.reverse_order)
    audit_start = time.monotonic()
    verify_population(directory)
    result = {
        "benchmark": "population-load/1",
        "evidence_kind": inputs.national.evidence_kind,
        "persons": args.population,
        "run_id": directory.name,
        "elapsed_seconds": time.monotonic() - started,
        "audit_seconds": time.monotonic() - audit_start,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "recovery_exercised": interrupted,
        "reverse_order": args.reverse_order,
        "status": "passed",
    }
    path = args.root / "reports/population" / f"benchmark-{directory.name}-{time.time_ns()}.json"
    atomic_json(path, result)
    print(json.dumps({"snapshot": str(directory), "report": str(path), **result}), flush=True)


if __name__ == "__main__":
    main()
