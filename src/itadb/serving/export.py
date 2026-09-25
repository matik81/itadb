"""Copy a verified published archive into a portable package without changing its data."""

import shutil
from pathlib import Path

from itadb.config import Settings
from itadb.serving.archive import DATABASE, verify_archive, write_json
from itadb.serving.publication import published_root


def export_archive(settings: Settings, directory: Path, evidence: Path) -> Path:
    if (directory / "manifest.json").exists():
        verify_archive(directory)
        print("Archivio esistente verificato; nessuna riscrittura", flush=True)
        return directory
    source = published_root(settings) / "current"
    if not source.exists() and not source.is_symlink():
        source = settings.serving_dir / "current"
    manifest = verify_archive(source.resolve())
    directory.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    try:
        for name in (DATABASE, "manifest.json"):
            shutil.copyfile(source / name, directory / name)
        verify_archive(directory)
        (directory / DATABASE).chmod(0o444)
        write_json(evidence / "export.json", {"verified": True, "database": manifest["database"]})
        print("Archivio completo verificato", flush=True)
        return directory
    except Exception as exc:
        write_json(evidence / "failure.json", {"error_type": type(exc).__name__})
        raise
