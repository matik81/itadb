"""Real PostgreSQL checks for the synthetic population product, using invented records."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.population.publish import publish_population
from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipMunicipality
from itadb.synthesis.national_models import Municipality, NationalInput
from itadb.synthesis.population_models import PopulationInput
from itadb.synthesis.population_runner import run_population

pytestmark = pytest.mark.integration


@pytest.fixture
def serving(tmp_path: Path) -> tuple[Settings, Path]:
    admin, reader = os.getenv("ITADB_TEST_DATABASE_URL"), os.getenv("ITADB_TEST_READER_URL")
    if not admin or not reader:
        pytest.skip("Explicit test database URLs required")
    male, female, foreign = [0] * 101, [0] * 101, [0] * 101
    male[10], female[10], male[40], female[40], male[100] = 2, 2, 5, 5, 1
    foreign[40] = 1
    hashes = {"fixture": uuid4().hex * 2}
    inputs = PopulationInput(
        national=NationalInput(
            evidence_kind="invented_load_fixture",
            population_reference="2025-01-01",
            household_reference="2024-12-31",
            geography_reference="2025-01-01",
            source_hashes=hashes,
            attribution="Fixture inventata CC0",
            municipalities=[
                Municipality(
                    code="900001",
                    province="900",
                    region="90",
                    male=male,
                    female=female,
                    households=[0, 1, 4, 0, 0, 0],
                )
            ],
        ),
        citizenship=CitizenshipInput(
            evidence_kind="invented_load_fixture",
            population_reference="2025-01-01",
            source_hashes=hashes,
            attribution="Fixture inventata CC0",
            country_labels={"100": "Italia", "201": "Albania"},
            municipalities=[
                CitizenshipMunicipality(
                    code="900001",
                    foreign_male=foreign,
                    foreign_female=foreign,
                    countries={"100": [7, 6], "201": [1, 1]},
                )
            ],
        ),
    )
    directory = run_population(tmp_path, inputs)
    return Settings(
        admin_database_url=admin, database_url=reader, data_dir=tmp_path, _env_file=None
    ), directory


def test_population_publication_queries_and_immutability(serving: tuple[Settings, Path]) -> None:
    settings, directory = serving
    sid = publish_population(settings, directory, allow_fixture=True)
    assert publish_population(settings, directory, allow_fixture=True) == sid
    with TestClient(create_app(settings)) as client:
        base = f"/v3/populations/{sid}"
        snapshot = client.get(base).json()
        assert snapshot["persons"] == 15 and snapshot["is_fixture"]
        assert snapshot["data_kind"] == "synthetic" and snapshot["located_persons"] == 0
        assert client.get(base + "/persons").status_code == 422
        args = {"municipality_code": "900001", "limit": 3, "sort_by": "age", "direction": "desc"}
        seen = []
        while True:
            response = client.get(base + "/persons", params=args)
            assert response.status_code == 200, response.text
            result = response.json()
            seen.extend(result["items"])
            if result["next_cursor"] is None:
                break
            args["after"] = result["next_cursor"]
        assert len({p["person_id"] for p in seen}) == 15
        assert [p["age"] for p in seen] == sorted([p["age"] for p in seen], reverse=True)
        assert seen[0]["age"] == 100 and seen[0]["age_is_lower_bound"]
        member = next(p for p in seen if p["household_id"])
        household = client.get(base + f"/households/{member['household_id']}").json()
        assert len(household["members"]) == household["size"]
        distribution = client.get(
            base + "/distributions", params={"citizenship_code": "201"}
        ).json()
        assert sum(r["persons"] for r in distribution) == 2
        validation = client.get(base + "/validation").json()
        assert len(validation) == 4 and all(r["mismatched_cells"] == 0 for r in validation)
        assert client.get(base + "/map").json()["representation"] == "municipality_aggregates"
        assert (
            client.get(
                base + "/persons", params={"municipality_code": "900001", "sort_by": "sql"}
            ).status_code
            == 422
        )
        assert (
            client.get(
                base + "/persons", params={"municipality_code": "900001", "limit": 501}
            ).status_code
            == 422
        )
        assert (
            client.get(
                base + "/persons",
                params={"municipality_code": "900001", "age_min": 80, "age_max": 10},
            ).status_code
            == 422
        )
        assert client.get("/v3/populations/9223372036854775807").status_code == 404
    with psycopg.connect(settings.admin_database_url, autocommit=True) as db:
        for query in [
            f"DELETE FROM population.person_{sid}",
            f"UPDATE population.household_{sid} SET size=2",
            f"TRUNCATE population.person_{sid}",
            f"UPDATE population.snapshot SET report='{{}}' WHERE id={sid}",
            f"DELETE FROM population.cell_{sid}",
            f"DELETE FROM population.municipality WHERE snapshot_id={sid}",
        ]:
            with pytest.raises(psycopg.errors.RaiseException):
                db.execute(query)
    with (
        psycopg.connect(settings.database_url, autocommit=True) as db,
        pytest.raises(psycopg.Error),
    ):
        db.execute("SELECT * FROM population.person LIMIT 1")


def test_failed_import_rolls_back_and_leaves_evidence(
    serving: tuple[Settings, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, directory = serving
    from itadb.population import publish

    original = publish._copy_parquet

    def corrupt(db, sid, kind, path, scratch):
        original(db, sid, kind, path, scratch)
        if kind == "person":
            db.execute(f"UPDATE population.person_{sid} SET household_id=999999 WHERE person_id=1")

    monkeypatch.setattr(publish, "_copy_parquet", corrupt)
    with pytest.raises(ValueError, match="Household relationships"):
        publish_population(settings, directory, allow_fixture=True)
    with psycopg.connect(settings.admin_database_url) as db:
        assert (
            db.execute(
                "SELECT id FROM population.snapshot WHERE run_id=%s", (directory.name,)
            ).fetchone()
            is None
        )
    assert list((settings.data_dir / "quarantine").glob("population-publication-*.json"))


def test_fixture_rejected_by_application_importer(serving: tuple[Settings, Path]) -> None:
    settings, directory = serving
    with pytest.raises(ValueError, match="official-input"):
        publish_population(settings, directory)
    with psycopg.connect(settings.admin_database_url) as db:
        assert (
            db.execute(
                "SELECT id FROM population.snapshot WHERE run_id=%s", (directory.name,)
            ).fetchone()
            is None
        )


def test_postcommit_report_error_does_not_claim_rollback(
    serving: tuple[Settings, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from itadb.population import publish

    settings, directory = serving
    original = publish.atomic_json

    def fail_report(path, content):
        if path.parent.name == "population-publication":
            raise OSError("Invented report write failure")
        original(path, content)

    monkeypatch.setattr(publish, "atomic_json", fail_report)
    with pytest.raises(OSError, match="Invented"):
        publish_population(settings, directory, allow_fixture=True)
    with psycopg.connect(settings.admin_database_url) as db:
        assert db.execute(
            "SELECT status FROM population.snapshot WHERE run_id=%s", (directory.name,)
        ).fetchone() == ("published",)
    report = json.loads(
        next((settings.data_dir / "quarantine").glob("population-publication-*.json")).read_text()
    )
    assert report["published"] is True
    assert report["snapshot_id"] is not None
