"""Bounded downloads from curated official URLs, with visible progress."""

import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from itadb.connectors.sdmx import SOURCES, AcquiredArtifact, SdmxConnector
from itadb.pipeline.storage import archive_file, atomic_json

ALLOWED_HOSTS = {"www.istat.it", "esploradati.istat.it", "demo.istat.it", "ec.europa.eu"}


def fetch_static(
    root: Path,
    url: str,
    max_bytes: int,
    client: httpx.Client | None = None,
    accept: str = "*/*",
) -> AcquiredArtifact:
    """Only called by reviewed CLI contracts, never by a public URL parameter."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.fragment
        or not 1 <= max_bytes <= 100_000_000
    ):
        raise ValueError("Unsupported official URL or download budget")
    source = "eurostat" if parsed.hostname == "ec.europa.eu" else "istat"
    SdmxConnector(SOURCES[source], root)._wait_turn()
    temporary = root / "raw" / f".{uuid4().hex}.download"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    owned = client is None
    client = client or httpx.Client(
        verify=ssl.create_default_context(),
        timeout=httpx.Timeout(60, connect=10),
        follow_redirects=False,
    )
    try:
        with client.stream(
            "GET", url, headers={"User-Agent": "itadb/0.1", "Accept": accept}
        ) as response:
            response.raise_for_status()
            length = int(response.headers.get("content-length", "0"))
            if length > max_bytes:
                raise ValueError("Upstream exceeds download budget")
            size = 0
            last = time.monotonic()
            with temporary.open("xb") as output:
                for chunk in response.iter_bytes(256 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Upstream exceeds download budget")
                    output.write(chunk)
                    if time.monotonic() - last >= 2:
                        print(
                            f"Download {source}: {size:,} / {length or max_bytes:,} byte",
                            flush=True,
                        )
                        last = time.monotonic()
            if size == 0:
                raise ValueError("Empty upstream response")
            path, checksum = archive_file(temporary, root / "raw")
            manifest = path.parent / f"acquisition-{uuid4().hex}.json"
            atomic_json(
                manifest,
                {
                    "source": source,
                    "url": str(response.request.url),
                    "retrieved_at": datetime.now(UTC),
                    "sha256": checksum,
                    "bytes": size,
                    "content_type": response.headers.get("content-type", ""),
                    "status": "raw_only",
                    "license_review": "required_before_publication",
                },
            )
            print(f"Archiviati {size:,} byte; SHA-256 {checksum}", flush=True)
            return AcquiredArtifact(path, checksum, manifest)
    finally:
        temporary.unlink(missing_ok=True)
        if owned:
            client.close()
