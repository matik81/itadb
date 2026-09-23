from datetime import date
from typing import Any, Protocol
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Repository(Protocol):
    def ping(self) -> None: ...
    def sources(self) -> list[dict[str, Any]]: ...
    def releases(self, limit: int) -> list[dict[str, Any]]: ...
    def release(self, release_id: UUID) -> dict[str, Any] | None: ...
    def quality(self, release_id: UUID) -> list[dict[str, Any]]: ...
    def observations(
        self, release_id: UUID, series: str, period: date, after: int, limit: int
    ) -> list[dict[str, Any]]: ...


class RepositoryV2(Repository, Protocol):
    def artifacts(self, release_id: UUID) -> list[dict[str, Any]]: ...
    def coverage(self, release_id: UUID) -> list[dict[str, Any]]: ...
    def territories(
        self, release_id: UUID, snapshot: date, level: str, after: int, limit: int
    ) -> list[dict[str, Any]]: ...
    def crosswalks(self, release_id: UUID, after: int, limit: int) -> list[dict[str, Any]]: ...
    def boundary(self, release_id: UUID, territory_id: int) -> dict[str, Any] | None: ...
    def observations_at_level(
        self, release_id: UUID, series: str, period: date, level: str, after: int, limit: int
    ) -> list[dict[str, Any]]: ...


class PostgresRepository:
    def __init__(self, pool: ConnectionPool[Any]):
        self.pool = pool

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    def ping(self) -> None:
        self._query("SELECT 1 FROM api.sources LIMIT 1")

    def sources(self) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM api.sources ORDER BY id")

    def releases(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.releases ORDER BY published_at DESC, id LIMIT %s", (limit,)
        )

    def release(self, release_id: UUID) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM api.releases WHERE id=%s", (release_id,))
        return rows[0] if rows else None

    def quality(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.quality WHERE release_id=%s ORDER BY check_name", (release_id,)
        )

    def observations(
        self, release_id: UUID, series: str, period: date, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.observations WHERE release_id=%s AND series_code=%s "
            "AND period=%s AND territory_id>%s ORDER BY territory_id LIMIT %s",
            (release_id, series, period, after, limit),
        )


class PostgresRepositoryV2(PostgresRepository):
    def ping(self) -> None:
        self._query("SELECT metadata_sha256,series_code FROM api.releases_v2 LIMIT 0")

    def releases(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.releases_v2 ORDER BY published_at DESC,id LIMIT %s", (limit,)
        )

    def release(self, release_id: UUID) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM api.releases_v2 WHERE id=%s", (release_id,))
        return rows[0] if rows else None

    def quality(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.quality_v2 WHERE release_id=%s ORDER BY check_name", (release_id,)
        )

    def artifacts(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.artifacts_v2 WHERE release_id=%s ORDER BY kind", (release_id,)
        )

    def observations(
        self, release_id: UUID, series: str, period: date, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.observations_v2 WHERE release_id=%s AND series_code=%s "
            "AND period=%s AND territory_id>%s ORDER BY territory_id LIMIT %s",
            (release_id, series, period, after, limit),
        )

    def coverage(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.coverage_v2 WHERE release_id=%s "
            "ORDER BY period,series_code LIMIT 500",
            (release_id,),
        )

    def territories(
        self, release_id: UUID, snapshot: date, level: str, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.territories_v2 WHERE release_id=%s AND snapshot=%s "
            "AND level=%s AND territory_id>%s ORDER BY territory_id LIMIT %s",
            (release_id, snapshot, level, after, limit),
        )

    def crosswalks(self, release_id: UUID, after: int, limit: int) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.crosswalks_v2 WHERE release_id=%s AND id>%s ORDER BY id LIMIT %s",
            (release_id, after, limit),
        )

    def boundary(self, release_id: UUID, territory_id: int) -> dict[str, Any] | None:
        rows = self._query(
            """SELECT release_id,territory_id,ST_AsGeoJSON(geom,5)::json AS geometry,
            0.001 AS simplification_degrees FROM (
            SELECT release_id,territory_id,ST_Multi(ST_SimplifyPreserveTopology(geom,0.001)) AS geom
            FROM api.boundaries_v2 WHERE release_id=%s AND territory_id=%s) b
            WHERE ST_NPoints(geom)<=20000""",
            (release_id, territory_id),
        )
        return rows[0] if rows else None

    def observations_at_level(
        self, release_id: UUID, series: str, period: date, level: str, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.observations_v2 WHERE release_id=%s AND series_code=%s "
            "AND period=%s AND level=%s AND territory_id>%s ORDER BY territory_id LIMIT %s",
            (release_id, series, period, level, after, limit),
        )
