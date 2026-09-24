"""All counts here are invented and confined to explicitly configured test databases."""

import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.pipeline import publish_istat
from itadb.pipeline.publish_istat import RevisionConflict, ingest_istat_population
from itadb.pipeline.runner import ingest_demo
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.pipeline.validate import QualityError

pytestmark = pytest.mark.integration
FIXTURES = Path("tests/fixtures")


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    admin = os.environ.get("ITADB_TEST_DATABASE_URL")
    reader = os.environ.get("ITADB_TEST_READER_URL")
    if not admin or not reader:
        pytest.skip("Explicit disposable PostgreSQL admin and reader URLs required")
    # A fresh database per case preserves evidence and keeps test order irrelevant.
    name = "itadb_m1_test_" + uuid4().hex[:16]
    with psycopg.connect(admin, autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    isolated_admin = make_conninfo(admin, dbname=name)
    isolated_reader = make_conninfo(reader, dbname=name)
    # Alembic expects a URL, while the Settings supplied to psycopg can use conninfo.
    from sqlalchemy.engine import URL

    parts = conninfo_to_dict(isolated_admin)
    migration_url = URL.create(
        "postgresql",
        username=parts["user"],
        password=parts.get("password"),
        host=parts.get("host"),
        port=int(parts.get("port", "5432")),
        database=name,
    )
    monkeypatch.setenv(
        "ITADB_ADMIN_DATABASE_URL", migration_url.render_as_string(hide_password=False)
    )
    command.upgrade(Config("alembic.ini"), "head")
    command.upgrade(Config("alembic.ini"), "head")
    with psycopg.connect(isolated_admin) as db:
        role = sql.Identifier(conninfo_to_dict(reader)["user"])
        db.execute(sql.SQL("GRANT USAGE ON SCHEMA api TO {}").format(role))
        db.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA api TO {}").format(role))
        db.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO {}").format(
                role
            )
        )
    return Settings(
        admin_database_url=isolated_admin,
        database_url=isolated_reader,
        data_dir=tmp_path,
        _env_file=None,
    )


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    return _database(tmp_path, monkeypatch)


