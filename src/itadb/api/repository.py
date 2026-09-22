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
