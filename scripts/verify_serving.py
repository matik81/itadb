"""Compare complete published API responses with PostgreSQL; read-only and bounded."""

import argparse
import hashlib
import json
import logging
import time
from pathlib import Path

from fastapi.testclient import TestClient

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.serving.archive import verify_archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings()
    manifest = verify_archive((settings.serving_dir / "current").resolve())
    logging.getLogger("itadb.api").disabled = True
    checks = []
    started = time.monotonic()
    with (
        TestClient(create_app(settings.model_copy(update={"serving_backend": "postgres"}))) as pg,
        TestClient(create_app(settings.model_copy(update={"serving_backend": "duckdb"}))) as duck,
    ):

        def check(path, params=None, *, paginate=False):
            times, responses = [], []
            for client in (pg, duck):
                now = time.perf_counter()
                response = client.get(path, params=params)
                times.append(round((time.perf_counter() - now) * 1000, 3))
                responses.append(response)
            expected, actual = responses
            passed = (
                expected.status_code == actual.status_code == 200
                and expected.json() == actual.json()
            )
            checks.append(
                {
                    "path": path,
                    "params": params,
                    "postgres_ms": times[0],
                    "duckdb_ms": times[1],
                    "passed": passed,
                    "status": [r.status_code for r in responses],
                }
            )
            if not passed:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps({"checks": checks, "complete": False}, indent=2) + "\n"
                )
                raise AssertionError(
                    f"API mismatch at check {len(checks)}: {path}; statuses {checks[-1]['status']}"
                )
            result = actual.json()
            checks[-1]["response_sha256"] = hashlib.sha256(
                json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if len(checks) % 20 == 0:
                print(
                    f"Verificate {len(checks)} richieste; "
                    f"trascorsi {time.monotonic() - started:.1f} s",
                    flush=True,
                )
            if paginate and isinstance(result, dict) and result.get("next_cursor"):
                check(path, {**(params or {}), "after": result["next_cursor"]})
            return result

        for path in ("/health/ready", "/v1/sources", "/v2/sources"):
            check(path)
        for version in ("v1", "v2"):
            releases = check(f"/{version}/releases", {"limit": 100})
            for release in releases:
                rid = release["id"]
                check(f"/{version}/releases/{rid}")
                check(f"/{version}/releases/{rid}/quality")
                query = {
                    "release_id": rid,
                    "series": release.get("series_code", "population_total"),
                    "period": release["reference_period"],
                    "limit": 3,
                }
                check(f"/{version}/observations", query, paginate=True)
                if version == "v1":
                    continue
                check(f"/v2/releases/{rid}/artifacts")
                coverage = check(f"/v2/releases/{rid}/coverage")
                for sort in ("territory_id", "name", "code", "value", "status"):
                    for direction in ("asc", "desc"):
                        check(
                            "/v2/observations",
                            {**query, "sort_by": sort, "direction": direction},
                            paginate=True,
                        )
                for sort in ("id", "date", "description", "from_code", "to_code", "usage"):
                    for direction in ("asc", "desc"):
                        check(
                            "/v2/crosswalks",
                            {
                                "release_id": rid,
                                "sort_by": sort,
                                "direction": direction,
                                "limit": 3,
                            },
                            paginate=True,
                        )
                for selection in coverage[:2]:
                    for level in ("country", "region", "province", "municipality"):
                        q = {
                            **query,
                            "series": selection["series_code"],
                            "period": selection["period"],
                            "level": level,
                        }
                        check("/v2/observations", q, paginate=True)
                        if selection["territory_snapshot"]:
                            territories = check(
                                "/v2/territories",
                                {
                                    "release_id": rid,
                                    "snapshot": selection["territory_snapshot"],
                                    "level": level,
                                    "limit": 3,
                                },
                                paginate=True,
                            )
                            for territory in territories["items"]:
                                if territory["has_boundary"]:
                                    check(
                                        f"/v2/releases/{rid}/territories/{territory['territory_id']}/boundary"
                                    )
        snapshots = check("/v3/populations")
        for snapshot in snapshots:
            base = f"/v3/populations/{snapshot['id']}"
            check(base)
            check(base + "/map")
            municipalities = check(base + "/municipalities", {"limit": 3}, paginate=True)["items"]
            for region in ("01", "09", "20"):
                check(base + "/map", {"region_code": region})
            check(base + "/validation")
            check(base + "/distributions")
            for territory in municipalities:
                municipality = territory["code"]
                check(
                    base + "/municipalities",
                    {
                        "region_code": territory["region_code"],
                        "search": territory["name"][:4],
                        "limit": 3,
                    },
                    paginate=True,
                )
                check(base + "/validation", {"municipality_code": municipality})
                for kind in ("sex_age", "foreign_age", "citizenship", "household_size"):
                    check(base + "/comparison", {"municipality_code": municipality, "kind": kind})
                for geo in (
                    {"municipality_code": municipality},
                    {"region_code": territory["region_code"]},
                    {"province_code": territory["province_code"]},
                    {"province_code": territory["province_code"], "region_code": "99"},
                ):
                    for filt in (
                        {},
                        {"sex": "F", "citizenship_code": "100", "age_min": 20, "age_max": 80},
                    ):
                        check(base + "/distributions", {**geo, **filt})
                for entity, sorts in (
                    ("persons", ("person_id", "age", "sex", "citizenship_code", "household_id")),
                    ("households", ("household_id", "size")),
                ):
                    for sort in sorts:
                        for direction in ("asc", "desc"):
                            page = check(
                                base + "/" + entity,
                                {
                                    "municipality_code": municipality,
                                    "sort_by": sort,
                                    "direction": direction,
                                    "limit": 3,
                                },
                                paginate=True,
                            )
                            if page["items"]:
                                identity = "person_id" if entity == "persons" else "household_id"
                                check(base + f"/{entity}/{page['items'][0][identity]}")
    result = {
        "complete": True,
        "checks_count": len(checks),
        "elapsed_seconds": time.monotonic() - started,
        "database": manifest["database"],
        "table_rows": {k: v["rows"] for k, v in manifest["tables"].items()},
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: v for k, v in result.items() if k not in ("checks", "table_rows")}),
        flush=True,
    )


if __name__ == "__main__":
    main()