def test_repeated_upgrade_preserves_published_demo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _database(tmp_path, monkeypatch)
    release = ingest_demo(
        legacy, FIXTURES / "population-demo.csv", Path("contracts/population-demo-v1.json")
    )
    with TestClient(create_app(legacy)) as client:
        before = client.get(f"/v1/releases/{release}").json()
    command.upgrade(Config("alembic.ini"), "head")
    command.upgrade(Config("alembic.ini"), "head")
    assert (
        ingest_demo(
            legacy, FIXTURES / "population-demo.csv", Path("contracts/population-demo-v1.json")
        )
        == release
    )
    with TestClient(create_app(legacy)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/v1/releases/{release}").json() == before
        assert client.get(f"/v2/releases/{release}").json()["is_demo"] is True


def inputs(root: Path, delta: int = 0) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    license_path = root / "test-license.txt"
    license_path.write_text("Invented test evidence; never publish this fixture as official data.")
    onboarding = json.loads(
        Path("contracts/istat-population-regions-v1.json").read_text(encoding="utf-8")
    )
    onboarding["license"]["evidence_sha256"] = sha256_file(license_path)
    onboarding_path = root / "onboarding.json"
    atomic_json(onboarding_path, onboarding)
    publication = json.loads(Path("contracts/istat-population-publication-v1.json").read_text())
    publication["onboarding_contract_sha256"] = sha256_file(onboarding_path)
    publication["license_evidence_sha256"] = sha256_file(license_path)
    publication_path = root / "publication.json"
    atomic_json(publication_path, publication)
    with (FIXTURES / "istat-population-invented.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["OBS_VALUE"] = str(int(rows[0]["OBS_VALUE"]) + delta)
    rows[1]["OBS_VALUE"] = str(int(rows[1]["OBS_VALUE"]) + delta)
    source = root / "invented.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    key = "A." + "+".join(onboarding["territories"]) + ".JAN.9.TOTAL.99"
    base = "https://esploradati.istat.it/SDMXWS/rest"
    artifacts = {
        "acquisition": (
            source,
            f"{base}/data/IT1,22_289_DF_DCIS_POPRES1_1,1.0/{key}?startPeriod=2024-01-01&endPeriod=2024-01-01",
        ),
        "structure": (
            FIXTURES / "istat-population-structure.xml",
            f"{base}/datastructure/IT1/DCIS_POPRES1/1.0?references=all",
        ),
        "dataflow": (
            FIXTURES / "istat-population-dataflow.xml",
            f"{base}/dataflow/IT1/22_289_DF_DCIS_POPRES1_1/1.0?references=none",
        ),
    }
    result = {
        "onboarding_contract": onboarding_path,
        "publication_contract": publication_path,
        "license_evidence": license_path,
    }
    for name, (path, url) in artifacts.items():
        raw, checksum = archive_file(path, root / "raw")
        manifest = raw.parent / f"acquisition-{uuid4().hex}.json"
        atomic_json(
            manifest,
            {
                "source": "istat",
                "url": url,
                "retrieved_at": "2026-09-22T23:34:58+00:00",
                "sha256": checksum,
                "bytes": raw.stat().st_size,
            },
        )
        result[name] = manifest
    return result


def test_publication_roundtrip_and_retry(settings: Settings) -> None:
    args = inputs(settings.data_dir / "inputs")
    release = ingest_istat_population(settings, **args)
    assert ingest_istat_population(settings, **args) == release
    # New acquisition manifests/timestamps are not new statistical releases.
    assert ingest_istat_population(settings, **inputs(settings.data_dir / "retry")) == release
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute(
            "SELECT count(*) FROM stats.observation WHERE release_id=%s", (release,)
        ).fetchone() == (21,)
        assert db.execute(
            "SELECT count(*) FROM catalog.pipeline_run WHERE status='succeeded'"
        ).fetchone() == (3,)
        artifacts = db.execute(
            "SELECT uri,sha256 FROM catalog.artifact WHERE release_id=%s", (release,)
        ).fetchall()
        assert len(artifacts) == 12
        for uri, checksum in artifacts:
            assert sha256_file(settings.data_dir / uri) == checksum
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/v1/releases/{release}").status_code == 404
        assert client.get("/v1/releases").json() == []
        detail = client.get(f"/v2/releases/{release}").json()
        assert detail["is_demo"] is False
        assert detail["series_code"] == "resident_population_jan1"
        assert detail["upstream_published_at"] is None
        assert detail["supersedes_release_id"] is None
        params = {
            "release_id": str(release),
            "series": detail["series_code"],
            "period": "2024-01-01",
            "limit": 8,
        }
        collected: list[dict[str, Any]] = []
        while True:
            response = client.get("/v2/observations", params=params)
            assert response.status_code == 200, response.text
            page = response.json()
            collected.extend(page["items"])
            if page["next_cursor"] is None:
                break
            params["after"] = page["next_cursor"]
        assert len({r["territory_id"] for r in collected}) == 21
        country = next(r for r in collected if r["level"] == "country")
        assert country["value"] == "210000.000000"
        assert sum(r["level"] == "region" for r in collected) == 20
        assert all(r["parent_code"] == "IT" for r in collected if r["level"] == "region")
        assert {r["status"] for r in collected} == {"unflagged_upstream"}
        assert len(client.get(f"/v2/releases/{release}/artifacts").json()) == 12
        assert all(q["passed"] for q in client.get(f"/v2/releases/{release}/quality").json())
        assert client.get("/v2/observations", params={**params, "limit": 501}).status_code == 422
    with psycopg.connect(settings.database_url, autocommit=True) as reader:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            reader.execute("SELECT * FROM catalog.release")
        with pytest.raises(psycopg.Error):
            reader.execute("DELETE FROM api.releases_v2")


def test_explicit_revision_preserves_previous_release(settings: Settings) -> None:
    original = ingest_istat_population(settings, **inputs(settings.data_dir / "first"))
    revised = inputs(settings.data_dir / "revised", delta=1)
    with pytest.raises(RevisionConflict):
        ingest_istat_population(settings, **revised)
    revision = ingest_istat_population(
        settings,
        **revised,
        supersedes=original,
        revision_reason="Correzione della fixture inventata",
    )
    assert original != revision
    assert (
        ingest_istat_population(
            settings,
            **revised,
            supersedes=original,
            revision_reason="Correzione della fixture inventata",
        )
        == revision
    )
    with pytest.raises(RevisionConflict):
        ingest_istat_population(
            settings,
            **inputs(settings.data_dir / "stale", delta=2),
            supersedes=original,
            revision_reason="Predecessore obsoleto",
        )
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        assert db.execute(
            "SELECT supersedes_release_id FROM catalog.release WHERE id=%s", (revision,)
        ).fetchone() == (original,)
        assert (
            db.execute(
                "SELECT value FROM api.observations_v2 WHERE release_id=%s AND territory_code='IT'",
                (original,),
            ).fetchone()[0]
            == 210000
        )
        assert db.execute("SELECT count(*) FROM geo.territory").fetchone() == (21,)
        for statement in [
            "UPDATE catalog.release SET upstream_last_update=now() WHERE id=%s",
            "UPDATE stats.observation SET upstream_note='changed' WHERE release_id=%s",
            "DELETE FROM catalog.artifact WHERE release_id=%s",
        ]:
            with pytest.raises(psycopg.errors.RaiseException):
                db.execute(statement, (original,))
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute("UPDATE geo.territory SET valid_to='2025-01-01'")


@pytest.mark.parametrize("invalid_delta", [-5000, 10**14])
def test_failed_gate_and_late_failure_leave_no_release(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, invalid_delta: int
) -> None:
    args = inputs(settings.data_dir / "invalid", delta=invalid_delta)
    with pytest.raises(QualityError):
        ingest_istat_population(settings, **args)
    actual_load = publish_istat._load

    def fail_after_copy(*args: Any, **kwargs: Any) -> None:
        actual_load(*args, **kwargs)
        raise RuntimeError("Injected failure after loading observations")

    monkeypatch.setattr(publish_istat, "_load", fail_after_copy)
    with pytest.raises(RuntimeError, match="Injected"):
        ingest_istat_population(settings, **inputs(settings.data_dir / "valid"))
    with psycopg.connect(settings.admin_database_url) as db:
        for table in ["catalog.release", "stats.observation", "geo.territory", "catalog.artifact"]:
            assert db.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(*table.split(".")))
            ).fetchone() == (0,)
        assert db.execute(
            "SELECT count(*) FROM catalog.pipeline_run WHERE status='failed'"
        ).fetchone() == (2,)
    assert len(list((settings.data_dir / "quarantine").glob("publication-*.json"))) == 2


