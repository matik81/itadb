"""Bounded queries against published synthetic population views only."""

from typing import Any

from itadb.api.repository import PostgresRepository

PERSON_FIELDS = (
    "person_id,household_id,lpad(municipality_code::text,6,'0') "
    "municipality_code,sex,birth_year,birth_year_upper_bound,age,"
    "age_is_lower_bound,lpad(citizenship_code::text,3,'0') "
    "citizenship_code,reference_adult,data_kind"
)
HOUSEHOLD_FIELDS = (
    "household_id,lpad(municipality_code::text,6,'0') municipality_code,size,data_kind"
)
MUNICIPALITY_FIELDS = (
    "lpad(code::text,6,'0') code,name,lpad(province_code::text,3,'0') "
    "province_code,province_name,lpad(region_code::text,2,'0') "
    "region_code,region_name,persons,households,ST_X(center) longitude,"
    "ST_Y(center) latitude"
)


class PopulationRepository(PostgresRepository):
    def ping(self) -> None:
        self._query(
            "SELECT (SELECT id FROM api.population_snapshots LIMIT 0),"
            "(SELECT person_id FROM api.population_persons LIMIT 0),"
            "(SELECT household_id FROM api.population_households LIMIT 0),"
            "(SELECT code FROM api.population_municipalities LIMIT 0),"
            "(SELECT persons FROM api.population_cells LIMIT 0),"
            "(SELECT expected FROM api.population_validation LIMIT 0),"
            "(SELECT code FROM api.population_regions LIMIT 0)"
        )

    def snapshots(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            (
                "SELECT id,run_id,manifest_sha256,reference_date,household_reference,"
                "persons,households,municipalities,located_persons,is_fixture,"
                "data_kind,published_at FROM api.population_snapshots ORDER BY "
                "published_at DESC,id DESC LIMIT %s"
            ),
            (limit,),
        )

    def snapshot(self, sid: int) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM api.population_snapshots WHERE id=%s", (sid,))
        return rows[0] if rows else None

    def municipalities(
        self, sid: int, region: str | None, search: str | None, after: int, limit: int
    ) -> list[dict[str, Any]]:
        conditions = ["snapshot_id=%s", "code>%s"]
        params: list[Any] = [sid, after]
        if region:
            conditions.append("region_code=%s")
            params.append(int(region))
        if search:
            conditions.append(
                "(strpos(lower(name),lower(%s))>0 OR strpos(lpad(code::text,6,'0'),%s)>0)"
            )
            params += [search, search]
        return self._query(
            f"SELECT {MUNICIPALITY_FIELDS} "
            f"FROM api.population_municipalities "
            f"WHERE {' AND '.join(conditions)} "
            f"ORDER BY code LIMIT %s",
            (*params, limit),
        )

    def regions(self, sid: int) -> list[dict[str, Any]]:
        return self._query(
            """SELECT lpad(r.code::text,2,'0') code,r.name,
            t.persons,t.households,ST_AsGeoJSON(r.boundary,5)::json geometry
            FROM api.population_regions r JOIN (SELECT region_code,sum(persons)::bigint persons,
            sum(households)::bigint households FROM api.population_municipalities
            WHERE snapshot_id=%s GROUP BY region_code) t ON t.region_code=r.code
            WHERE r.snapshot_id=%s ORDER BY r.code""",
            (sid, sid),
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
        # All identifiers and ordering expressions are selected internally.
        order, comparison = ("DESC", "<") if direction == "desc" else ("ASC", ">")
        return self._query(
            f"""WITH selected AS NOT MATERIALIZED (
            SELECT *,{column} sort_value FROM {view} WHERE {" AND ".join(conditions)}),
            anchor AS (SELECT sort_value,{identity} FROM selected WHERE {identity}=%s)
            SELECT {fields} FROM selected p WHERE (%s=0 OR EXISTS(SELECT 1 FROM anchor a
                WHERE p.sort_value {comparison} a.sort_value OR
                (p.sort_value=a.sort_value AND p.{identity}>a.{identity})))
            ORDER BY sort_value {order},{identity} ASC LIMIT %s""",
            (*params, after, after, limit),
        )

    def persons(
        self,
        sid: int,
        municipality: str,
        sex: str | None,
        citizenship: str | None,
        age_min: int,
        age_max: int,
        sort_by: str,
        direction: str,
        after: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        conditions = ["snapshot_id=%s", "municipality_code=%s", "age BETWEEN %s AND %s"]
        params: list[Any] = [sid, int(municipality), age_min, age_max]
        if sex:
            conditions.append("sex=%s")
            params.append(sex)
        if citizenship:
            conditions.append("citizenship_code=%s")
            params.append(int(citizenship))
        column = {
            "person_id": "person_id",
            "age": "age",
            "sex": "sex",
            "citizenship_code": "citizenship_code",
            "household_id": "coalesce(household_id,0)",
        }[sort_by]
        return self._page(
            "api.population_persons",
            PERSON_FIELDS,
            "person_id",
            conditions,
            params,
            column,
            direction,
            after,
            limit,
        )

    def person(self, sid: int, pid: int) -> dict[str, Any] | None:
        rows = self._query(
            f"SELECT {PERSON_FIELDS} "
            f"FROM api.population_persons "
            f"WHERE snapshot_id=%s AND person_id=%s",
            (sid, pid),
        )
        return rows[0] if rows else None

    def households(
        self,
        sid: int,
        municipality: str,
        size: int | None,
        sort_by: str,
        direction: str,
        after: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        conditions = ["snapshot_id=%s", "municipality_code=%s"]
        params: list[Any] = [sid, int(municipality)]
        if size:
            conditions.append("size=%s")
            params.append(size)
        return self._page(
            "api.population_households",
            HOUSEHOLD_FIELDS,
            "household_id",
            conditions,
            params,
            {"household_id": "household_id", "size": "size"}[sort_by],
            direction,
            after,
            limit,
        )

    def household(self, sid: int, hid: int) -> dict[str, Any] | None:
        rows = self._query(
            f"SELECT {HOUSEHOLD_FIELDS} "
            f"FROM api.population_households "
            f"WHERE snapshot_id=%s AND household_id=%s",
            (sid, hid),
        )
        if not rows:
            return None
        return {
            **rows[0],
            "members": self._query(
                f"SELECT {PERSON_FIELDS} "
                f"FROM api.population_persons "
                f"WHERE snapshot_id=%s AND household_id=%s "
                f"ORDER BY person_id LIMIT 6",
                (sid, hid),
            ),
        }

    def distributions(
        self,
        sid: int,
        municipality: str | None,
        region: str | None,
        sex: str | None,
        citizenship: str | None,
        age_min: int,
        age_max: int,
    ) -> list[dict[str, Any]]:
        conditions = ["snapshot_id=%s", "age BETWEEN %s AND %s"]
        params: list[Any] = [sid, age_min, age_max]
        for field, value in [
            ("municipality_code", municipality),
            ("region_code", region),
            ("sex", sex),
            ("citizenship_code", citizenship),
        ]:
            if value is not None:
                conditions.append(f"{field}=%s")
                params.append(value if field == "sex" else int(value))
        return self._query(
            f"SELECT age,sex,sum(persons)::bigint persons "
            f"FROM api.population_cells "
            f"WHERE {' AND '.join(conditions)} GROUP BY age,sex "
            f"ORDER BY age,sex LIMIT 202",
            tuple(params),
        )

    def validation(self, sid: int, municipality: str | None) -> list[dict[str, Any]]:
        where, params = "snapshot_id=%s", [sid]
        if municipality:
            where += " AND municipality_code=%s"
            params.append(int(municipality))
        return self._query(
            f"""SELECT kind,count(*) cells,sum(expected)::bigint expected,sum(actual)::bigint
            actual,
            count(*) FILTER(WHERE expected<>actual) mismatched_cells,max(abs(expected-actual))
            max_absolute_error
            FROM api.population_validation WHERE {where} GROUP BY kind ORDER BY kind LIMIT 4""",
            tuple(params),
        )

    def comparison(self, sid: int, municipality: str, kind: str) -> list[dict[str, Any]]:
        return self._query(
            (
                "SELECT kind,sex,category,expected,actual FROM "
                "api.population_validation WHERE snapshot_id=%s AND "
                "municipality_code=%s AND kind=%s ORDER BY category,sex LIMIT 2000"
            ),
            (sid, int(municipality), kind),
        )
