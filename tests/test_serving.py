"""Serving fixtures are invented; no database server or network is needed."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest
from fastapi.testclient import TestClient

from itadb.api.app import create_app
from itadb.api.duckdb_repository import DuckDBPopulationRepository, DuckDBRepositoryV2
from itadb.config import Settings
from itadb.serving.archive import (
    DATABASE,
    ArchiveUnavailable,
    activate_archive,
    create_schema,
    empty_archive,
    install_archive,
    seal_archive,
    verify_archive,
)
from itadb.serving.schema import SCHEMA
from itadb.serving.store import ArchiveStore


def fixture_archive(path: Path, label: str = "Inventato") -> Path:
    path.mkdir()
    with duckdb.connect(str(path / DATABASE)) as db:
        create_schema(db)
        db.execute(
            "INSERT INTO api.sources VALUES ('demo',?,'https://example.org','CC0',true)", [label]
        )
        db.execute(
            "INSERT INTO api.population_persons (snapshot_id,person_id,household_id,"
            "municipality_code,sex,birth_year,age,citizenship_code,reference_adult,"
            "age_is_lower_bound,data_kind) VALUES "
            "(1,1,NULL,900001,'F',1984,40,100,false,false,'synthetic'),"
            "(1,2,1,900001,'M',1984,40,100,true,false,'synthetic'),"
            "(1,3,1,900001,'F',2014,10,201,false,false,'synthetic'),"
            "(2,1,1,900001,'F',1974,50,100,true,false,'synthetic')"
        )
        db.execute(
            "INSERT INTO api.observations_v2 (release_id,territory_id,series_code,"
            "period,value) VALUES ('11111111-1111-4111-8111-111111111111',1,'fixture',"
            "'2025-01-01',0),('11111111-1111-4111-8111-111111111111',2,'fixture',"
            "'2025-01-01',NULL),('11111111-1111-4111-8111-111111111111',3,'fixture',"
            "'2025-01-01',1.234567)"
        )
        counts = {
            name: {"rows": db.execute(f"SELECT count(*) FROM api.{name}").fetchone()[0]}
            for name in SCHEMA
        }
        db.execute("CHECKPOINT")
    seal_archive(path, counts, "invented-test-fixture")
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    root = tmp_path / "serving"
    activate_archive(root, install_archive(fixture_archive(tmp_path / "archive"), root))
    return Settings(
        serving_dir=root, database_url="postgresql://invalid.invalid/unused", _env_file=None
    )


def test_serving_never_connects_postgres_and_preserves_openapi(settings: Settings) -> None:
    with (
        patch("psycopg.connect", side_effect=AssertionError("PostgreSQL used")),
        patch("itadb.api.app.ConnectionPool", side_effect=AssertionError("Pool used")),
        TestClient(create_app(settings)) as client,
    ):
        assert client.get("/health/ready").status_code == 200
        assert client.get("/v1/sources").json()[0]["name"] == "Inventato"
        assert client.get("/v2/sources").json()[0]["is_demo"] is True
        assert client.get("/v3/populations").json() == []
        assert client.get("/v3/populations/99").status_code == 404
        assert client.get("/v2/crosswalks").status_code == 422


def test_missing_and_corrupt_archives_fail_closed(tmp_path: Path, settings: Settings) -> None:
    for root in (tmp_path / "missing", settings.serving_dir):
        if root == settings.serving_dir:
            database = (root / "current" / DATABASE).resolve()
            database.chmod(0o644)
            with database.open("ab") as stream:
                stream.write(b"corruption")
        with TestClient(create_app(settings.model_copy(update={"serving_dir": root}))) as client:
            assert client.get("/health/live").status_code == 200
            for route in ("/health/ready", "/v1/sources", "/v3/populations"):
                response = client.get(route)
                assert response.status_code == 503
                assert response.headers["content-type"] == "application/problem+json"
                assert str(root) not in response.text


def test_install_retry_activation_rollback_and_pinned_readers(
    tmp_path: Path, settings: Settings
) -> None:
    root = settings.serving_dir
    previous = (root / "current").resolve()
    old = ArchiveStore(settings)
    second = fixture_archive(tmp_path / "second", "Seconda")
    installed = install_archive(second, root)
    assert install_archive(second, root) == installed
    activate_archive(root, installed)
    assert old.query("SELECT name FROM api.sources")[0]["name"] == "Inventato"
    new = ArchiveStore(settings)
    assert new.query("SELECT name FROM api.sources")[0]["name"] == "Seconda"
    new.close()
    activate_archive(root, previous)
    assert (root / "current").resolve() == previous
    assert verify_archive(installed)["tables"]["sources"]["rows"] == 1
    old.close()
    (second / DATABASE).chmod(0o644)
    with (second / DATABASE).open("ab") as stream:
        stream.write(b"broken")
    with pytest.raises(ArchiveUnavailable):
        install_archive(second, root)
    assert (root / "current").resolve() == previous
    with pytest.raises(ArchiveUnavailable):
        activate_archive(root, tmp_path)


def test_archive_is_read_only_and_concurrent(settings: Settings) -> None:
    store = ArchiveStore(settings)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            result = list(
                pool.map(lambda _: store.query("SELECT count(*) n FROM api.sources"), range(40))
            )
        assert all(r == [{"n": 1}] for r in result)
        for sql in ("DELETE FROM api.sources", "SELECT * FROM read_csv('/etc/passwd')"):
            with pytest.raises(duckdb.Error):
                store.query(sql)
    finally:
        store.close()


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("sort", ["person_id", "age", "sex", "citizenship_code", "household_id"])
def test_population_pages_ties_and_snapshot_isolation(
    settings: Settings, direction: str, sort: str
) -> None:
    store = ArchiveStore(settings)
    repo = DuckDBPopulationRepository(store)
    args = (1, "900001", None, None, 0, 100, sort, direction)
    try:
        full = repo.persons(*args, 0, 50)
        seen = []
        after = 0
        while page := repo.persons(*args, after, 1):
            seen.extend(page)
            after = page[-1]["person_id"]
        assert seen == full and len(seen) == 3
        assert all(p["age"] != 50 for p in seen)
        assert repo.persons(*args, 999, 5) == []
        assert repo.persons(1, "900001", "F", None, 0, 100, sort, direction, 2, 5) == []
    finally:
        store.close()


def test_null_last_decimal_and_cursor_values(settings: Settings) -> None:
    from datetime import date
    from decimal import Decimal
    from uuid import UUID

    store = ArchiveStore(settings)
    repo = DuckDBRepositoryV2(store)
    try:
        for direction, ids in [("asc", [1, 3, 2]), ("desc", [3, 1, 2])]:
            after = 0
            seen = []
            while rows := repo.observation_table(
                UUID("11111111-1111-4111-8111-111111111111"),
                "fixture",
                date(2025, 1, 1),
                None,
                after,
                1,
                "value",
                direction,
                None,
                None,
                None,
            ):
                seen.extend(rows)
                after = rows[-1]["territory_id"]
            assert [r["territory_id"] for r in seen] == ids
            assert next(r["value"] for r in seen if r["territory_id"] == 3) == Decimal("1.234567")
            assert next(r["value"] for r in seen if r["territory_id"] == 1) == Decimal("0.000000")
    finally:
        store.close()


def test_query_deadline_does_not_poison_connection(settings: Settings) -> None:
    store = ArchiveStore(settings.model_copy(update={"serving_timeout_seconds": 0.05}))
    try:
        with pytest.raises(duckdb.InterruptException):
            store.query("SELECT sum(sin(i)) FROM range(1000000000) t(i)")
        assert store.query("SELECT 1 n") == [{"n": 1}]
    finally:
        store.close()


def test_empty_installation_is_explicit_and_schema_is_required(tmp_path: Path) -> None:
    archive = empty_archive(tmp_path / "empty")
    assert all(t["rows"] == 0 for t in verify_archive(archive)["tables"].values())
    with pytest.raises(FileExistsError):
        empty_archive(archive)
    (archive / DATABASE).chmod(0o644)
    with duckdb.connect(str(archive / DATABASE)) as db:
        db.execute("DROP TABLE api.population_validation")
    with pytest.raises(ArchiveUnavailable):
        verify_archive(archive)
