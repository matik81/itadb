"""DuckDB implementations of the unchanged v1/v2/v3 read contracts."""

from typing import Any
from uuid import UUID

from itadb.api.population_repository import PopulationQueries
from itadb.api.repository import SQLRepository, SQLRepositoryV2
from itadb.serving.schema import SCHEMA
from itadb.serving.store import ArchiveStore


class DuckDBExecutor:
    def text_order(self, expression: str) -> str:
        return f"(SELECT ordinal FROM api.text_order WHERE value=({expression}))"

    def __init__(self, store: ArchiveStore):
        self.store = store

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return self.store.query(sql, params)


class DuckDBRepository(DuckDBExecutor, SQLRepository):
    pass


class DuckDBRepositoryV2(DuckDBExecutor, SQLRepositoryV2):
    def ping(self) -> None:
        for table in SCHEMA:
            self._query(f"SELECT * FROM api.{table} LIMIT 0")

    def boundary(self, release_id: UUID, territory_id: int) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT * FROM api.boundaries_v2 WHERE release_id=%s AND territory_id=%s",
            (release_id, territory_id),
        )
        return rows[0] if rows else None

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
        return ordered_page(
            self,
            view,
            "*",
            identity,
            where,
            params,
            column,
            direction,
            after,
            limit,
            nulls_last=True,
        )


def ordered_page(
    repo: SQLRepository,
    view: str,
    fields: str,
    identity: str,
    where: str,
    params: tuple[Any, ...],
    column: str,
    direction: str,
    after: int,
    limit: int,
    *,
    nulls_last: bool = False,
) -> list[dict[str, Any]]:
    # Resolve the anchor once; correlated EXISTS in the original PostgreSQL plan is
    # expensive for DuckDB. Both queries see the same immutable archive.
    order, comparison = ("DESC", "<") if direction == "desc" else ("ASC", ">")
    if after:
        anchors = repo._query(
            f"SELECT {column} AS anchor FROM {view} WHERE {where} AND {identity}=%s",
            (*params, after),
        )
        if not anchors:
            return []
        anchor = anchors[0]["anchor"]
        if anchor is None:
            where += f" AND ({column} IS NULL AND {identity}>%s)"
            params = (*params, after)
        else:
            where += f" AND ({column} {comparison} %s OR ({column}=%s AND {identity}>%s)"
            if nulls_last:
                where += f" OR {column} IS NULL"
            where += ")"
            params = (*params, anchor, anchor, after)
    return repo._query(
        f"SELECT {fields} FROM {view} WHERE {where} "
        f"ORDER BY {column} {order} NULLS LAST,{identity} ASC LIMIT %s",
        (*params, limit),
    )


class DuckDBPopulationRepository(DuckDBExecutor, PopulationQueries):
    def municipalities(
        self,
        sid: int,
        region: str | None,
        search: str | None,
        after: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        where = "snapshot_id=%s AND code>%s"
        params: list[Any] = [sid, after]
        if region:
            where += " AND region_code=%s"
            params.append(int(region))
        if search:
            where += " AND (strpos(lower(name),lower(%s))>0 OR strpos(lpad(code::text,6,'0'),%s)>0)"
            params.extend([search, search])
        return self._query(
            "SELECT lpad(code::text,6,'0') code,name,lpad(province_code::text,3,'0') province_code,"
            "province_name,lpad(region_code::text,2,'0') region_code,region_name,"
            "persons,households,"
            "longitude,latitude FROM api.population_municipalities "
            f"WHERE {where} ORDER BY code LIMIT %s",
            (*params, limit),
        )

    def regions(self, sid: int) -> list[dict[str, Any]]:
        return self._query(
            "SELECT lpad(r.code::text,2,'0') code,r.name,t.persons,t.households,r.geometry "
            "FROM api.population_regions r JOIN (SELECT region_code,sum(persons)::bigint persons,"
            "sum(households)::bigint households FROM api.population_municipalities "
            "WHERE snapshot_id=%s "
            "GROUP BY region_code) t ON t.region_code=r.code WHERE r.snapshot_id=%s "
            "ORDER BY r.code",
            (sid, sid),
        )

    def province_boundaries(self, sid: int, region: str | None) -> list[dict[str, Any]]:
        return self._query(
            "SELECT lpad(code::text,3,'0') code,geometry FROM api.population_provinces "
            "WHERE snapshot_id=%s AND (%s::smallint IS NULL "
            "OR region_code=%s) "
            "ORDER BY code LIMIT 1000",
            (sid, int(region) if region else None, int(region) if region else None),
        )

    def municipality_boundaries(self, sid: int, region: str | None) -> list[dict[str, Any]]:
        return self._query(
            "SELECT lpad(code::text,6,'0') code,geometry FROM api.population_municipalities "
            "WHERE snapshot_id=%s AND geometry IS NOT NULL AND (%s::smallint IS NULL "
            "OR region_code=%s) "
            "ORDER BY code LIMIT 10000",
            (sid, int(region) if region else None, int(region) if region else None),
        )

    def _page(
        self,
        view: str,
        fields: str,
        identity: str,
        conditions: list[str],
        params: list[Any],
        column: str,
        direction: str,
        after: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        return ordered_page(
            self,
            view,
            fields,
            identity,
            " AND ".join(conditions),
            tuple(params),
            column,
            direction,
            after,
            limit,
        )
