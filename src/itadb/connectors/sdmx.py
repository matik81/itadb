import ssl
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote
from uuid import uuid4

import httpx
from filelock import FileLock

from itadb.pipeline.storage import archive_file, atomic_json


@dataclass(frozen=True)
class SourceDefinition:
    id: str
    base_url: str
    interval_seconds: float
    docs_url: str


SOURCES = {
    "istat": SourceDefinition(
        "istat",
        "https://esploradati.istat.it/SDMXWS/rest",
        15,
        "https://www.istat.it/classificazioni-e-strumenti/web-services-sdmx/",
    ),
    "eurostat": SourceDefinition(
        "eurostat",
        "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1",
        2,
        "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access",
    ),
}


@dataclass(frozen=True)
class AcquiredArtifact:
    path: Path
    sha256: str
    manifest_path: Path


class SourceConnector(Protocol):
    def fetch(self, flow: str, key: str, start: str, end: str) -> AcquiredArtifact: ...


class SdmxConnector:
    """Bounded SDMX-CSV acquisition. Mapping/DSD validation is a separate adapter.

    The lock is shared by processes using the same data directory. Multi-host
    workers behind one IP require a central outbound limiter (see sources.md).
    """

    def __init__(
        self,
        source: SourceDefinition,
        root: Path,
        client: httpx.Client | None = None,
        max_bytes: int = 100_000_000,
    ):
        self.source = source
        self.root = root
        self.client = client
        self.max_bytes = max_bytes

    def _wait_turn(self) -> None:
        state = self.root / "state"
        state.mkdir(parents=True, exist_ok=True)
        next_file = state / f"{self.source.id}.next"
        with FileLock(str(state / f"{self.source.id}.lock"), timeout=120):
            next_at = float(next_file.read_text()) if next_file.exists() else 0.0
            time.sleep(max(0, min(next_at - time.time(), 60)))
            next_file.write_text(str(time.time() + self.source.interval_seconds))

    def fetch(self, flow: str, key: str, start: str, end: str) -> AcquiredArtifact:
        if not flow or not key or not start or not end:
            raise ValueError("A bounded flow, key and period range are required")
        url = f"{self.source.base_url}/data/{quote(flow, safe=',')}/{quote(key, safe='.+')}"
        params = {"startPeriod": start, "endPeriod": end}
        headers = {
            "Accept": "application/vnd.sdmx.data+csv;version=1.0",
            "User-Agent": "itadb/0.1 (+https://github.com/matik81/itadb)",
        }
        client = self.client or httpx.Client(
            timeout=httpx.Timeout(60, connect=10),
            follow_redirects=False,
            verify=ssl.create_default_context(),
        )
        temporary = self.root / "raw" / f".{uuid4().hex}.download"
        temporary.parent.mkdir(parents=True, exist_ok=True)
        try:
            for attempt in range(3):
                self._wait_turn()
                try:
                    with client.stream("GET", url, params=params, headers=headers) as response:
                        if (
                            response.status_code == 429 or response.status_code >= 500
                        ) and attempt < 2:
                            retry = response.headers.get("Retry-After", "30")
                            try:
                                delay = float(retry)
                            except ValueError:
                                try:
                                    delay = (
                                        parsedate_to_datetime(retry) - datetime.now(UTC)
                                    ).total_seconds()
                                except (ValueError, TypeError):
                                    delay = 60.0
                            if delay > 60:
                                response.raise_for_status()
                            time.sleep(max(15, delay))
                            continue
                        response.raise_for_status()
                        if response.status_code != 200:
                            raise ValueError("Expected synchronous HTTP 200; narrow the query")
                        content_type = response.headers.get("content-type", "").lower()
                        if "csv" not in content_type:
                            raise ValueError(
                                "Provider did not return SDMX-CSV; inspect its DSD/format"
                            )
                        size = 0
                        with temporary.open("wb") as output:
                            for chunk in response.iter_bytes(1024 * 1024):
                                size += len(chunk)
                                if size > self.max_bytes:
                                    raise ValueError(
                                        "Source response exceeds the configured byte limit"
                                    )
                                output.write(chunk)
                        if not size:
                            raise ValueError("Empty upstream response")
                        path, checksum = archive_file(temporary, self.root / "raw")
                        manifest = path.parent / f"acquisition-{uuid4().hex}.json"
                        atomic_json(
                            manifest,
                            {
                                "source": self.source.id,
                                "url": str(response.request.url),
                                "retrieved_at": datetime.now(UTC),
                                "sha256": checksum,
                                "bytes": size,
                                "content_type": content_type,
                                "etag": response.headers.get("etag"),
                                "last_modified": response.headers.get("last-modified"),
                                "status": "raw_only",
                                "license_review": "required_before_publication",
                            },
                        )
                        return AcquiredArtifact(path, checksum, manifest)
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    time.sleep(15 * (attempt + 1))
            raise RuntimeError("Upstream retry budget exhausted")
        finally:
            temporary.unlink(missing_ok=True)
            if self.client is None:
                client.close()
