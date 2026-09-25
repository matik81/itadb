"""Bounded concurrent readers, pinned to one verified immutable release per process."""

import json
import threading
from typing import Any

import duckdb

from itadb.config import Settings
from itadb.serving.archive import DATABASE, READ_CONFIG, ArchiveUnavailable, verify_archive


class ArchiveStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.directory = (settings.serving_dir / "current").resolve()
        self.connection: duckdb.DuckDBPyConnection | None = None
        self.slots = threading.BoundedSemaphore(settings.serving_concurrency)
        self.lock = threading.Lock()
        self.database = self.directory / DATABASE
        self.signature: tuple[int, int, int] | None = None
        try:
            verify_archive(self.directory)
            self.connection = duckdb.connect(
                str(self.database),
                read_only=True,
                config=READ_CONFIG,
            )
            self.connection.execute(f"SET threads={settings.duckdb_threads}")
            self.connection.execute(f"SET memory_limit='{settings.duckdb_memory_mb}MB'")
            self.connection.execute("SET TimeZone='UTC'")
            self.signature = self._signature()
        except (ArchiveUnavailable, OSError, duckdb.Error):
            # Keep liveness available, fail readiness and requests without exposing paths.
            self.close()

    def _signature(self) -> tuple[int, int, int]:
        stat = self.database.stat()
        return stat.st_ino, stat.st_size, stat.st_mtime_ns

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            valid = self.connection is not None and self._signature() == self.signature
        except OSError:
            valid = False
        if not valid or not self.slots.acquire(timeout=self.settings.serving_timeout_seconds):
            raise ArchiveUnavailable("Archive unavailable or busy")
        try:
            with self.lock:
                assert self.connection is not None
                cursor = self.connection.cursor()
            timer = threading.Timer(self.settings.serving_timeout_seconds, cursor.interrupt)
            timer.daemon = True
            try:
                timer.start()
                # DuckDB cursors are independent sessions: timezone is not inherited
                # from SET on the parent connection. Keep timestamp JSON portable.
                cursor.execute("SET TimeZone='UTC'")
                result = cursor.execute(sql.replace("%s", "?"), params)
                description = result.description
                rows = result.fetchall()
                return [
                    {
                        col[0]: json.loads(value)
                        if str(col[1]) == "JSON" and value is not None
                        else value
                        for col, value in zip(description, row, strict=True)
                    }
                    for row in rows
                ]
            finally:
                timer.cancel()
                timer.join()
                cursor.close()
        finally:
            self.slots.release()
