import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.pipeline.runner import ingest_demo
from itadb.pipeline.validate import QualityError

pytestmark = pytest.mark.integration
FIXTURE = Path("tests/fixtures/population-demo.csv")
CONTRACT = Path("contracts/population-demo-v1.json")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    admin = os.environ.get("ITADB_TEST_DATABASE_URL")
    reader = os.environ.get("ITADB_TEST_READER_URL")
    if not admin or not reader:
        pytest.skip("Explicit disposable PostgreSQL admin and reader URLs required")
    return Settings(
        admin_database_url=admin, database_url=reader, data_dir=tmp_path, _env_file=None
    )


def test_end_to_end_idempotency_read_only_and_immutability(settings: Settings) -> None:
    release = ingest_demo(settings, FIXTURE, CONTRACT)
    assert ingest_demo(settings, FIXTURE, CONTRACT) == release
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        assert db.execute(
            "SELECT count(*) FROM stats.observation WHERE release_id=%s", (release,)
        ).fetchone() == (3,)
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute("UPDATE stats.observation SET value=9 WHERE release_id=%s", (release,))
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute("DELETE FROM catalog.release WHERE id=%s", (release,))
        plan = db.execute(
            "EXPLAIN (FORMAT JSON) SELECT * FROM stats.observation WHERE release_id=%s", (release,)
        ).fetchone()[0]
        import json

        assert json.dumps(plan).count('"Relation Name": "observation_p') == 1
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        response = client.get(
            "/v1/observations",
            params={"release_id": str(release), "period": "2025-01-01", "limit": 2},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        assert response.json()["next_cursor"] is not None
        assert client.get(f"/v1/releases/{release}/quality").json()
    with (
        psycopg.connect(settings.database_url, autocommit=True) as db,
        pytest.raises(psycopg.Error),
    ):
        db.execute("INSERT INTO catalog.source VALUES ('bad','bad','bad','bad',false)")


def test_failed_quality_gate_records_run_without_publishing(settings: Settings) -> None:
    source = settings.data_dir / "invalid.csv"
    source.write_text(FIXTURE.read_text().replace(",1200", ",-1200"))
    with psycopg.connect(settings.admin_database_url) as db:
        before = db.execute("SELECT count(*) FROM catalog.release").fetchone()
    with pytest.raises(QualityError):
        ingest_demo(settings, source, CONTRACT)
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute("SELECT count(*) FROM catalog.release").fetchone() == before
        assert (
            db.execute(
                "SELECT count(*) FROM catalog.pipeline_run WHERE status='failed'"
            ).fetchone()[0]
            > 0
        )
    assert list((settings.data_dir / "quarantine").glob("*.json"))