def test_concurrent_imports_are_one_release(settings: Settings) -> None:
    args = inputs(settings.data_dir / "inputs")
    # Different local roots also exercise the database lock rather than just a file lock.
    other = settings.model_copy(update={"data_dir": settings.data_dir / "other-worker"})
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(ingest_istat_population, item, **args) for item in (settings, other)
        ]
        releases = [f.result(timeout=30) for f in futures]
    assert releases[0] == releases[1]
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute("SELECT count(*) FROM catalog.release").fetchone() == (1,)
        assert db.execute("SELECT count(*) FROM stats.observation").fetchone() == (21,)


def test_concurrent_revisions_cannot_fork(settings: Settings) -> None:
    original = ingest_istat_population(settings, **inputs(settings.data_dir / "first"))
    candidates = [inputs(settings.data_dir / str(delta), delta=delta) for delta in (1, 2)]
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(
                ingest_istat_population,
                settings,
                **args,
                supersedes=original,
                revision_reason="Revisione di test",
            )
            for args in candidates
        ]
        results = []
        for future in futures:
            try:
                results.append(future.result(timeout=30))
            except RevisionConflict:
                results.append(None)
    assert results.count(None) == 1
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute("SELECT count(*) FROM catalog.release").fetchone() == (2,)


def test_database_refuses_publication_without_provenance(settings: Settings) -> None:
    original = ingest_istat_population(settings, **inputs(settings.data_dir / "first"))
    draft = uuid4()
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        db.execute(
            """INSERT INTO catalog.release
            (id,dataset_id,reference_period,retrieved_at,upstream_url,raw_sha256,transform_version,
             contract_sha256,license_url,status,row_count,api_version,series_code,
             supersedes_release_id,revision_reason)
            SELECT %s,dataset_id,reference_period,retrieved_at,upstream_url,%s,transform_version,
             contract_sha256,license_url,'draft',row_count,2,series_code,id,'Test gate'
             FROM catalog.release WHERE id=%s""",
            (draft, "0" * 64, original),
        )
        db.execute(
            """INSERT INTO stats.observation
            (release_id,series_id,territory_id,period,value,status)
            SELECT %s,series_id,territory_id,period,value,status FROM stats.observation
            WHERE release_id=%s""",
            (draft, original),
        )
        db.execute("INSERT INTO catalog.quality_result VALUES (%s,'test',true,'{}')", (draft,))
        with pytest.raises(psycopg.errors.RaiseException, match="provenance"):
            db.execute(
                "UPDATE catalog.release SET status='published',published_at=now() WHERE id=%s",
                (draft,),
            )
        db.execute("UPDATE catalog.quality_result SET passed=false WHERE release_id=%s", (draft,))
        with pytest.raises(psycopg.errors.RaiseException, match="quality"):
            db.execute(
                "UPDATE catalog.release SET status='published',published_at=now() WHERE id=%s",
                (draft,),
            )
        assert db.execute("SELECT 1 FROM api.releases_v2 WHERE id=%s", (draft,)).fetchone() is None


