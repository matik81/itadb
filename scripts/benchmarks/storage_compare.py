"""Read-only, parameterized storage benchmark with canonical result hashes."""

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import random
import resource
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import psycopg
from psycopg.conninfo import conninfo_to_dict

from itadb.config import Settings

CGROUP = Path("/sys/fs/cgroup/itadb-storage-benchmark")
LIBRARY = Path("experiments/population-store/target/release/libitadb_population_store.so")
FIELDS = (
    "person_id,NULLIF(household_id,0),municipality_code,sex,"
    "CASE WHEN age<100 THEN 2024-age END,CASE WHEN age=100 THEN 1924 END,"
    "age,citizenship_code,reference_adult"
)


def canonical(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class RustStore:
    def __init__(self, root):
        self.lib = ctypes.CDLL(str(LIBRARY.resolve()))
        self.lib.store_open.argtypes = [ctypes.c_char_p]
        self.lib.store_open.restype = ctypes.c_void_p
        self.lib.store_query.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.store_query.restype = ctypes.c_void_p
        self.lib.store_free.argtypes = [ctypes.c_void_p]
        self.lib.store_close.argtypes = [ctypes.c_void_p]
        self.handle = self.lib.store_open(str((root / "rust").resolve()).encode())
        if not self.handle:
            raise ValueError("Rust archive failed validation")

    def query(self, q):
        pointer = self.lib.store_query(self.handle, canonical(q))
        if not pointer:
            raise ValueError("Rust query returned a null pointer")
        try:
            value = json.loads(ctypes.string_at(pointer))
        finally:
            self.lib.store_free(pointer)
        if isinstance(value, dict) and "error" in value:
            raise ValueError(value["error"])
        return value

    def close(self):
        self.lib.store_close(self.handle)


class SQLStore:
    def __init__(self, root, engine, pagination="native"):
        self.engine = engine
        self.pagination = pagination
        self.local = threading.local()
        self.connections = []
        self.lock = threading.Lock()
        self.root = root
        self.database = None
        if engine == "duckdb":
            if not (root / "prepare-duckdb.json").is_file():
                raise ValueError("DuckDB archive has no successful preparation manifest")
            self.database = duckdb.connect(str(root / "population.duckdb"), read_only=True)
            self.database.execute("SET threads=2; SET memory_limit='3GB'")
        else:
            self.config = conninfo_to_dict(Settings().admin_database_url)
            if engine == "postgres_compact":
                self.config["dbname"] = json.loads((root / "prepare-postgres.json").read_text())[
                    "database"
                ]

    def connection(self):
        if not hasattr(self.local, "connection"):
            if self.database is not None:
                connection = self.database.cursor()
            else:
                connection = psycopg.connect(
                    **self.config,
                    autocommit=True,
                    options="-c default_transaction_read_only=on -c statement_timeout=30000",
                )
            self.local.connection = connection
            with self.lock:
                self.connections.append(connection)
        return self.local.connection

    def execute(self, sql, params=()):
        if self.engine != "duckdb":
            sql = sql.replace("?", "%s")
        return self.connection().execute(sql, params).fetchall()

    def table(self, kind):
        if self.engine == "postgres":
            return {
                "person": "api.population_persons",
                "household": "api.population_households",
                "cell": "api.population_cells",
            }[kind]
        return kind

    def fields(self):
        if self.engine == "postgres_compact":
            return FIELDS.replace(
                "municipality_code,sex,", "municipality_code,CASE sex WHEN 0 THEN 'F' ELSE 'M' END,"
            ).replace("citizenship_code,reference_adult", "citizenship_code,reference_adult<>0")
        return FIELDS

    def query(self, q):
        op = q["op"]
        kind = (
            "cell"
            if op == "distribution"
            else ("household" if op in ("household", "households") else "person")
        )
        table = self.table(kind)
        identity = "household_id" if kind == "household" else "person_id"
        fields = self.fields() if kind == "person" else "household_id,municipality_code,size"
        where = ["snapshot_id=1"] if self.engine == "postgres" else ["1=1"]
        params = []
        if op in ("person", "household"):
            rows = self.execute(
                f"SELECT {fields} FROM {table} WHERE {' AND '.join(where)} AND {identity}=?",
                (q["id"],),
            )
            if not rows:
                return None
            if op == "person":
                return rows[0]
            members = self.execute(
                f"SELECT {self.fields()} FROM {self.table('person')} WHERE "
                f"{' AND '.join(where)} AND household_id=? "
                "ORDER BY person_id LIMIT 6",
                (q["id"],),
            )
            return {"household": rows[0], "members": members}
        if q.get("municipality"):
            where.append("municipality_code=?")
            params.append(q["municipality"])
        if kind != "household":
            where.append("age BETWEEN ? AND ?")
            params += [q.get("age_min", 0), q.get("age_max", 100)]
            if q.get("sex"):
                where.append("sex=?")
                params.append(
                    int(q["sex"] == "M") if self.engine == "postgres_compact" else q["sex"]
                )
            if q.get("citizenship") is not None:
                where.append("citizenship_code=?")
                params.append(q["citizenship"])
        elif q.get("size"):
            where.append("size=?")
            params.append(q["size"])
        predicate = " AND ".join(where)
        if op == "distribution":
            sex = (
                "CASE sex WHEN 0 THEN 'F' ELSE 'M' END"
                if (self.engine == "postgres_compact")
                else "sex"
            )
            return self.execute(
                f"SELECT age,{sex},sum(persons)::BIGINT FROM {table} "
                f"WHERE {predicate} GROUP BY age,sex ORDER BY age,sex LIMIT 202",
                params,
            )
        column = {
            "id": identity,
            "age": "age",
            "sex": "sex",
            "citizenship": "citizenship_code",
            "household": "coalesce(household_id,0)",
            "size": "size",
        }[q.get("sort", "id")]
        direction, comparison = ("DESC", "<") if q.get("desc") else ("ASC", ">")
        after = q.get("after", 0)
        if self.engine != "postgres" and self.pagination == "native":
            # These archives are immutable: resolving the filtered anchor separately is safe.
            # Avoid a correlated MARK/DELIM join over millions of rows in DuckDB.
            if after:
                anchor = self.execute(
                    f"SELECT {column} FROM {table} WHERE {predicate} AND {identity}=?",
                    [*params, after],
                )
                if not anchor:
                    return []
                predicate += f" AND ({column} {comparison} ? OR ({column}=? AND {identity}>?))"
                params += [anchor[0][0], anchor[0][0], after]
            return self.execute(
                f"SELECT {fields} FROM {table} WHERE {predicate} "
                f"ORDER BY {column} {direction},{identity} ASC LIMIT ?",
                [*params, q.get("limit", 100)],
            )
        # Same filtered-anchor and ascending-ID tie-break semantics as the current API.
        return self.execute(
            f"WITH selected AS NOT MATERIALIZED (SELECT *,{column} sort_value "
            f"FROM {table} WHERE {predicate}),anchor AS (SELECT sort_value,"
            f"{identity} FROM selected WHERE {identity}=?) "
            f"SELECT {fields} FROM selected p WHERE (?=0 OR EXISTS(SELECT 1 "
            f"FROM anchor a WHERE p.sort_value {comparison} a.sort_value OR "
            f"(p.sort_value=a.sort_value AND p.{identity}>a.{identity}))) "
            f"ORDER BY sort_value {direction},{identity} ASC LIMIT ?",
            [*params, after, after, q.get("limit", 100)],
        )

    def close(self):
        for connection in self.connections:
            connection.close()
        if self.database is not None:
            self.database.close()


def workload(root):
    if not (root / "prepare-duckdb.json").is_file():
        raise ValueError("Workload requires a completed archive")
    db = duckdb.connect(str(root / "population.duckdb"), read_only=True)
    roma = 58091
    small = db.execute(
        "SELECT municipality_code FROM person GROUP BY municipality_code "
        "HAVING count(*) BETWEEN 500 AND 1000 ORDER BY municipality_code LIMIT 1"
    ).fetchone()[0]
    anchor = db.execute(
        "SELECT person_id FROM person WHERE municipality_code=? "
        "ORDER BY person_id LIMIT 1 OFFSET 99",
        [roma],
    ).fetchone()[0]
    age_anchor = db.execute(
        "SELECT person_id FROM person WHERE municipality_code=? "
        "ORDER BY age DESC,person_id LIMIT 1 OFFSET 99",
        [roma],
    ).fetchone()[0]
    open_id = db.execute("SELECT min(person_id) FROM person WHERE age=100").fetchone()[0]
    null_id = db.execute("SELECT min(person_id) FROM person WHERE household_id IS NULL").fetchone()[
        0
    ]
    city_id = db.execute(
        "SELECT min(person_id) FROM person WHERE municipality_code=?", [roma]
    ).fetchone()[0]
    city_hh = db.execute(
        "SELECT min(household_id) FROM household WHERE municipality_code=?", [roma]
    ).fetchone()[0]
    db.close()
    page = {"op": "persons", "municipality": roma}
    queries = {
        "point_first": {"op": "person", "id": 1},
        "point_city": {"op": "person", "id": city_id},
        "point_last": {"op": "person", "id": 58943464},
        "point_missing": {"op": "person", "id": 60000000},
        "point_age_100_plus": {"op": "person", "id": open_id},
        "point_unassigned": {"op": "person", "id": null_id},
        "municipality_id_page": page,
        "municipality_second_page": {**page, "after": anchor},
        "municipality_age_desc": {**page, "sort": "age", "desc": True},
        "municipality_age_second_page": {**page, "sort": "age", "desc": True, "after": age_anchor},
        "municipality_citizenship_filter": {
            **page,
            "sex": "F",
            "citizenship": 201,
            "age_min": 18,
            "age_max": 65,
        },
        "municipality_sex_sort": {**page, "sort": "sex", "desc": True},
        "municipality_citizenship_sort": {**page, "sort": "citizenship"},
        "municipality_household_sort": {**page, "sort": "household"},
        "small_municipality": {**page, "municipality": small, "sort": "age"},
        "filtered_out_anchor": {**page, "after": age_anchor, "age_max": 10},
        "missing_anchor": {**page, "after": 60000000},
        "empty_municipality": {**page, "municipality": 999999},
        "household_members": {"op": "household", "id": city_hh},
        "household_missing": {"op": "household", "id": 30000000},
        "household_size_page": {
            "op": "households",
            "municipality": roma,
            "sort": "size",
            "desc": True,
        },
        "household_size_filter": {"op": "households", "municipality": roma, "size": 6},
        "national_distribution": {"op": "distribution"},
        "national_filtered_distribution": {
            "op": "distribution",
            "citizenship": 201,
            "sex": "F",
            "age_min": 18,
            "age_max": 65,
        },
        "municipality_distribution": {"op": "distribution", "municipality": roma},
    }
    return queries


def cpu_seconds():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def pg_resources():
    result = subprocess.check_output(
        [
            "docker",
            "exec",
            "itadb-db-1",
            "sh",
            "-c",
            "cat /sys/fs/cgroup/cpu.stat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.stat",
        ],
        text=True,
    ).splitlines()
    values = {}
    for line in result:
        bits = line.split()
        if len(bits) == 1:
            values["memory_current"] = int(bits[0])
        else:
            values[bits[0]] = int(bits[1])
    return {
        "cpu_seconds": values["usage_usec"] / 1e6,
        "memory_bytes": values["memory_current"],
        "anonymous_bytes": values.get("anon", 0),
        "file_cache_bytes": values.get("file", 0),
    }


def summary(samples):
    ordered = sorted(samples)
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "p95_ms": ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)],
        "max_ms": max(samples),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--engine", choices=["postgres", "postgres_compact", "duckdb", "rust"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--make-workload", action="store_true")
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--pagination", choices=["legacy", "native"], default="native")
    parser.add_argument("--concurrency-seconds", type=float, default=10)
    parser.add_argument("--only-concurrency", action="store_true")
    parser.add_argument("--cgroup", action="store_true")
    args = parser.parse_args()
    if args.make_workload:
        with (args.root / "workload.json").open("x") as stream:
            json.dump(workload(args.root), stream, indent=2)
        return
    if args.engine is None or args.output is None:
        parser.error("--engine and --output are required for a benchmark")
    if not 2 <= args.repeats <= 30 or not 1 <= args.concurrency_seconds <= 300:
        parser.error("Use 2..30 repeats and 1..300 seconds per concurrency phase")
    if args.output.exists():
        raise ValueError("Output exists")
    if args.cgroup:
        # Moving from WSL's init.scope requires write access to the common ancestor.
        # The root helper moves only this benchmark PID; it does not change system permissions.
        subprocess.run(
            [
                "/mnt/c/Windows/System32/wsl.exe",
                "-d",
                "Ubuntu",
                "-u",
                "root",
                "--",
                "sh",
                "-c",
                f"echo {os.getpid()} > /sys/fs/cgroup/itadb-storage-benchmark/cgroup.procs",
            ],
            check=True,
        )
    queries = json.loads((args.root / "workload.json").read_text())
    # Reassign reclaimable file-cache pages to this isolated benchmark where possible.
    # This is an advisory eviction for experiment artifacts, not a global cache flush.
    artifacts = [args.root / "population.duckdb", *list((args.root / "rust").glob("*.bin"))]
    for artifact in artifacts:
        with artifact.open("rb") as stream:
            os.posix_fadvise(stream.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    expected_path = args.root / "expected.json"
    expected = json.loads(expected_path.read_text()) if expected_path.exists() else {}
    if not expected and args.engine != "postgres":
        raise ValueError("Establish the source PostgreSQL baseline first")
    started = time.monotonic()
    store = (
        RustStore(args.root)
        if args.engine == "rust"
        else SQLStore(args.root, args.engine, args.pagination)
    )
    result = {
        "engine": args.engine,
        "pagination": "legacy" if args.engine == "postgres" else args.pagination,
        "startup_seconds": time.monotonic() - started,
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
        "platform": platform.platform(),
        "queries": {},
        "concurrency": {},
        "limits": {
            "native_cgroup_cpu": None,
            "native_cgroup_memory_gib": None,
            "postgres_server_cpu": None,
            "postgres_server_memory_gib": None,
        },
        "cache": "new process; OS cache not flushed; Rust verifies file hashes on open",
    }
    if args.cgroup:
        result["cgroup_before_open_note"] = (
            "Experiment files received POSIX_FADV_DONTNEED before open; advisory only. "
            "Python imports happened before cgroup entry; RSS/PSS reported separately."
        )
        result["limits"]["observed_cpu_max"] = (CGROUP / "cpu.max").read_text().strip()
        result["limits"]["observed_memory_max"] = int((CGROUP / "memory.max").read_text())
        quota, period = result["limits"]["observed_cpu_max"].split()
        result["limits"]["native_cgroup_cpu"] = int(quota) / int(period)
        result["limits"]["native_cgroup_memory_gib"] = (
            result["limits"]["observed_memory_max"] / 2**30
        )
    is_pg = args.engine.startswith("postgres")
    if is_pg:
        host = json.loads(
            subprocess.check_output(
                ["docker", "inspect", "itadb-db-1", "--format", "{{json .HostConfig}}"], text=True
            )
        )
        result["limits"]["postgres_server_cpu"] = host["NanoCpus"] / 1e9 or None
        result["limits"]["postgres_server_memory_gib"] = host["Memory"] / 2**30 or None
    for label, query in [] if args.only_concurrency else queries.items():
        samples = []
        before_cpu = cpu_seconds()
        before_pg = pg_resources() if is_pg else None
        for _ in range(args.repeats):
            before = time.perf_counter()
            value = store.query(query)
            # Include the same canonical JSON serialization in every measured call.
            encoded = canonical(value)
            samples.append((time.perf_counter() - before) * 1000)
            actual = hashlib.sha256(encoded).hexdigest()
            if label in expected and actual != expected[label]:
                raise ValueError(f"Result mismatch: {args.engine}/{label}")
            expected[label] = actual
        after_cpu = cpu_seconds()
        after_pg = pg_resources() if is_pg else None
        result["queries"][label] = {
            **summary(samples),
            "result_sha256": actual,
            "response_bytes": len(encoded),
            "client_cpu_ms_per_query": (after_cpu - before_cpu) * 1000 / args.repeats,
            "server_cpu_ms_per_query": (
                (after_pg["cpu_seconds"] - before_pg["cpu_seconds"]) * 1000 / args.repeats
            )
            if is_pg
            else 0,
            "server_resources": after_pg,
        }
        print(
            f"{args.engine}: {label}: mediana {statistics.median(samples):.3f} ms; "
            f"hash verificato; trascorsi {time.monotonic() - started:.1f}s",
            flush=True,
        )
    if not expected_path.exists():
        with expected_path.open("x") as stream:
            json.dump(expected, stream, indent=2)
    # A deliberately declared mix; not an estimate of production user behavior.
    mix = [
        "point_city",
        "municipality_id_page",
        "municipality_age_desc",
        "household_members",
        "municipality_citizenship_filter",
        "municipality_distribution",
        "national_distribution",
    ]
    randomizer = random.Random(20260925)
    labels = mix.copy()
    randomizer.shuffle(labels)
    broad = [
        *labels,
        "municipality_sex_sort",
        "municipality_citizenship_sort",
        "municipality_household_sort",
    ]
    for workers, active_labels, name in [
        (1, labels, "1"),
        (4, labels, "4"),
        (8, labels, "8"),
        (8, broad, "8_broad"),
    ]:

        def call(label):
            before = time.perf_counter()
            value = store.query(queries[label])
            encoded = canonical(value)
            elapsed = (time.perf_counter() - before) * 1000
            if hashlib.sha256(encoded).hexdigest() != expected[label]:
                raise ValueError(f"Concurrent mismatch: {label}")
            return elapsed

        before_pg = pg_resources() if is_pg else None
        before_cpu = cpu_seconds()
        before = time.perf_counter()
        deadline = before + args.concurrency_seconds

        def client_loop(index, active_labels=active_labels, deadline=deadline):
            durations = []
            order = (
                active_labels[index % len(active_labels) :]
                + active_labels[: index % len(active_labels)]
            )
            while time.perf_counter() < deadline:
                durations.extend(call(label) for label in order)
            return durations

        with ThreadPoolExecutor(max_workers=workers) as pool:
            durations = [
                duration for batch in pool.map(client_loop, range(workers)) for duration in batch
            ]
        elapsed = time.perf_counter() - before
        used_cpu = cpu_seconds() - before_cpu
        after_pg = pg_resources() if is_pg else None
        if is_pg:
            used_cpu += after_pg["cpu_seconds"] - before_pg["cpu_seconds"]
        result["concurrency"][name] = {
            **summary(durations),
            "mix": active_labels,
            "requests": len(durations),
            "wall_seconds": elapsed,
            "requests_per_second": len(durations) / elapsed,
            "total_cpu_seconds": used_cpu,
            "cpu_ms_per_request": used_cpu * 1000 / len(durations),
            "server_resources": after_pg,
        }
        print(
            f"{args.engine}: {name} client: {len(durations) / elapsed:.1f} req/s; "
            f"p95 {result['concurrency'][name]['p95_ms']:.1f} ms; durata {elapsed:.1f}s",
            flush=True,
        )
    result["process_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    result["process_smaps_rollup_kib"] = {
        line.split(":")[0]: int(line.split()[1])
        for line in Path("/proc/self/smaps_rollup").read_text().splitlines()[1:]
    }
    if args.cgroup:
        result["cgroup_memory_current_bytes"] = int((CGROUP / "memory.current").read_text())
        result["cgroup_memory_stat"] = dict(
            (line.split()[0], int(line.split()[1]))
            for line in (CGROUP / "memory.stat").read_text().splitlines()
        )
    result["elapsed_seconds"] = time.monotonic() - started
    store.close()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
