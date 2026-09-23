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
    def observation_table(
        self,
        release_id: UUID,
        series: str,
        period: date,
        level: str | None,
        after: int,
        limit: int,
        sort_by: str,
        direction: str,
        search: str | None,
        parent_code: str | None,
        status: str | None,
    ) -> list[dict[str, Any]]: ...
    def crosswalk_table(
        self,
        release_id: UUID,
        after: int,
        limit: int,
        sort_by: str,
        direction: str,
        kind: str | None,
        weight_basis: str | None,
    ) -> list[dict[str, Any]]: ...
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
    def _ordered_page(
        self,
        view: str,
        identity: str,
        where: str,
        params: tuple[Any, ...],
        column: str,
        direction: str,
        after: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        # Identifiers/clauses are private constants selected by allowlists below.
        # Values, including the cursor's identity, are always bound parameters.
        order, comparison = ("DESC", "<") if direction == "desc" else ("ASC", ">")
        return self._query(
            f"""WITH selected AS NOT MATERIALIZED (
                SELECT *, {column} AS table_sort_value FROM {view} WHERE {where}
            ), anchor AS (
                SELECT table_sort_value AS sort_value, {identity} AS row_id
                FROM selected WHERE {identity}=%s
            )
            SELECT o.* FROM selected o
            WHERE (%s=0 OR EXISTS (
                SELECT 1 FROM anchor a WHERE
                (o.table_sort_value IS NULL AND a.sort_value IS NOT NULL)
                OR o.table_sort_value {comparison} a.sort_value
                OR (o.table_sort_value IS NOT DISTINCT FROM a.sort_value AND o.{identity}>a.row_id)
            ))
            ORDER BY o.table_sort_value {order} NULLS LAST, o.{identity} ASC LIMIT %s""",
            (*params, after, after, limit),
        )

    def observation_table(
        self,
        release_id: UUID,
        series: str,
        period: date,
        level: str | None,
        after: int,
        limit: int,
        sort_by: str,
        direction: str,
        search: str | None,
        parent_code: str | None,
        status: str | None,
    ) -> list[dict[str, Any]]:
        column = {
            "territory_id": "territory_id",
            "name": "territory_name",
            "code": "territory_code",
            "value": "value",
            "status": "CASE status WHEN 'demo' THEN 'Dimostrativo' "
            "WHEN 'missing' THEN 'Mancante' WHEN 'observed' THEN 'Osservato' "
            "WHEN 'suppressed' THEN 'Riservato' WHEN 'unflagged_upstream' THEN '—' "
            "WHEN 'estimated' THEN 'Stimato' END",
        }[sort_by]
        conditions = ["release_id=%s", "series_code=%s", "period=%s"]
        params: list[Any] = [release_id, series, period]
        for field, value in (("level", level), ("parent_code", parent_code), ("status", status)):
            if value is not None:
                conditions.append(f"{field}=%s")
                params.append(value)
        if search:
            conditions.append(
                "(strpos(lower(territory_name),lower(%s))>0 "
                "OR strpos(lower(territory_code),lower(%s))>0)"
            )
            params.extend([search, search])
        return self._ordered_page(
            "api.observations_v2",
            "territory_id",
            " AND ".join(conditions),
            tuple(params),
            column,
            direction,
            after,
            limit,
        )

    def crosswalk_table(
        self,
        release_id: UUID,
        after: int,
        limit: int,
        sort_by: str,
        direction: str,
        kind: str | None,
        weight_basis: str | None,
    ) -> list[dict[str, Any]]:
        column = {
            "id": "id",
            "date": "effective_date",
            "description": "description",
            "from_code": "from_code",
            "to_code": "to_code",
            "usage": "weight_basis",
        }[sort_by]
        conditions = ["release_id=%s"]
        params: list[Any] = [release_id]
        for field, value in (("kind", kind), ("weight_basis", weight_basis)):
            if value is not None:
                conditions.append(f"{field}=%s")
                params.append(value)
        return self._ordered_page(
            "api.crosswalks_v2",
            "id",
            " AND ".join(conditions),
            tuple(params),
            column,
            direction,
            after,
            limit,
        )

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
