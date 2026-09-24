"""Local resource measurements and progress; no optional monitoring dependencies."""

import os
import platform
import resource
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from itadb.synthesis.national_models import ResourceBudget


def peak_rss_bytes() -> int:
    # Linux reports ru_maxrss in KiB; expose bytes to the resource budget.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def disk_bytes(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            pass  # DuckDB spill files can disappear between enumeration and stat.
    return total


class RunMonitor:
    def __init__(self, directory: Path, budget: ResourceBudget, emit: Callable[[str], None]):
        self.directory, self.budget, self.emit = directory, budget, emit
        self.started = time.monotonic()
        self.peak_rss = 0
        self.peak_disk = 0
        self.error: str | None = None
        self.phase = "inizializzazione"
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _watch(self) -> None:
        tick = 0
        while not self.stop.wait(1):
            try:
                self.sample()
            except Exception as error:
                self.error = type(error).__name__
            tick += 1
            if tick % 10 == 0:
                self.emit(
                    f"{self.phase}; trascorsi {time.monotonic() - self.started:.1f}s; "
                    f"picco RAM {self.peak_rss / 2**20:.0f} MiB; "
                    f"disco {self.peak_disk / 2**20:.0f} MiB"
                )

    def sample(self) -> None:
        self.peak_rss = max(self.peak_rss, peak_rss_bytes())
        self.peak_disk = max(self.peak_disk, disk_bytes(self.directory))
        if self.peak_rss > self.budget.max_rss_mb * 2**20:
            self.error = "RSS budget exceeded"
        if self.peak_disk > self.budget.max_disk_mb * 2**20:
            self.error = "Disk budget exceeded"
        if time.monotonic() - self.started > self.budget.max_seconds:
            self.error = "Elapsed-time budget exceeded"

    def check(self, phase: str) -> None:
        self.phase = phase
        self.sample()
        if self.error:
            raise RuntimeError(self.error)
        self.emit(phase)

    def close(self) -> dict[str, Any]:
        self.stop.set()
        self.thread.join()
        self.sample()
        return {
            "elapsed_seconds": time.monotonic() - self.started,
            "peak_process_rss_bytes": self.peak_rss,
            "peak_disk_bytes_sampled": self.peak_disk,
            "disk_sample_interval_seconds": 1,
            "budget_passed": self.error is None,
            "hardware": {
                "platform": platform.system(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "logical_cpus": os.cpu_count(),
            },
            "budget": self.budget.model_dump(),
        }
