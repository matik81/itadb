"""Acquire finite, reviewed source inventories; reuse verified archives."""

import json
from pathlib import Path
from uuid import uuid4

from itadb.connectors.static import fetch_static
from itadb.pipeline.storage import atomic_json, sha256_file


def acquire_territorial_aggregates(root: Path, contract: Path) -> Path:
    return acquire_inventory(root, contract, "istat-m2", "m2")


def acquire_inventory(root: Path, contract: Path, contract_name: str, prefix: str) -> Path:
    """Shared bounded archive acquisition for an explicitly selected contract family."""
    spec = json.loads(contract.read_text(encoding="utf-8"))
    if spec["name"] != contract_name or spec["version"] != "1.0.0":
        raise ValueError("Unsupported acquisition contract")
    inventory = {}
    for index, (name, source) in enumerate(spec["sources"].items(), 1):
        print(f"Fonte {index}/{len(spec['sources'])}: {name}", flush=True)
        checksum = source["sha256"]
        folder = root / "raw" / checksum[:2] / checksum
        found = None
        if (folder / "payload").exists() and sha256_file(folder / "payload") == checksum:
            for candidate in sorted(folder.glob("acquisition-*.json")):
                meta = json.loads(candidate.read_text(encoding="utf-8"))
                if all(meta.get(k) == source[k] for k in ("sha256", "url", "bytes")):
                    found = candidate
                    break
        if found is None:
            url = source["url"]
            accept = "*/*"
            if "/rest/data/" in url:
                accept = "application/vnd.sdmx.data+csv;version=1.0"
            elif "/rest/" in url:
                accept = "application/vnd.sdmx.structure+xml;version=2.1"
            result = fetch_static(root, url, min(source["bytes"] * 2, 50_000_000), accept=accept)
            if result.sha256 != checksum or result.path.stat().st_size != source["bytes"]:
                atomic_json(
                    root / "quarantine" / f"{prefix}-acquisition-{uuid4()}.json",
                    {"source": name, "published": False, "error_code": "SourceChanged"},
                )
                raise ValueError(
                    f"Source {name} changed; archive retained, contract review required"
                )
            found = result.manifest_path
        else:
            print("Archivio verificato riutilizzato", flush=True)
        inventory[name] = str(found)
    output = root / "state" / f"{prefix}-inputs-{uuid4()}.json"
    atomic_json(output, inventory)
    return output
