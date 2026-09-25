"""Archive executable sources and record the repository revision for synthesis."""

import subprocess
from pathlib import Path
from typing import Any

from itadb.pipeline.storage import archive_file


def implementation(root: Path) -> dict[str, str]:
    """Archive the executable source and dependency lock, including uncommitted changes."""
    source = Path(__file__).resolve().parents[1]
    files = sorted(source.rglob("*.py"))
    lock = Path("uv.lock")
    if not lock.is_file():
        raise ValueError("Run synthesis from the repository root with uv.lock")
    result = {}
    for path in [*files, lock]:
        _, digest = archive_file(path, root / "raw")
        result[path.relative_to(source).as_posix() if path != lock else "uv.lock"] = digest
    return result


def _commit() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = (
            subprocess.run(
                ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
            ).stdout
            != ""
        )
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"revision": None, "dirty": None}
