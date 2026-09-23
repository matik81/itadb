import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from fastapi.testclient import TestClient

from itadb.api.app import create_app

RID = UUID("11111111-1111-4111-8111-111111111111")


class MemoryRepository:
    def ping(self) -> None:
        pass

    def sources(self) -> list[dict[str, Any]]:
        return []

    def releases(self, limit: int) -> list[dict[str, Any]]:
        return []

    def release(self, release_id: UUID) -> dict[str, Any] | None:
        return {"id": RID} if release_id == RID else None

    def quality(self, release_id: UUID) -> list[dict[str, Any]]:
        return []

    def observations(
        self, release_id: UUID, series: str, period: date, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return [
            {
                "release_id": RID,
                "series_code": series,
                "unit": "persons",
                "territory_id": i,
                "territory_code": f"DEMO00{i}",
                "territory_name": "Test",
                "scheme": "ITADB_DEMO",
                "period": period,
                "value": "1200",
                "status": "demo",
            }
            for i in range(1, 4)
            if i > after
        ][:limit]


def test_keyset_pagination_and_decimal_contract() -> None:
    with TestClient(create_app(repo=MemoryRepository())) as client:
        params = {"release_id": str(RID), "period": "2025-01-01", "limit": 2}
        first = client.get("/v1/observations", params=params)
        assert first.status_code == 200
        assert first.json()["next_cursor"] == 2
        assert first.json()["items"][0]["value"] == "1200"
        second = client.get("/v1/observations", params={**params, "after": 2}).json()
        assert [row["territory_id"] for row in second["items"]] == [3]
        assert second["next_cursor"] is None


def test_query_guards_and_problem_details() -> None:
    with TestClient(create_app(repo=MemoryRepository())) as client:
        for query in [
            {},
            {"release_id": str(RID), "period": "2025-01-01", "limit": 501},
            {"release_id": str(RID), "period": "2025-01-01", "series": "'; DROP TABLE"},
        ]:
            response = client.get("/v1/observations", params=query)
            assert response.status_code == 422
            assert response.headers["content-type"] == "application/problem+json"
            assert response.json()["request_id"] == response.headers["x-request-id"]
        assert client.get("/v1/releases/22222222-2222-4222-8222-222222222222").status_code == 404


def test_readiness_detects_db_failure_without_leaking_details() -> None:
    class Broken(MemoryRepository):
        def ping(self) -> None:
            raise psycopg.OperationalError("secret postgres URL")

    with TestClient(create_app(repo=Broken())) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert "secret" not in response.text


def test_openapi_export_is_current() -> None:
    assert json.loads(Path("docs/api/openapi.json").read_text()) == create_app().openapi()


def test_table_queries_reject_unknown_fields_directions_and_filters() -> None:
    with TestClient(create_app(repo=MemoryRepository())) as client:
        for endpoint, base, invalid in [
            (
                "/v2/observations",
                {"release_id": str(RID), "series": "population_total", "period": "2025-01-01"},
                [
                    {"sort_by": "value; DROP TABLE"},
                    {"direction": "descending"},
                    {"parent_code": "' OR 1=1"},
                    {"status": "unknown"},
                    {"search": "x" * 101},
                    {"search": ""},
                ],
            ),
            (
                "/v2/crosswalks",
                {"release_id": str(RID)},
                [
                    {"sort_by": "description; DROP TABLE"},
                    {"direction": "ascending"},
                    {"kind": "unknown"},
                    {"weight_basis": "unknown"},
                ],
            ),
        ]:
            for query in invalid:
                response = client.get(endpoint, params={**base, **query})
                assert response.status_code == 422
                assert response.headers["content-type"] == "application/problem+json"
