from datetime import date
from typing import Any, Protocol
from uuid import UUID


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


class SQLRepository:
    def text_order(self, expression: str) -> str:
        return expression

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        raise NotImplementedError

    def ping(self) -> None:
        self._query("SELECT 1 FROM api.sources LIMIT 1")

    def sources(self) -> list[dict[str, Any]]:
        return self._query(f"SELECT * FROM api.sources ORDER BY {self.text_order('id')}")

    def releases(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.releases ORDER BY published_at DESC, id LIMIT ?", (limit,)
        )

    def release(self, release_id: UUID) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM api.releases WHERE id=?", (release_id,))
        return rows[0] if rows else None

    def quality(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT * FROM api.quality WHERE release_id=? "
            f"ORDER BY {self.text_order('check_name')}",
            (release_id,),
        )

    def observations(
        self, release_id: UUID, series: str, period: date, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.observations WHERE release_id=? AND series_code=? "
            "AND period=? AND territory_id>? ORDER BY territory_id LIMIT ?",
            (release_id, series, period, after, limit),
        )


class SQLRepositoryV2(SQLRepository):
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
        raise NotImplementedError

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
            "name": self.text_order("territory_name"),
            "code": self.text_order("territory_code"),
            "value": "value",
            "status": self.text_order(
                "CASE status WHEN 'demo' THEN 'Dimostrativo' "
                "WHEN 'missing' THEN 'Mancante' WHEN 'observed' THEN 'Osservato' "
                "WHEN 'suppressed' THEN 'Riservato' WHEN 'unflagged_upstream' THEN '—' "
                "WHEN 'estimated' THEN 'Stimato' END"
            ),
        }[sort_by]
        conditions = ["release_id=?", "series_code=?", "period=?"]
        params: list[Any] = [release_id, series, period]
        for field, value in (("level", level), ("parent_code", parent_code), ("status", status)):
            if value is not None:
                conditions.append(f"{field}=?")
                params.append(value)
        if search:
            conditions.append(
                "(strpos(lower(territory_name),lower(?))>0 "
                "OR strpos(lower(territory_code),lower(?))>0)"
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
            "description": self.text_order("description"),
            "from_code": self.text_order("from_code"),
            "to_code": self.text_order("to_code"),
            "usage": self.text_order("weight_basis"),
        }[sort_by]
        conditions = ["release_id=?"]
        params: list[Any] = [release_id]
        for field, value in (("kind", kind), ("weight_basis", weight_basis)):
            if value is not None:
                conditions.append(f"{field}=?")
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
        # Resolve every public table without scanning data.
        raise NotImplementedError

    def releases(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.releases_v2 ORDER BY published_at DESC,id LIMIT ?", (limit,)
        )

    def release(self, release_id: UUID) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM api.releases_v2 WHERE id=?", (release_id,))
        return rows[0] if rows else None

    def quality(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT * FROM api.quality_v2 WHERE release_id=? "
            f"ORDER BY {self.text_order('check_name')}",
            (release_id,),
        )

    def artifacts(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            f"SELECT * FROM api.artifacts_v2 WHERE release_id=? ORDER BY {self.text_order('kind')}",
            (release_id,),
        )

    def observations(
        self, release_id: UUID, series: str, period: date, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.observations_v2 WHERE release_id=? AND series_code=? "
            "AND period=? AND territory_id>? ORDER BY territory_id LIMIT ?",
            (release_id, series, period, after, limit),
        )

    def coverage(self, release_id: UUID) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.coverage_v2 WHERE release_id=? "
            f"ORDER BY period,{self.text_order('series_code')} LIMIT 500",
            (release_id,),
        )

    def territories(
        self, release_id: UUID, snapshot: date, level: str, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.territories_v2 WHERE release_id=? AND snapshot=? "
            "AND level=? AND territory_id>? ORDER BY territory_id LIMIT ?",
            (release_id, snapshot, level, after, limit),
        )

    def crosswalks(self, release_id: UUID, after: int, limit: int) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.crosswalks_v2 WHERE release_id=? AND id>? ORDER BY id LIMIT ?",
            (release_id, after, limit),
        )

    def boundary(self, release_id: UUID, territory_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def observations_at_level(
        self, release_id: UUID, series: str, period: date, level: str, after: int, limit: int
    ) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM api.observations_v2 WHERE release_id=? AND series_code=? "
            "AND period=? AND level=? AND territory_id>? ORDER BY territory_id LIMIT ?",
            (release_id, series, period, level, after, limit),
        )
