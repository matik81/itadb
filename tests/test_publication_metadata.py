import json
from pathlib import Path

from itadb.pipeline.publish_istat import metadata_fingerprint
from itadb.pipeline.storage import sha256_file


def test_checked_in_contract_hashes_are_portable() -> None:
    onboarding = Path("contracts/istat-population-regions-v1.json")
    publication = Path("contracts/istat-population-publication-v1.json")
    spec = json.loads(publication.read_text(encoding="utf-8"))
    assert spec["onboarding_contract_sha256"] == sha256_file(onboarding)
    assert b"\r\n" not in onboarding.read_bytes()
    assert b"\r\n" not in publication.read_bytes()


def test_response_header_is_not_a_statistical_revision(tmp_path: Path) -> None:
    structure = Path("tests/fixtures/istat-population-structure.xml")
    original = Path("tests/fixtures/istat-population-dataflow.xml")
    updated = tmp_path / "dataflow.xml"
    text = original.read_text(encoding="utf-8")
    assert "IDREF247" in text
    updated.write_text(text.replace("IDREF247", "NEW_RESPONSE_ID"), encoding="utf-8")
    assert metadata_fingerprint(structure, original) == metadata_fingerprint(structure, updated)
    updated.write_text(
        text.replace("2026-03-31T08:03:43.724Z", "2026-04-01T00:00:00Z"), encoding="utf-8"
    )
    assert metadata_fingerprint(structure, original) != metadata_fingerprint(structure, updated)
