"""Bounded queries against published synthetic population tables only."""

from typing import Any

from itadb.api.repository import SQLRepository

PERSON_FIELDS = (
    "person_id,household_id,lpad(municipality_code::text,6,'0') "
    "municipality_code,sex,birth_year,birth_year_upper_bound,age,"
    "age_is_lower_bound,lpad(citizenship_code::text,3,'0') "
    "citizenship_code,reference_adult,data_kind"
)
HOUSEHOLD_FIELDS = (
    "household_id,lpad(municipality_code::text,6,'0') municipality_code,size,data_kind"
)


class PopulationQueries(SQLRepository):
    def ping(self) -> None:
        self._query(
            "SELECT (SELECT id FROM api.population_snapshots LIMIT 0),"
            "(SELECT person_id FROM api.population_persons LIMIT 0),"
            "(SELECT household_id FROM api.population_households LIMIT 0),"
            "(SELECT code FROM api.population_municipalities LIMIT 0),"
            "(SELECT persons FROM api.population_cells LIMIT 0),"
            "(SELECT expected FROM api.population_validation LIMIT 0),"
            "(SELECT code FROM api.population_regions LIMIT 0),"
            "(SELECT code FROM api.population_provinces LIMIT 0)"
        )

    def snapshots(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            (
                "SELECT id,run_id,manifest_sha256,reference_date,household_reference,"
                "persons,households,municipalities,located_persons,is_fixture,"
                "data_kind,published_at FROM api.population_snapshots ORDER BY "
                "published_at DESC,id DESC LIMIT ?"
            ),
            (limit,),
        )

    def snapshot(self, sid: int) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM api.population_snapshots WHERE id=?", (sid,))
        return rows[0] if rows else None

    def municipalities(
        self, sid: int, region: str | None, search: str | None, after: int, limit: int
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def regions(self, sid: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def province_boundaries(self, sid: int, region: str | None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def municipality_boundaries(self, sid: int, region: str | None) -> list[dict[str, Any]]:
        raise NotImplementedError

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
        raise NotImplementedError

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
        conditions = ["snapshot_id=?", "municipality_code=?", "age BETWEEN ? AND ?"]
        params: list[Any] = [sid, int(municipality), age_min, age_max]
        if sex:
            conditions.append("sex=?")
            params.append(sex)
        if citizenship:
            conditions.append("citizenship_code=?")
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
            f"WHERE snapshot_id=? AND person_id=?",
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
        conditions = ["snapshot_id=?", "municipality_code=?"]
        params: list[Any] = [sid, int(municipality)]
        if size:
            conditions.append("size=?")
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
            f"WHERE snapshot_id=? AND household_id=?",
            (sid, hid),
        )
        if not rows:
            return None
        return {
            **rows[0],
            "members": self._query(
                f"SELECT {PERSON_FIELDS} "
                f"FROM api.population_persons "
                f"WHERE snapshot_id=? AND household_id=? "
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
        province: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["snapshot_id=?", "age BETWEEN ? AND ?"]
        params: list[Any] = [sid, age_min, age_max]
        for field, value in [
            ("municipality_code", municipality),
            ("region_code", region),
            ("province_code", province),
            ("sex", sex),
            ("citizenship_code", citizenship),
        ]:
            if value is not None:
                conditions.append(f"{field}=?")
                params.append(value if field == "sex" else int(value))
        return self._query(
            f"SELECT age,sex,sum(persons)::bigint persons "
            f"FROM api.population_cells "
            f"WHERE {' AND '.join(conditions)} GROUP BY age,sex "
            f"ORDER BY age,sex LIMIT 202",
            tuple(params),
        )

    def validation(self, sid: int, municipality: str | None) -> list[dict[str, Any]]:
        where, params = "snapshot_id=?", [sid]
        if municipality:
            where += " AND municipality_code=?"
            params.append(int(municipality))
        return self._query(
            f"""SELECT kind,count(*) cells,sum(expected)::bigint expected,sum(actual)::bigint
            actual,
            count(*) FILTER(WHERE expected<>actual) mismatched_cells,max(abs(expected-actual))
            max_absolute_error
            FROM api.population_validation WHERE {where} GROUP BY kind
            ORDER BY {self.text_order("kind")} LIMIT 4""",
            tuple(params),
        )

    def comparison(self, sid: int, municipality: str, kind: str) -> list[dict[str, Any]]:
        return self._query(
            (
                "SELECT kind,sex,category,expected,actual FROM "
                "api.population_validation WHERE snapshot_id=? AND "
                "municipality_code=? AND kind=? ORDER BY category,sex LIMIT 2000"
            ),
            (sid, int(municipality), kind),
        )
