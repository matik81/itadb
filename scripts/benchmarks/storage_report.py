"""Publish aggregate benchmark evidence and an explicit monthly cost model."""

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    preparation = read(root / "prepare-duckdb.json")
    audit = read(root / "audit-postgres.json")
    extended = read(root / "audit-extended.json")
    evidence = {
        "date": "2026-09-25",
        "scope": "local national synthetic snapshot; engine adapters, not HTTP",
        "environment": read(root / "environment.json")
        if (root / "environment.json").exists()
        else {
            "source_git": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "platform": platform.platform(),
        },
        "run_id": preparation["run_id"],
        "source_manifest_sha256": preparation["source_manifest_sha256"],
        "counts": preparation["counts"],
        "source_parquet_bytes": preparation["input_bytes"],
        "postgres_audit": audit,
        "rust_full_parity": extended["rust_full_parity"],
        "extended_query_count": extended["query_count"],
        "deterministic_rebuild": read(root / "audit-rebuild.json")
        if (root / "audit-rebuild.json").exists()
        else {"verified": False, "note": "Rebuild evidence not supplied for this run"},
        "engines": {},
    }
    for name in ["postgres", "postgres_compact", "duckdb", "rust"]:
        path = root / f"benchmark-{name}-final.json"
        if name == "postgres" and not path.exists():
            path = root / "benchmark-postgres.json"
        results = read(path)
        if name == "postgres":
            results["queries"] = read(root / "benchmark-postgres.json")["queries"]
        for sample in results["concurrency"].values():
            samples = sample.pop("samples_ms")
            sample["sample_count"] = len(samples)
            sample["over_5_seconds"] = sum(x > 5000 for x in samples)
            sample["samples_sha256"] = hashlib.sha256(
                json.dumps(samples, separators=(",", ":")).encode()
            ).hexdigest()
        # PG client cgroup inherited unrelated cache from a preceding preliminary run.
        # RSS/PSS and the server's separately measured cgroup remain valid metrics.
        if name.startswith("postgres"):
            results["client_cgroup_cache_caveat"] = (
                "Contains cache from earlier native preliminary run; use client RSS/PSS, "
                "not this cgroup total, when comparing architectures."
            )
        evidence["engines"][name] = results
    relations = audit["source_storage"]["population_relations"]
    core_pg = sum(r[3] for r in relations if r[0] in ("person_1", "household_1", "cell_1"))
    residual = audit["source_storage"]["database_bytes"] - core_pg
    compact = read(root / "prepare-postgres.json")
    rust_bytes = sum(p.stat().st_size for p in (root / "rust").iterdir())
    sizes = {
        "postgres": core_pg,
        "postgres_compact": compact["archive_bytes"],
        "duckdb": preparation["archive_bytes"],
        "rust": rust_bytes,
    }
    evidence["storage"] = {
        "core_bytes": sizes,
        "retained_postgres_estimate_bytes": residual,
        "complete_footprint_estimate_bytes": {k: v + residual for k, v in sizes.items()},
        "compact_relations": compact["relations"],
        "rust_files": {p.name: p.stat().st_size for p in (root / "rust").iterdir()},
    }
    evidence["build"] = {
        "duckdb_and_csv_seconds": preparation["build_seconds"],
        "postgres_from_csv_seconds": compact["build_seconds"],
        "rust_from_csv_seconds": read(root / "rust/manifest.json")["build_seconds"],
        "rust_rebuild_resources": (root / "rust-rebuild-resources.txt").read_text()
        if (root / "rust-rebuild-resources.txt").exists()
        else None,
    }
    prices = {
        "verified_on": "2026-09-25",
        "currency": "USD",
        "taxes_included": False,
        "neon_cu_hour": 0.106,
        "neon_gb_month": 0.35,
        "railway_ram_gb_month": 10,
        "railway_cpu_month": 20,
        "railway_volume_gb_month": 0.15,
        "railway_egress_gb": 0.05,
        "railway_hobby_minimum": 5,
        "railway_pro_minimum": 20,
        "sources": [
            "https://neon.com/pricing",
            "https://docs.railway.com/pricing",
            "https://docs.railway.com/pricing/plans",
            "https://docs.railway.com/volumes/reference",
        ],
    }
    evidence["prices"] = prices
    hours = 730
    seconds = hours * 3600
    requests = 1_000_000
    # Capacity assumptions, deliberately separate from measured local memory or Neon sizing.
    # API-only baseline: 0.25 GB average; embedded alternatives include API headroom.
    ram = {"postgres": 0.25, "postgres_compact": 0.25, "duckdb": 0.50, "rust": 0.75}
    scenarios = []
    for label, cu, active_hours in [
        ("low_activity", 0.25, 60),
        ("always_on_025", 0.25, 730),
        ("always_on_050", 0.5, 730),
    ]:
        for engine in sizes:
            native = engine in ("duckdb", "rust")
            neon_storage = residual if native else sizes[engine] + residual
            neon_cost = cu * active_hours * prices["neon_cu_hour"] + neon_storage / 1e9 * 0.35
            # Native CPU measured for the complete adapter; PG client uses explicit allowance.
            cpu_ms = (
                evidence["engines"][engine]["concurrency"]["8"]["cpu_ms_per_request"]
                if native
                else 1
            )
            cpu_cost = cpu_ms / 1000 * requests / seconds * 20
            volume_gb = 2 * sizes[engine] / 1e9 if native else 0
            railway = max(5, ram[engine] * 10 + cpu_cost + volume_gb * 0.15 + 10 * 0.05)
            scenarios.append(
                {
                    "scenario": label,
                    "engine": engine,
                    "neon_cu_assumed": cu,
                    "neon_active_hours_assumed": active_hours,
                    "railway_ram_gb_assumed": ram[engine],
                    "neon_usd": neon_cost,
                    "railway_usd": railway,
                    "monthly_usd": neon_cost + railway,
                }
            )
    evidence["cost_model"] = {
        "assumptions": {
            "hours": hours,
            "requests": requests,
            "railway_egress_gb": 10,
            "native_archive_copies": 2,
            "billing_gb_bytes": 1e9,
            "postgres_api_cpu_ms_per_request_assumed": 1,
            "excluded": "VAT, frontend, domains, remote backup, Neon history, operations labor",
            "warning": "Estimates, not invoices or validated Neon instance sizes. "
            "All hybrid scenarios retain legacy PostgreSQL; its storage is a subtraction estimate, "
            "not a measured migrated database.",
        },
        "scenarios": scenarios,
        "railway_cpu_usd_per_million_requests": {
            engine: {
                mix: evidence["engines"][engine]["concurrency"][mix]["cpu_ms_per_request"]
                / 1000
                * requests
                / seconds
                * 20
                for mix in ["8", "8_broad"]
            }
            for engine in sizes
        },
        "rust_full_cache_ram_gb_sensitivity": 1.8,
        "rust_full_cache_additional_usd": (1.8 - ram["rust"]) * 10,
    }
    evidence["artifact_hashes"] = {}
    for path in sorted(root.glob("*.json")):
        with path.open("rb") as stream:
            evidence["artifact_hashes"][path.name] = hashlib.file_digest(
                stream, "sha256"
            ).hexdigest()
    with args.output.open("x") as stream:
        json.dump(evidence, stream, indent=2)
        stream.write("\n")
    print(f"Evidenze aggregate: {args.output}")
    for item in scenarios:
        print(item["scenario"], item["engine"], f"${item['monthly_usd']:.2f}")


if __name__ == "__main__":
    main()
