"""Province filters preserve the bounded synthetic-population distribution contract."""

from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from itadb.api.population import repository, router
from itadb.api.population_repository import PopulationRepository


def test_distribution_province_filter_validation_and_forwarding() -> None:
    repo = Mock(spec=PopulationRepository)
    repo.snapshot.return_value = {"id": 1}
    repo.distributions.return_value = [{"age": 40, "sex": "F", "persons": 5}]
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[repository] = lambda: repo
    with TestClient(app) as client:
        response = client.get(
            "/v3/populations/1/distributions",
            params={
                "province_code": "090",
                "region_code": "09",
                "sex": "F",
                "citizenship_code": "201",
                "age_min": 20,
                "age_max": 80,
            },
        )
        assert response.status_code == 200
        assert response.json() == [{"age": 40, "sex": "F", "persons": 5}]
        repo.distributions.assert_called_once_with(
            1, None, "09", "F", "201", 20, 80, province="090"
        )
        for province in ["9", "9000", "abc", "090 OR 1=1"]:
            assert (
                client.get(
                    "/v3/populations/1/distributions", params={"province_code": province}
                ).status_code
                == 422
            )
        repo.distributions.assert_called_once()


def test_distribution_province_query_is_parameterized_and_snapshot_scoped() -> None:
    repo = object.__new__(PopulationRepository)
    repo._query = Mock(return_value=[])
    repo.distributions(7, None, "09", "F", "201", 20, 80, province="090")
    sql, params = repo._query.call_args.args
    assert "FROM api.population_cells" in sql
    assert "snapshot_id=%s" in sql
    assert "province_code=%s" in sql
    assert "LIMIT 202" in sql
    assert params == (7, 20, 80, 9, 90, "F", 201)
