from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row
from test_istat_publication import _database

from itadb.api.app import create_app
from itadb.api.repository import PostgresRepositoryV2
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


def test_readiness_requires_each_m2_view(settings: Settings) -> None:
    with (
        psycopg.connect(settings.admin_database_url, autocommit=True) as db,
        TestClient(create_app(settings)) as client,
    ):
        assert client.get("/health/ready").status_code == 200
        for view in ["coverage_v2", "territories_v2", "crosswalks_v2", "boundaries_v2"]:
            db.execute(
                sql.SQL("ALTER VIEW api.{} RENAME TO unavailable").format(sql.Identifier(view))
            )
            try:
                assert client.get("/health/live").status_code == 200
                response = client.get("/health/ready")
                assert response.status_code == 503
                assert view not in response.text
            finally:
                db.execute(
                    sql.SQL("ALTER VIEW api.unavailable RENAME TO {}").format(sql.Identifier(view))
                )
            assert client.get("/health/ready").status_code == 200


def test_repeated_upgrade_preserves_published_m2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, m2_bundle: tuple[Bundle, Path]
) -> None:
    old = _database(tmp_path, monkeypatch)
    bundle, contract = m2_bundle
    rid = publish_coverage(old, bundle, contract)
    tables = [
        "catalog.release",
        "catalog.coverage",
        "catalog.artifact",
        "catalog.quality_result",
        "stats.observation",
        "geo.release_territory",
        "geo.change_event",
        "geo.crosswalk",
        "geo.boundary",
    ]

    def fingerprints() -> list[Any]:
        with psycopg.connect(old.admin_database_url) as db:
            return [
                db.execute(
                    sql.SQL(
                        "SELECT count(*), md5(string_agg(row_to_json(t)::text, '' "
                        "ORDER BY row_to_json(t)::text)) FROM {} t"
                    ).format(sql.SQL(table))
                ).fetchone()
                for table in tables
            ]

    before = fingerprints()
    command.upgrade(Config("alembic.ini"), "head")
    command.upgrade(Config("alembic.ini"), "head")
    assert fingerprints() == before
    assert publish_coverage(old, bundle, contract) == rid
    with TestClient(create_app(old)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/v2/releases/{rid}").status_code == 200


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


def test_sorted_filtered_tables_across_pages(
    settings: Settings, m2_bundle: tuple[Bundle, Path]
) -> None:
    bundle, contract = m2_bundle
    rid = publish_coverage(settings, bundle, contract)
    with TestClient(create_app(settings)) as client:

        def pages(endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            rows = []
            after = 0
            for _ in range(20):
                response = client.get(
                    endpoint, params={"release_id": str(rid), **params, "limit": 1, "after": after}
                )
                assert response.status_code == 200
                page = response.json()
                rows.extend(page["items"])
                if page["next_cursor"] is None:
                    return rows
                assert page["next_cursor"] != after
                after = page["next_cursor"]
            pytest.fail("Pagination did not terminate")

        base = {"series": "m2_test_total", "period": "2021-01-01", "level": "region"}
        for field, key in [
            ("name", "territory_name"),
            ("code", "territory_code"),
            ("value", "value"),
        ]:
            for direction in ["asc", "desc"]:
                rows = pages("/v2/observations", {**base, "sort_by": field, "direction": direction})
                assert len(rows) == 2
                values = [float(row[key]) if field == "value" else row[key] for row in rows]
                assert values == sorted(values, reverse=direction == "desc")
                assert len({row["territory_id"] for row in rows}) == 2
        rows = pages("/v2/observations", {**base, "sort_by": "name", "search": "r1"})
        assert [row["territory_code"] for row in rows] == ["R1"]
        assert pages("/v2/observations", {**base, "search": "%' OR 1=1 --"}) == []
        assert len(pages("/v2/observations", {**base, "parent_code": "IT", "status": "demo"})) == 2
        assert pages("/v2/observations", {**base, "parent_code": "R1"}) == []
        assert pages("/v2/observations", {**base, "status": "missing"}) == []
        for field, key in [
            ("date", "effective_date"),
            ("description", "description"),
            ("from_code", "from_code"),
            ("to_code", "to_code"),
            ("usage", "weight_basis"),
        ]:
            for direction in ["asc", "desc"]:
                rows = pages("/v2/crosswalks", {"sort_by": field, "direction": direction})
                assert len(rows) == len({row["id"] for row in rows}) == 4
                values = [row[key] for row in rows]
                assert values == sorted(values, reverse=direction == "desc")
        splits = pages("/v2/crosswalks", {"kind": "split", "weight_basis": "structural"})
        assert len(splits) == 2
        assert all(row["kind"] == "split" and row["weight_basis"] == "structural" for row in splits)
        assert pages("/v2/crosswalks", {"kind": "split", "weight_basis": "exact"}) == []


def test_sort_cursor_preserves_numeric_ties_and_nulls(settings: Settings) -> None:
    # A temporary, invented fixture exercises nulls that M2's complete bundle excludes.
    # No evidence or published observation is modified.
    with psycopg.connect(settings.admin_database_url, row_factory=dict_row) as db:
        db.execute("CREATE TEMP TABLE sort_fixture (territory_id bigint, value numeric)")
        db.execute("INSERT INTO sort_fixture VALUES (9,10),(2,2.5),(7,2.5),(4,NULL),(1,NULL),(3,0)")

        class FixtureRepository(PostgresRepositoryV2):
            def __init__(self) -> None:
                pass

            def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
                return list(db.execute(sql, params).fetchall())

        repo = FixtureRepository()
        for direction, expected in [("asc", [3, 2, 7, 9, 1, 4]), ("desc", [9, 2, 7, 3, 1, 4])]:
            for size in [1, 2, 3]:
                actual: list[int] = []
                after = 0
                while True:
                    rows = repo._ordered_page(
                        "sort_fixture", "territory_id", "TRUE", (), "value", direction, after, size
                    )
                    if not rows:
                        break
                    actual.extend(row["territory_id"] for row in rows)
                    after = rows[-1]["territory_id"]
                    assert len(actual) <= len(expected)
                assert actual == expected


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
        "UPDATE geo.change_event SET effective_date='2020-01-01' WHERE release_id=%s",
        "UPDATE geo.change_event SET effective_date='2021-01-02' WHERE release_id=%s",
        "UPDATE geo.change_event SET kind='recode' WHERE release_id=%s AND kind='merger'",
        "UPDATE geo.change_event SET kind='transfer' WHERE release_id=%s AND kind='merger'",
        "UPDATE geo.territory SET level='province' WHERE code='C' AND id IN "
        "(SELECT territory_id FROM geo.release_territory WHERE release_id=%s)",
        "UPDATE geo.boundary b SET geom=ST_Translate(b.geom,2,0) FROM geo.territory t "
        "WHERE b.territory_id=t.id AND t.code='A' AND b.release_id=%s",
        "UPDATE geo.boundary b SET geom=ST_Translate(b.geom,2,0) FROM geo.territory t "
        "WHERE b.territory_id=t.id AND t.code='R1' AND b.release_id=%s",
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
        assert db.execute("SELECT status FROM catalog.pipeline_run").fetchall() == [("failed",)]
    assert list(settings.data_dir.joinpath("quarantine").glob("coverage-*.json"))


@pytest.mark.parametrize(
    "derived,shift,allowed", [(False, 0.005, True), (False, 0.05, False), (True, 0.005, False)]
)
def test_publication_repeats_the_declared_boundary_policy(
    settings: Settings,
    m2_bundle: tuple[Bundle, Path],
    monkeypatch: pytest.MonkeyPatch,
    derived: bool,
    shift: float,
    allowed: bool,
) -> None:
    bundle, contract = m2_bundle
    bundle.derive_parent_boundaries = derived
    original = publication._load_observations
    called = []

    def tamper(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        db, rid = args[:2]
        # Move the leftmost half-region municipality slightly outside its parent.
        db.execute(
            "UPDATE geo.boundary b SET geom=ST_Translate(b.geom,%s,0) "
            "FROM geo.territory t WHERE b.territory_id=t.id AND t.code='A' "
            "AND b.release_id=%s",
            (-shift, rid),
        )
        called.append(True)

    monkeypatch.setattr(publication, "_load_observations", tamper)
    if allowed:
        publish_coverage(settings, bundle, contract)
    else:
        with pytest.raises(psycopg.Error, match="Boundary hierarchy changed before publication"):
            publish_coverage(settings, bundle, contract)
        with psycopg.connect(settings.admin_database_url) as db:
            assert db.execute("SELECT count(*) FROM catalog.release").fetchone() == (0,)
    assert called == [True]


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
