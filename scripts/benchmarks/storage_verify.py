"""Extended engine parity on ordering, ties, cursor anchors and bounded filters."""

import argparse
import json
import random
import subprocess
from pathlib import Path

from storage_compare import RustStore, SQLStore, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    stores = {
        engine: SQLStore(args.root, engine) for engine in ["postgres", "postgres_compact", "duckdb"]
    }
    stores["rust"] = RustStore(args.root)
    workload = json.loads((args.root / "workload.json").read_text())
    municipality = workload["small_municipality"]["municipality"]
    checks = []

    def check(query):
        expected = stores["postgres"].query(query)
        expected_hash = fingerprint(expected)
        for name, store in stores.items():
            if name != "postgres" and fingerprint(store.query(query)) != expected_hash:
                raise ValueError(f"Extended parity mismatch: {name}, {query}")
        checks.append({"query": query, "sha256": expected_hash})
        return expected

    for sort in ["id", "age", "sex", "citizenship", "household"]:
        for desc in [False, True]:
            for filters in [{}, {"sex": "F"}, {"citizenship": 100}, {"age_min": 18, "age_max": 65}]:
                query = {
                    "op": "persons",
                    "municipality": municipality,
                    "sort": sort,
                    "desc": desc,
                    "limit": 3,
                    **filters,
                }
                rows = check(query)
                if rows:
                    check({**query, "after": rows[-1][0]})
                check({**query, "after": 60000000})
    for sort in ["id", "size"]:
        for desc in [False, True]:
            for size in [None, 1, 6]:
                query = {
                    "op": "households",
                    "municipality": municipality,
                    "sort": sort,
                    "desc": desc,
                    "limit": 3,
                    "size": size,
                }
                rows = check(query)
                if rows:
                    check({**query, "after": rows[-1][0]})
    rng = random.Random(20260925)
    for _ in range(100):
        check({"op": "person", "id": rng.randint(1, 58943464)})
        check({"op": "household", "id": rng.randint(1, 26670169)})
    for age in [0, 18, 65, 100]:
        for sex in ["F", "M"]:
            check(
                {
                    "op": "distribution",
                    "municipality": municipality,
                    "age_min": age,
                    "age_max": age,
                    "sex": sex,
                }
            )
    for store in stores.values():
        store.close()
    print(f"Parità estesa: {len(checks)} query, quattro motori", flush=True)
    audit = subprocess.run(
        [
            "experiments/population-store/target/release/build-store",
            str(args.root),
            str(args.root / "rust"),
            "audit",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    print(audit.stdout, flush=True)
    with (args.root / "audit-extended.json").open("x") as stream:
        json.dump(
            {
                "checks": checks,
                "query_count": len(checks),
                "rust_full_parity": audit.stdout.splitlines(),
            },
            stream,
            indent=2,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
