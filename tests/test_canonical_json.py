from pathlib import Path

from itadb.pipeline.storage import atomic_json


def test_json_identity_is_independent_of_platform_newlines(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    atomic_json(path, {"source": "Istat", "count": 42})
    assert path.read_bytes() == b'{\n  "source": "Istat",\n  "count": 42\n}\n'
