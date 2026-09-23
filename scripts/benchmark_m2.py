"""Storage/query benchmark on invented aggregates, in an explicit empty test DB.

Run with scripts/run_logged.py. No source acquisition and no synthetic individuals.
"""

import json
import os
import statistics
import time
from pathlib import Path
from uuid import uuid4

import psycopg

from itadb.pipeline.publish_coverage import archive_json
from itadb.pipeline.storage import atomic_json, sha256_file


def main() -> None:
    url = os.environ["ITADB_TEST_DATABASE_URL"]
    root = Path("data")
    rid = uuid4()
    started = time.monotonic()
    with psycopg.connect(url, autocommit=True) as db:
        if db.execute("SELECT count(*) FROM catalog.release").fetchone()[0]:
            raise ValueError("Benchmark requires an empty, explicitly configured test database")
        database_before = db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        wal_start = db.execute("SELECT pg_current_wal_insert_lsn()").fetchone()[0]
        db.execute(
            "INSERT INTO catalog.dataset VALUES ('m2_benchmark','demo',"
            "'Benchmark inventato','8000 territori × 128 serie',"
            "'Solo misura del motore di archiviazione, non dati osservati.')"
        )
        artifact = archive_json(
            root,
            {
                "kind": "invented_storage_benchmark",
                "territories": 8000,
                "series": 128,
                "value": 1,
                "release": str(rid),
            },
        )
        digest = sha256_file(artifact)
        db.execute("""INSERT INTO stats.series(code,title,unit,dimensions)
            SELECT 'm2_bench_'||n,'Serie inventata '||n,'persons','{}'::jsonb
            FROM generate_series(1,128) n""")
        db.execute(
            """INSERT INTO catalog.release(id,dataset_id,reference_period,retrieved_at,
            upstream_url,raw_sha256,transform_version,contract_sha256,license_url,status,row_count,
            api_version,metadata_sha256,territory_snapshot,series_code,publication_kind)
            VALUES (%s,'m2_benchmark','2021-01-01',now(),'https://example.org/invented',%s,
            'benchmark/1',%s,'https://creativecommons.org/publicdomain/zero/1.0/','draft',
            1024000,2,%s,'2021-01-01','m2_bench_1','coverage')""",
            (rid, digest, digest, digest),
        )
        db.execute("""INSERT INTO geo.territory(scheme,code,name,level,valid_from)
            VALUES ('M2_BENCH','IT','Italia inventata','country','2021-01-01')""")
        parent = db.execute("SELECT id FROM geo.territory WHERE scheme='M2_BENCH'").fetchone()[0]
        db.execute(
            """INSERT INTO geo.territory(scheme,code,name,level,valid_from,parent_id)
            SELECT 'M2_BENCH',n::text,'Comune inventato '||n,'municipality','2021-01-01',%s
            FROM generate_series(1,8000) n""",
            (parent,),
        )
        db.execute(
            "INSERT INTO geo.release_territory SELECT %s,id,'2021-01-01' "
            "FROM geo.territory WHERE scheme='M2_BENCH'",
            (rid,),
        )
        db.execute(
            """INSERT INTO geo.boundary SELECT id,%s,
            ST_Multi(ST_MakeEnvelope(10,42,10.01,42.01,4326)) FROM geo.territory
            WHERE scheme='M2_BENCH' AND level='municipality'""",
            (rid,),
        )
        db.execute(
            "INSERT INTO catalog.coverage SELECT %s,id,'2021-01-01','M2_BENCH',"
            "'2021-01-01',8000 FROM stats.series WHERE code LIKE 'm2_bench_%%'",
            (rid,),
        )
        for start in range(1, 129, 8):
            db.execute(
                """INSERT INTO stats.observation(release_id,series_id,territory_id,
                period,value,status) SELECT %s,s.id,t.id,'2021-01-01',1,'demo'
                FROM stats.series s CROSS JOIN geo.territory t
                WHERE s.code IN (SELECT 'm2_bench_'||n
                FROM generate_series(%s::integer,%s::integer) n)
                AND t.scheme='M2_BENCH' AND t.level='municipality'""",
                (rid, start, start + 7),
            )
            print(
                f"Caricamento: {(start + 7) * 8000:,}/1,024,000; "
                f"trascorsi {time.monotonic() - started:.1f}s",
                flush=True,
            )
        load_seconds = time.monotonic() - started
        for kind in (
            "raw",
            "curated",
            "quality",
            "contract",
            "evidence",
            "geography",
            "crosswalk",
            "license",
        ):
            db.execute(
                "INSERT INTO catalog.artifact VALUES (%s,%s,%s,%s,%s)",
                (rid, kind, artifact.relative_to(root).as_posix(), digest, artifact.stat().st_size),
            )
        db.execute(
            "INSERT INTO catalog.quality_result VALUES (%s,'invented_benchmark',true,'{}')", (rid,)
        )
        db.execute(
            "UPDATE catalog.release SET status='published',published_at=now() WHERE id=%s", (rid,)
        )
        db.execute("ANALYZE stats.observation")
        db.execute("ANALYZE geo.territory")
        db.execute("ANALYZE stats.series")
        query = """SELECT * FROM api.observations_v2 WHERE release_id=%s AND series_code=%s
            AND period=%s AND level=%s AND territory_id>%s ORDER BY territory_id LIMIT %s"""
        times = []
        for index in range(100):
            params = (
                rid,
                "m2_bench_" + str(index % 128 + 1),
                "2021-01-01",
                "municipality",
                parent + 1 + (index * 79) % 7900,
                100,
            )
            tick = time.perf_counter()
            rows = db.execute(query, params).fetchall()
            assert len(rows) == 100
            times.append((time.perf_counter() - tick) * 1000)
        plan = db.execute("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + query, params).fetchone()[0]
        report = {
            "kind": "invented_storage_benchmark",
            "release_id": str(rid),
            "rows": 1024000,
            "territories": 8000,
            "series": 128,
            "load_seconds": load_seconds,
            "query_count": len(times),
            "p50_ms": statistics.median(times),
            "p95_ms": sorted(times)[94],
            "query_ms": times,
            "plan": plan,
            "database_growth_bytes": db.execute(
                "SELECT pg_database_size(current_database())"
            ).fetchone()[0]
            - database_before,
            "wal_bytes": int(
                db.execute(
                    "SELECT pg_wal_lsn_diff(pg_current_wal_insert_lsn(),%s)", (wal_start,)
                ).fetchone()[0]
            ),
            "server_version": db.execute("SHOW server_version").fetchone()[0],
            "shared_buffers": db.execute("SHOW shared_buffers").fetchone()[0],
            "work_mem": db.execute("SHOW work_mem").fetchone()[0],
        }
        output = root / "reports" / f"m2-benchmark-{rid}.json"
        atomic_json(output, report)
        print(
            json.dumps({k: v for k, v in report.items() if k not in {"plan", "query_ms"}}),
            flush=True,
        )
        print(output, flush=True)


if __name__ == "__main__":
    main()
