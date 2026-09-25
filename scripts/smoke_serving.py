"""Replay verified responses over HTTP, against an immutable archive."""

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--clients", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = json.loads(args.checks.read_text())["checks"]
    now = time.monotonic()

    def request(check):
        query = "?" + urlencode(check["params"]) if check["params"] else ""
        start = time.perf_counter()
        with urlopen(args.url + check["path"] + query, timeout=30) as response:
            payload = json.load(response)
        actual = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert actual == check["response_sha256"], check["path"]
        return (time.perf_counter() - start) * 1000

    with ThreadPoolExecutor(max_workers=args.clients) as pool:
        times = []
        for result in pool.map(request, checks):
            times.append(result)
            if len(times) % 40 == 0:
                print(
                    f"HTTP verificato {len(times)}/{len(checks)}; {time.monotonic() - now:.1f} s",
                    flush=True,
                )
    times.sort()
    result = {
        "passed": len(times),
        "clients": args.clients,
        "elapsed_seconds": time.monotonic() - now,
        "p50_ms": times[len(times) // 2],
        "p95_ms": times[int(len(times) * 0.95)],
        "max_ms": max(times),
    }
    for metric in ("memory.peak", "memory.events", "cpu.stat", "cpu.max", "memory.max"):
        path = Path("/sys/fs/cgroup") / metric
        if path.exists():
            result[metric] = path.read_text().strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
