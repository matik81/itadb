"""Functional tooling, retry and evidence preservation."""

import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from itadb.cli import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("command", "family"),
    [
        ("fetch-national-inputs", "istat-m4-national"),
        ("fetch-pilot-inputs", "istat-m3-valle-aosta"),
        ("fetch-territorial-aggregates", "istat-m2"),
    ],
)
def test_acquisition_cli_retries_reuse_archives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, family: str
) -> None:
    payload = b"invented source"
    digest = hashlib.sha256(payload).hexdigest()
    folder = tmp_path / "raw" / digest[:2] / digest
    folder.mkdir(parents=True)
    (folder / "payload").write_bytes(payload)
    meta = {"sha256": digest, "url": "https://www.istat.it/fixture", "bytes": len(payload)}
    acquisition = folder / "acquisition-fixture.json"
    acquisition.write_text(json.dumps(meta))
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"name": family, "version": "1.0.0", "sources": {"fixture": meta}})
    )
    monkeypatch.setenv("ITADB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "itadb.connectors.inventory.fetch_static",
        lambda *a, **kw: pytest.fail("An archived source must not require network access"),
    )
    inventories = []
    for _ in range(2):
        result = CliRunner().invoke(app, [command, "--contract", str(contract)])
        assert result.exit_code == 0, result.output
        inventories.append(Path(result.output.strip().splitlines()[-1]))
    assert inventories[0] != inventories[1]
    assert all(json.loads(p.read_text()) == {"fixture": str(acquisition)} for p in inventories)
    assert (folder / "payload").read_bytes() == payload


@pytest.mark.parametrize(
    "entrypoint",
    [
        ["scripts/benchmark_population_api.py"],
        ["-m", "scripts.benchmarks.population_api"],
    ],
)
def test_query_benchmark_refuses_to_overwrite_evidence(
    tmp_path: Path, entrypoint: list[str]
) -> None:
    output = tmp_path / "measurement.json"
    output.write_bytes(b"previous measurement")
    result = subprocess.run(
        [sys.executable, *entrypoint, "--snapshot", "1", "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "output already exists" in result.stderr
    assert output.read_bytes() == b"previous measurement"


def test_documentation_checker_detects_broken_moves_and_anchors(tmp_path: Path) -> None:
    checker = runpy.run_path(str(ROOT / "scripts/check_docs.py"))
    target = tmp_path / "moved.md"
    target.write_text("# Qualità e dati\n\n## Ripresa\n\n## Ripresa\n")
    index = tmp_path / "README.md"
    index.write_text(
        "[ok](moved.md#qualità-e-dati)\n[duplicate](moved.md#ripresa-1)\n"
        "[old](old.md)\n[anchor](moved.md#absent)\n"
        "[external](https://example.org/anything)\n"
        "```md\n[example](does-not-exist.md)\n```\n"
    )
    errors = checker["check_links"](tmp_path, [index])
    assert len(errors) == 2
    assert any("missing file: old.md" in error for error in errors)
    assert any("missing anchor: moved.md#absent" in error for error in errors)
