"""End-to-end DuckDB publication; all input records in this suite are invented."""

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest
from fastapi.testclient import TestClient

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.pipeline import publish_coverage as coverage_publisher
from itadb.pipeline.publish_coverage import publish_coverage
from itadb.pipeline.publish_istat import ingest_istat_population
from itadb.pipeline.runner import ingest_demo
from itadb.pipeline.storage import archive_file, atomic_json, sha256_file
from itadb.population import publish
from itadb.population.cartography import display_geometry, load_spatial
from itadb.population.publish import publish_population
from itadb.serving.archive import DATABASE, activate_archive, install_archive, verify_archive
from itadb.serving.export import export_archive
from itadb.serving.publication import RevisionConflict, publication
from itadb.synthesis.citizenship_models import CitizenshipInput, CitizenshipMunicipality
from itadb.synthesis.national_models import Municipality, NationalInput
from itadb.synthesis.population_models import PopulationInput
from itadb.synthesis.population_runner import run_population

pytestmark = pytest.mark.integration
FIXTURES = Path("tests/fixtures")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, serving_dir=tmp_path / "published", _env_file=None)


@pytest.fixture
def serving(tmp_path: Path) -> tuple[Settings, Path]:
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
        serving_dir=tmp_path / "published",
        data_dir=tmp_path,
        _env_file=None,
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
        provincial = client.get(
            base + "/distributions",
            params={"province_code": "900", "region_code": "90", "citizenship_code": "201"},
        )
        assert provincial.status_code == 200
        assert provincial.json() == distribution
        assert client.get(base + "/distributions", params={"province_code": "901"}).json() == []
        assert (
            client.get(
                base + "/distributions", params={"province_code": "900", "region_code": "91"}
            ).json()
            == []
        )
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


def test_aggregate_publication_retry_revisions_and_concurrency(settings: Settings) -> None:
    args = inputs(settings.data_dir / "inputs")
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: ingest_istat_population(settings, **args), range(2)))
    assert ids[0] == ids[1]
    release = ids[0]
    original = (settings.serving_dir / "current").resolve()
    original_hash = sha256_file(original / DATABASE)
    with TestClient(create_app(settings)) as client:
        assert len(client.get("/v2/releases").json()) == 1
        assert (
            len(
                client.get(
                    "/v2/observations",
                    params={
                        "release_id": str(release),
                        "series": "resident_population_jan1",
                        "period": "2024-01-01",
                    },
                ).json()["items"]
            )
            == 21
        )
        assert client.get(f"/v1/releases/{release}").status_code == 404
    with pytest.raises(RevisionConflict):
        ingest_istat_population(settings, **inputs(settings.data_dir / "revision", 2))
    new = ingest_istat_population(
        settings,
        **inputs(settings.data_dir / "revision", 2),
        supersedes=release,
        revision_reason="Correzione fixture",
    )
    assert new != release and sha256_file(original / DATABASE) == original_hash
    with TestClient(create_app(settings)) as client:
        assert len(client.get("/v2/releases").json()) == 2
        assert client.get(f"/v2/releases/{new}").json()["supersedes_release_id"] == str(release)


def test_population_failure_never_changes_published_archive(serving, monkeypatch):
    settings, directory = serving
    rid = ingest_demo(
        settings, FIXTURES / "population-demo.csv", Path("contracts/population-demo-v1.json")
    )
    original = (settings.serving_dir / "current").resolve()

    def fail(*args, **kwargs):
        raise ValueError("Injected failed distribution gate")

    monkeypatch.setattr(publish, "_validate", fail)
    with pytest.raises(ValueError, match="distribution"):
        publish_population(settings, directory, allow_fixture=True)
    assert (settings.serving_dir / "current").resolve() == original
    assert list((settings.data_dir / "quarantine").glob("*.json"))
    with TestClient(create_app(settings)) as client:
        assert client.get("/v3/populations").json() == []
        assert client.get(f"/v1/releases/{rid}").status_code == 200


def test_fixture_rejected_and_corruption_rejected(serving):
    settings, directory = serving
    with pytest.raises(ValueError, match="official-input"):
        publish_population(settings, directory)
    assert not (settings.serving_dir / "current").exists()
    path = next(directory.glob("batch-*/persons.parquet"))
    with path.open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(ValueError):
        publish_population(settings, directory, allow_fixture=True)
    assert not (settings.serving_dir / "current").exists()


def test_coverage_geometry_api_and_retry(settings, coverage_bundle):
    bundle, contract = coverage_bundle
    rid = publish_coverage(settings, bundle, contract)
    assert publish_coverage(settings, bundle, contract) == rid
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/v2/releases/{rid}/coverage").json()
        for level in ("region", "municipality"):
            page = client.get(
                "/v2/territories",
                params={"release_id": str(rid), "snapshot": "2021-01-01", "level": level},
            ).json()
            assert page["items"]
            for item in page["items"]:
                response = client.get(
                    f"/v2/releases/{rid}/territories/{item['territory_id']}/boundary"
                )
                assert response.status_code == 200, response.text
                assert response.json()["geometry"]["type"] == "MultiPolygon"
        crosswalk = client.get("/v2/crosswalks", params={"release_id": str(rid)}).json()
        assert crosswalk["items"]


