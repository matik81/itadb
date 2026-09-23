"""Measured citizenship enrichment on an explicitly invented M4 load snapshot."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from itadb.pipeline.storage import atomic_json
from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipMunicipality
from itadb.synthesis.citizenship_runner import run_citizenship, verify_citizenship
from itadb.synthesis.national_models import NationalInput
from itadb.synthesis.national_runtime import peak_rss_bytes


def fixture(base: NationalInput) -> CitizenshipInput:
    if base.evidence_kind != "invented_load_fixture":
        raise ValueError("Citizenship load fixtures cannot be applied to official aggregates")
    municipalities = []
    for m in base.municipalities:
        fm, ff = [[n // 5 for n in counts] for counts in [m.male, m.female]]
        countries: dict[str, list[int]] = {c: [] for c in ["100", "201", "235", "999"]}
        for foreign, population in [(fm, m.male), (ff, m.female)]:
            n = sum(foreign)
            stateless = int(n > 0)
            countries["100"].append(sum(population) - n)
            countries["201"].append(n // 2)
            countries["235"].append(n - n // 2 - stateless)
            countries["999"].append(stateless)
        municipalities.append(
            CitizenshipMunicipality(
                code=m.code, foreign_male=fm, foreign_female=ff, countries=countries
            )
        )
    return CitizenshipInput(
        population_reference=base.population_reference,
        evidence_kind="invented_load_fixture",
        municipalities=municipalities,
        country_labels={"100": "Italia", "201": "Albania", "235": "Romania", "999": "Apolide"},
        source_hashes={"fixture_specification": hashlib.sha256(b"citizenship-load/1").hexdigest()},
        attribution="Fixture di carico inventata, CC0; non dati osservati ISTAT",
    )


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