def test_query_plan_on_twenty_thousand_artificial_observations(settings: Settings) -> None:
    release = uuid4()
    scheme = "TEST_PLAN_" + release.hex
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        db.execute(
            """INSERT INTO geo.territory(scheme,code,name,level,valid_from)
            SELECT %s,i::text,'Territorio artificiale '||i,'municipality','2025-01-01'
            FROM generate_series(1,20000) i""",
            (scheme,),
        )
        db.execute(
            """INSERT INTO catalog.release
            (id,dataset_id,reference_period,retrieved_at,upstream_url,raw_sha256,transform_version,
             contract_sha256,license_url,status,row_count)
            VALUES (%s,'demo_population','2025-01-01',now(),'test',%s,%s,%s,
                    'test','draft',20000)""",
            (release, "a" * 64, str(release), "b" * 64),
        )
        db.execute(
            """INSERT INTO stats.observation(release_id,series_id,territory_id,period,value,status)
            SELECT %s,s.id,t.id,'2025-01-01',1000,'demo'
            FROM geo.territory t CROSS JOIN stats.series s
            WHERE t.scheme=%s AND s.code='population_total'""",
            (release, scheme),
        )
        db.execute(
            "UPDATE catalog.release SET status='published',published_at=now() WHERE id=%s",
            (release,),
        )
        for relation in ("stats.observation", "geo.territory", "catalog.release", "stats.series"):
            db.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(*relation.split("."))))
    with psycopg.connect(settings.database_url) as reader:
        plan = reader.execute(
            """EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON)
            SELECT * FROM api.observations_v2 WHERE release_id=%s AND series_code='population_total'
            AND period='2025-01-01' AND territory_id>10000 ORDER BY territory_id LIMIT 51""",
            (release,),
        ).fetchone()[0]

    def nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
        return [node] + [child for item in node.get("Plans", []) for child in nodes(item)]

    observations = [
        n for n in nodes(plan[0]["Plan"]) if n.get("Relation Name", "").startswith("observation_p")
    ]
    assert len(observations) == 1
    assert "Index" in observations[0]["Node Type"]
    assert plan[0]["Plan"]["Actual Rows"] == 51
    evidence_path = Path("data/reports") / f"m1-query-plan-{release}.json"
    atomic_json(evidence_path, {"artificial_rows": 20000, "requested_rows": 51, "plan": plan})
    print(f"Query plan evidence: {evidence_path}")


def test_territorial_integrity(settings: Settings) -> None:
    release = ingest_istat_population(settings, **inputs(settings.data_dir / "inputs"))
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        territory = db.execute("SELECT scheme,id FROM geo.territory WHERE code='ITC1'").fetchone()
        with pytest.raises(psycopg.errors.ExclusionViolation):
            db.execute(
                "INSERT INTO geo.territory(scheme,code,name,level,valid_from,valid_to) "
                "VALUES (%s,'ITC1','Overlap','region','2023-12-31','2024-01-02')",
                (territory[0],),
            )
        with pytest.raises(psycopg.errors.RaiseException, match="hierarchy"):
            db.execute(
                "INSERT INTO geo.territory(scheme,code,name,level,valid_from,parent_id) "
                "VALUES ('WRONG','X','Wrong','region','2024-01-01',%s)",
                (territory[1],),
            )
        draft = uuid4()
        db.execute(
            """INSERT INTO catalog.release
            (id,dataset_id,reference_period,retrieved_at,upstream_url,raw_sha256,transform_version,
             contract_sha256,license_url,status,row_count)
             VALUES (%s,'demo_population','2025-01-01',now(),'test',%s,%s,%s,'test','draft',1)""",
            (draft, "a" * 64, str(draft), "b" * 64),
        )
        series = db.execute("SELECT id FROM stats.series WHERE code='population_total'").fetchone()[
            0
        ]
        with pytest.raises(psycopg.errors.RaiseException, match="validity"):
            db.execute(
                "INSERT INTO stats.observation"
                "(release_id,series_id,territory_id,period,value,status) "
                "VALUES (%s,%s,%s,'2024-01-02',1,'demo')",
                (draft, series, territory[1]),
            )
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/v2/releases/{draft}").status_code == 404
        assert client.get(f"/v2/releases/{draft}/artifacts").status_code == 404
        assert client.get(f"/v2/releases/{release}").status_code == 200