@pytest.mark.parametrize("failure", ["quality", "evidence", "after_load", "geometry"])
def test_coverage_failures_do_not_publish(settings, coverage_bundle, monkeypatch, failure):
    bundle, contract = coverage_bundle
    if failure == "quality":
        bundle.observations[0].value = Decimal(-1)
    elif failure == "evidence":
        (settings.data_dir / bundle.evidence[0].path).write_text("corrupt")
    elif failure == "after_load":

        def fail(*args, **kwargs):
            raise ValueError("injected")

        monkeypatch.setattr(coverage_publisher, "_load_observations", fail)
    else:
        bundle.boundary_repair_keys = ["unreviewed"]
    with pytest.raises(ValueError):
        publish_coverage(settings, bundle, contract)
    assert not (settings.serving_dir / "current").exists()
    assert list((settings.data_dir / "quarantine").glob("*.json"))


def test_export_restore_retry_and_readonly(settings, tmp_path):
    rid = ingest_demo(
        settings, FIXTURES / "population-demo.csv", Path("contracts/population-demo-v1.json")
    )
    archive = export_archive(settings, tmp_path / "export", tmp_path / "export-evidence")
    before = (archive / DATABASE).read_bytes()
    assert export_archive(settings, archive, tmp_path / "unused") == archive
    assert (archive / DATABASE).read_bytes() == before
    restored = tmp_path / "restored"
    installed = install_archive(archive, restored)
    assert install_archive(archive, restored) == installed
    activate_archive(restored, installed)
    verify_archive(installed)
    with (
        duckdb.connect(str(installed / DATABASE), read_only=True) as db,
        pytest.raises(duckdb.Error),
    ):
        db.execute("DELETE FROM api.releases")
    with TestClient(create_app(settings.model_copy(update={"serving_dir": restored}))) as client:
        assert client.get(f"/v1/releases/{rid}").status_code == 200


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE api.population_persons SET sex=NULL WHERE person_id=1",
        "UPDATE api.population_persons SET birth_year=birth_year-1 WHERE age=40",
        "UPDATE api.population_persons SET birth_year_upper_bound=1900 WHERE age=100",
        "UPDATE api.population_persons SET reference_adult=NULL WHERE person_id=1",
        "UPDATE api.population_persons SET age_is_lower_bound=false WHERE age=100",
        "UPDATE api.population_persons SET reference_date='2020-01-01' WHERE person_id=1",
        "UPDATE api.population_households SET size=NULL WHERE household_id=1",
        "UPDATE api.population_persons SET household_id=NULL WHERE age=10",
        "UPDATE api.population_persons SET municipality_code=999999 WHERE person_id=1",
        "UPDATE api.population_persons SET reference_adult=true WHERE age=10",
        "INSERT INTO api.population_persons SELECT * FROM api.population_persons LIMIT 1",
    ],
)
def test_loaded_population_integrity_gate(serving, monkeypatch, mutation):
    settings, directory = serving
    validate = publish._validate

    def corrupt_then_validate(db, *args):
        db.execute(mutation)
        return validate(db, *args)

    monkeypatch.setattr(publish, "_validate", corrupt_then_validate)
    with pytest.raises(ValueError):
        publish_population(settings, directory, allow_fixture=True)
    assert not (settings.serving_dir / "current").exists()


def test_display_geometry_preserves_small_territories():
    original = json.dumps(
        {
            "type": "MultiPolygon",
            "coordinates": [[[[10, 40], [10.001, 40], [10.001, 40.001], [10, 40.001], [10, 40]]]],
        }
    )
    triangle = json.dumps(
        {
            "type": "MultiPolygon",
            "coordinates": [[[[10, 40], [10.001, 40], [10.001, 40.001], [10, 40]]]],
        }
    )
    with duckdb.connect() as db:
        load_spatial(db)
        result = display_geometry(db, original, triangle)
        assert json.loads(result) == json.loads(original)


def test_corrupt_current_archive_blocks_new_publication(settings):
    ingest_demo(
        settings, FIXTURES / "population-demo.csv", Path("contracts/population-demo-v1.json")
    )
    current = (settings.serving_dir / "current").resolve()
    path = current / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["database"]["sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    from itadb.serving.archive import ArchiveUnavailable

    with pytest.raises(ArchiveUnavailable), publication(settings):
        pytest.fail("Corrupt archives must be rejected before writing")
    assert (settings.serving_dir / "current").resolve() == current


def test_verification_failure_keeps_previous_release(settings, monkeypatch):
    ingest_demo(
        settings, FIXTURES / "population-demo.csv", Path("contracts/population-demo-v1.json")
    )
    current = (settings.serving_dir / "current").resolve()
    digest = sha256_file(current / DATABASE)

    def fail(*args, **kwargs):
        raise ValueError("Injected sealing failure")

    monkeypatch.setattr("itadb.serving.publication.seal_archive", fail)
    with pytest.raises(ValueError, match="sealing"), publication(settings) as writer:
        writer.db.execute("DELETE FROM api.sources")
        writer.changed = True
    assert (settings.serving_dir / "current").resolve() == current
    assert sha256_file(current / DATABASE) == digest
