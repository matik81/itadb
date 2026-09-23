from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_istat_publication import _database

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.pipeline import publish_coverage as publication
from itadb.pipeline.coverage import Bundle
from itadb.pipeline.publish_coverage import publish_coverage
from itadb.pipeline.publish_istat import RevisionConflict
from itadb.pipeline.validate import QualityError

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    return _database(tmp_path, monkeypatch)


def test_publication_api_history_boundaries_and_immutability(
    settings: Settings, m2_bundle: tuple[Bundle, Path]
) -> None:
    bundle, contract = m2_bundle
    rid = publish_coverage(settings, bundle, contract)
    assert publish_coverage(settings, bundle, contract) == rid
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/v1/releases/{rid}").status_code == 404
        assert client.get(f"/v2/releases/{rid}").json()["is_demo"] is True
        assert len(client.get(f"/v2/releases/{rid}/coverage").json()) == 10
        params = {
            "release_id": str(rid),
            "series": "m2_test_total",
            "period": "2021-01-01",
            "level": "region",
            "limit": 1,
        }
        first = client.get("/v2/observations", params=params).json()
        second = client.get(
            "/v2/observations", params={**params, "after": first["next_cursor"]}
        ).json()
        assert len(first["items"]) == len(second["items"]) == 1
        assert first["items"][0]["territory_id"] != second["items"][0]["territory_id"]
        assert second["next_cursor"] is None
        territories = client.get(
            "/v2/territories",
            params={"release_id": str(rid), "snapshot": "2021-01-01", "level": "region"},
        ).json()
        tid = territories["items"][0]["territory_id"]
        boundary = client.get(f"/v2/releases/{rid}/territories/{tid}/boundary").json()
        assert boundary["geometry"]["type"] == "MultiPolygon"
        cross = client.get("/v2/crosswalks", params={"release_id": str(rid), "limit": 2}).json()
        assert cross["next_cursor"] is not None
        rest = client.get(
            "/v2/crosswalks", params={"release_id": str(rid), "after": cross["next_cursor"]}
        ).json()
        assert len(cross["items"] + rest["items"]) == 4
        assert all(
            row["allocation_weight"] is None
            for row in cross["items"] + rest["items"]
            if row["kind"] == "split"
        )
        assert client.get("/v2/territories", params={"release_id": str(rid)}).status_code == 422
        assert (
            client.get("/v2/crosswalks", params={"release_id": str(rid), "limit": 501}).status_code
            == 422
        )
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        for statement in [
            "UPDATE catalog.coverage SET row_count=row_count+1 WHERE release_id=%s",
            "DELETE FROM geo.release_territory WHERE release_id=%s",
            "DELETE FROM geo.crosswalk WHERE release_id=%s",
            "DELETE FROM geo.change_event WHERE release_id=%s",
            "DELETE FROM geo.boundary WHERE release_id=%s",
            "UPDATE geo.territory SET name='changed' WHERE id IN "
            "(SELECT territory_id FROM geo.release_territory WHERE release_id=%s)",
        ]:
            with pytest.raises(psycopg.Error):
                db.execute(statement, (rid,))
    with (
        psycopg.connect(settings.database_url, autocommit=True) as db,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        db.execute("SELECT * FROM geo.crosswalk")


def test_concurrency_revision_and_no_forks(
    settings: Settings, m2_bundle: tuple[Bundle, Path]
) -> None:
    b, c = m2_bundle
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: publish_coverage(settings, b, c), range(2)))
    assert results[0] == results[1]
    revised = b.model_copy(deep=True)
    for o in revised.observations:
        o.value *= 2
    with pytest.raises(RevisionConflict):
        publish_coverage(settings, revised, c)
    newer = publish_coverage(settings, revised, c, results[0], "Revisione della fixture inventata")
    assert newer != results[0]
    fork = b.model_copy(deep=True)
    for o in fork.observations:
        o.value *= 3
    with pytest.raises(RevisionConflict):
        publish_coverage(settings, fork, c, results[0], "Predecessore obsoleto")


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE catalog.coverage SET scheme='wrong' WHERE release_id=%s",
        "UPDATE geo.release_territory SET snapshot='2030-01-01' WHERE release_id=%s",
        "DELETE FROM geo.boundary WHERE release_id=%s",
    ],
)
def test_database_rechecks_draft_before_publication(
    settings: Settings,
    m2_bundle: tuple[Bundle, Path],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    bundle, contract = m2_bundle
    original = publication._load_observations
    called = []

    def tamper(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        db, rid = args[:2]
        db.execute(mutation, (rid,))
        called.append(True)

    monkeypatch.setattr(publication, "_load_observations", tamper)
    with pytest.raises(psycopg.Error):
        publish_coverage(settings, bundle, contract)
    assert called == [True]
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute("SELECT count(*) FROM catalog.release").fetchone() == (0,)


def test_derived_parents_follow_municipal_partition(
    settings: Settings, m2_bundle: tuple[Bundle, Path]
) -> None:
    bundle, contract = m2_bundle
    bundle.derive_parent_boundaries = True
    rid = publish_coverage(settings, bundle, contract)
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute(
            """SELECT count(*) FROM geo.boundary b
            JOIN geo.territory t ON t.id=b.territory_id
            JOIN geo.boundary p ON p.territory_id=t.parent_id AND p.release_id=b.release_id
            WHERE b.release_id=%s AND NOT ST_CoveredBy(b.geom,p.geom)""",
            (rid,),
        ).fetchone() == (0,)


@pytest.mark.parametrize("failure", ["quality", "evidence", "after_copy", "geometry"])
def test_failed_run_keeps_quarantine_without_partial_release(
    settings: Settings,
    m2_bundle: tuple[Bundle, Path],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    b, c = m2_bundle
    if failure == "quality":
        b.observations[0].value += 1
    elif failure == "evidence":
        b.evidence[0].sha256 = "f" * 64
    elif failure == "geometry":
        b.boundaries[0].source_srid = 32632
    else:
        original = publication._load_observations

        def crash(*args: Any, **kwargs: Any) -> None:
            original(*args, **kwargs)
            raise RuntimeError("Injected post-COPY failure")

        monkeypatch.setattr(publication, "_load_observations", crash)
    with pytest.raises((QualityError, ValueError, RuntimeError, psycopg.Error)):
        publish_coverage(settings, b, c)
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute(
            "SELECT count(*) FROM catalog.release WHERE dataset_id='demo_m2'"
        ).fetchone() == (0,)
        assert db.execute(
            "SELECT status FROM catalog.pipeline_run ORDER BY started_at DESC LIMIT 1"
        ).fetchone() == ("failed",)
        assert db.execute("SELECT count(*) FROM geo.crosswalk").fetchone() == (0,)
    assert list(settings.data_dir.joinpath("quarantine").glob("coverage-*.json"))
