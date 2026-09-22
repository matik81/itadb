import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(content, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def archive_file(source: Path, root: Path) -> tuple[Path, str]:
    """Copy bounded chunks and hash the copied bytes, never a mutable source twice."""
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".{uuid4().hex}.tmp"
    digest = hashlib.sha256()
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(chunk)
                writer.write(chunk)
        checksum = digest.hexdigest()
        target = root / checksum[:2] / checksum / "payload"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256_file(target) != checksum:
                raise ValueError("Content-addressed archive has been modified")
        else:
            os.replace(temporary, target)
        return target, checksum
    finally:
        temporary.unlink(missing_ok=True)
