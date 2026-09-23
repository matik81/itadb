"""Acquire only the finite, reviewed M2 inventory; reuse verified archives."""

import json
from pathlib import Path
from uuid import uuid4

from itadb.connectors.static import fetch_static
from itadb.pipeline.storage import atomic_json, sha256_file


def acquire_m2(root: Path, contract: Path) -> Path:
    spec = json.loads(contract.read_text(encoding="utf-8"))
    if spec["name"] != "istat-m2" or spec["version"] != "1.0.0":
        raise ValueError("Unsupported M2 contract")
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
                    root / "quarantine" / f"m2-acquisition-{uuid4()}.json",
                    {"source": name, "published": False, "error_code": "SourceChanged"},
                )
                raise ValueError(
                    f"Source {name} changed; archive retained, contract review required"
                )
            found = result.manifest_path
        else:
            print("Archivio verificato riutilizzato", flush=True)
        inventory[name] = str(found)
    output = root / "state" / f"m2-inputs-{uuid4()}.json"
    atomic_json(output, inventory)
    return output
