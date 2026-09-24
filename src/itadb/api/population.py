"""Application API for verified synthetic population snapshots."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from itadb.api.population_models import (
    PopulationComparison,
    PopulationDistribution,
    PopulationEvidence,
    PopulationMap,
    PopulationMunicipalityPage,
    PopulationSnapshot,
    PopulationValidation,
    SyntheticHouseholdDetail,
    SyntheticHouseholdPage,
    SyntheticPerson,
    SyntheticPersonPage,
)
from itadb.api.population_repository import PopulationRepository

router = APIRouter(prefix="/v3/populations", tags=["Popolazione sintetica"])
SnapshotID = Annotated[int, Path(ge=1, le=9223372036854775807)]
RecordID = Annotated[int, Path(ge=1, le=70_000_000)]
Municipality = Annotated[str, Query(pattern=r"^[0-9]{6}$")]
OptionalMunicipality = Annotated[str | None, Query(pattern=r"^[0-9]{6}$")]
Region = Annotated[str | None, Query(pattern=r"^[0-9]{2}$")]
Citizenship = Annotated[str | None, Query(pattern=r"^[0-9]{3}$")]
Age = Annotated[int, Query(ge=0, le=100)]
Cursor = Annotated[int, Query(ge=0, le=70_000_000)]
Limit = Annotated[int, Query(ge=1, le=500)]
Direction = Literal["asc", "desc"]
Kind = Literal["sex_age", "foreign_age", "citizenship", "household_size"]


def repository(request: Request) -> PopulationRepository:
    repo: PopulationRepository | None = getattr(request.app.state, "population_repository", None)
    if repo is None:
        raise HTTPException(503, "Population database temporarily unavailable")
    return repo


Repo = Annotated[PopulationRepository, Depends(repository)]


def published(snapshot_id: SnapshotID, db: Repo) -> int:
    if db.snapshot(snapshot_id) is None:
        raise HTTPException(404, "Published population not found")
    return snapshot_id


Published = Annotated[int, Depends(published)]


def page(rows: list[dict[str, Any]], limit: int, identity: str) -> dict[str, Any]:
    return {
        "items": rows[:limit],
        "next_cursor": int(rows[limit - 1][identity]) if len(rows) > limit else None,
    }


@router.get("", response_model=list[PopulationSnapshot])
def snapshots(db: Repo, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> object:
    return db.snapshots(limit)


@router.get("/{snapshot_id}", response_model=PopulationEvidence)
def snapshot(snapshot_id: Published, db: Repo) -> object:
    return db.snapshot(snapshot_id)


@router.get("/{snapshot_id}/municipalities", response_model=PopulationMunicipalityPage)
def municipalities(
    snapshot_id: Published,
    db: Repo,
    region_code: Region = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    after: Annotated[int, Query(ge=0, le=999999)] = 0,
    limit: Limit = 100,
) -> object:
    return page(
        db.municipalities(snapshot_id, region_code, search, after, limit + 1), limit, "code"
    )


@router.get("/{snapshot_id}/map", response_model=PopulationMap)
def population_map(snapshot_id: Published, db: Repo, region_code: Region = None) -> object:
    """Representative municipality locations, never synthetic individual residences."""
    return {
        "regions": db.regions(snapshot_id),
        "municipalities": db.municipalities(snapshot_id, region_code, None, 0, 10000),
        "provinces": db.province_boundaries(snapshot_id, region_code),
        "municipality_boundaries": db.municipality_boundaries(snapshot_id, region_code),
    }


@router.get("/{snapshot_id}/persons", response_model=SyntheticPersonPage)
def persons(
    snapshot_id: Published,
    db: Repo,
    municipality_code: Municipality,
    sex: Literal["M", "F"] | None = None,
    citizenship_code: Citizenship = None,
    age_min: Age = 0,
    age_max: Age = 100,
    sort_by: Literal["person_id", "age", "sex", "citizenship_code", "household_id"] = "person_id",
    direction: Direction = "asc",
    after: Cursor = 0,
    limit: Limit = 100,
) -> object:
    if age_min > age_max:
        raise HTTPException(422, "Minimum age must not exceed maximum age")
    return page(
        db.persons(
            snapshot_id,
            municipality_code,
            sex,
            citizenship_code,
            age_min,
            age_max,
            sort_by,
            direction,
            after,
            limit + 1,
        ),
        limit,
        "person_id",
    )


@router.get("/{snapshot_id}/persons/{person_id}", response_model=SyntheticPerson)
def person(snapshot_id: Published, person_id: RecordID, db: Repo) -> object:
    result = db.person(snapshot_id, person_id)
    if result is None:
        raise HTTPException(404, "Synthetic person not found")
    return result


@router.get("/{snapshot_id}/households", response_model=SyntheticHouseholdPage)
def households(
    snapshot_id: Published,
    db: Repo,
    municipality_code: Municipality,
    size: Annotated[int | None, Query(ge=1, le=6)] = None,
    sort_by: Literal["household_id", "size"] = "household_id",
    direction: Direction = "asc",
    after: Cursor = 0,
    limit: Limit = 100,
) -> object:
    return page(
        db.households(snapshot_id, municipality_code, size, sort_by, direction, after, limit + 1),
        limit,
        "household_id",
    )


@router.get("/{snapshot_id}/households/{household_id}", response_model=SyntheticHouseholdDetail)
def household(snapshot_id: Published, household_id: RecordID, db: Repo) -> object:
    result = db.household(snapshot_id, household_id)
    if result is None:
        raise HTTPException(404, "Synthetic household not found")
    return result


@router.get("/{snapshot_id}/distributions", response_model=list[PopulationDistribution])
def distributions(
    snapshot_id: Published,
    db: Repo,
    municipality_code: OptionalMunicipality = None,
    region_code: Region = None,
    sex: Literal["M", "F"] | None = None,
    citizenship_code: Citizenship = None,
    age_min: Age = 0,
    age_max: Age = 100,
) -> object:
    if age_min > age_max:
        raise HTTPException(422, "Minimum age must not exceed maximum age")
    return db.distributions(
        snapshot_id, municipality_code, region_code, sex, citizenship_code, age_min, age_max
    )


@router.get("/{snapshot_id}/validation", response_model=list[PopulationValidation])
def validation(
    snapshot_id: Published, db: Repo, municipality_code: OptionalMunicipality = None
) -> object:
    return db.validation(snapshot_id, municipality_code)


@router.get("/{snapshot_id}/comparison", response_model=list[PopulationComparison])
def comparison(
    snapshot_id: Published, db: Repo, municipality_code: Municipality, kind: Kind = "sex_age"
) -> object:
    """Observed input constraints and corresponding counts from imported synthetic records."""
    return db.comparison(snapshot_id, municipality_code, kind)
