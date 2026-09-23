import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool, PoolTimeout
from starlette.responses import Response

from itadb import __version__
from itadb.api.models import (
    Artifact,
    BoundaryItem,
    CoverageItem,
    CrosswalkPage,
    ObservationPage,
    ObservationPageV2,
    Problem,
    Quality,
    Release,
    ReleaseV2,
    Source,
    TerritoryPage,
)
from itadb.api.repository import PostgresRepository, PostgresRepositoryV2, Repository, RepositoryV2
from itadb.config import Settings

logger = logging.getLogger("itadb.api")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def repository(request: Request) -> Repository:
    result: Repository = request.app.state.repository
    return result


Repo = Annotated[Repository, Depends(repository)]


def repository_v2(request: Request) -> RepositoryV2:
    result: RepositoryV2 = request.app.state.repository_v2
    return result


RepoV2 = Annotated[RepositoryV2, Depends(repository_v2)]


def create_app(
    settings: Settings | None = None,
    repo: Repository | None = None,
    repo_v2: RepositoryV2 | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if repo is not None:
            application.state.repository = repo
            application.state.repository_v2 = repo_v2 or repo
            yield
            return
        pool = ConnectionPool(
            settings.database_url,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            timeout=5,
            open=False,
            kwargs={"connect_timeout": 5, "application_name": "itadb-api"},
        )
        pool.open(wait=False)
        application.state.repository = PostgresRepository(pool)
        application.state.repository_v2 = PostgresRepositoryV2(pool)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(
        title="Itadb Public API",
        root_path=settings.root_path,
        version=__version__,
        lifespan=lifespan,
        description=(
            "Versioned aggregate evidence. No real-person records. "
            "Only published releases are visible. Demo data are explicitly labelled. "
            "Values are decimal strings; missing and suppressed values are null."
        ),
        license_info={"name": "Apache-2.0", "identifier": "Apache-2.0"},
        responses={422: {"model": Problem}, 503: {"model": Problem}},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["Accept"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        # No URLs, query strings, credentials or input values in access logs.
        logger.info(
            json.dumps(
                {
                    "request_id": request.state.request_id,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - start) * 1000, 1),
                }
            )
        )
        return response

    def problem(request: Request, status: int, title: str, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": title,
                "status": status,
                "detail": detail,
                "request_id": getattr(request.state, "request_id", "unavailable"),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({str(error["loc"][-1]) for error in exc.errors()})
        return problem(request, 422, "Invalid query", "Check: " + ", ".join(fields))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return problem(request, exc.status_code, "Request failed", str(exc.detail))

    async def database_error(request: Request, exc: Exception) -> JSONResponse:
        return problem(request, 503, "Service unavailable", "Database temporarily unavailable")

    app.add_exception_handler(psycopg.Error, database_error)
    app.add_exception_handler(PoolTimeout, database_error)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready", tags=["health"])
    def ready(db: Repo, db_v2: RepoV2) -> dict[str, str]:
        db.ping()
        db_v2.ping()
        return {"status": "ready"}

    @app.get("/v1/sources", response_model=list[Source], tags=["catalog"])
    def sources(db: Repo) -> object:
        """Registered sources; registration does not imply an imported dataset."""
        return db.sources()

    @app.get("/v1/releases", response_model=list[Release], tags=["catalog"])
    def releases(db: Repo, limit: Annotated[int, Query(ge=1, le=100)] = 50) -> object:
        """Most recent immutable published releases, with provenance and limitations."""
        return db.releases(limit)

    @app.get(
        "/v1/releases/{release_id}",
        response_model=Release,
        tags=["catalog"],
        responses={404: {"model": Problem}},
    )
    def release(release_id: UUID, db: Repo) -> object:
        item = db.release(release_id)
        if item is None:
            raise HTTPException(404, "Published release not found")
        return item

    @app.get(
        "/v1/releases/{release_id}/quality",
        response_model=list[Quality],
        tags=["quality"],
        responses={404: {"model": Problem}},
    )
    def quality(release_id: UUID, db: Repo) -> object:
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        return db.quality(release_id)

    @app.get(
        "/v1/observations",
        response_model=ObservationPage,
        tags=["statistics"],
        responses={404: {"model": Problem}},
    )
    def observations(
        db: Repo,
        release_id: UUID,
        period: date,
        series: Annotated[str, Query(pattern=r"^[a-z][a-z0-9_]{0,63}$")] = "population_total",
        after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> object:
        """Bounded keyset pagination. Keep release_id, period and series fixed across pages.

        Pass next_cursor as after. A null next_cursor means the last page.
        Unknown series or periods return an empty page; unknown releases return 404.
        """
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        rows = db.observations(release_id, series, period, after, limit + 1)
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["territory_id"] if len(rows) > limit else None,
        }

    @app.get("/v2/sources", response_model=list[Source], tags=["catalog v2"])
    def sources_v2(db: RepoV2) -> object:
        return db.sources()

    @app.get("/v2/releases", response_model=list[ReleaseV2], tags=["catalog v2"])
    def releases_v2(db: RepoV2, limit: Annotated[int, Query(ge=1, le=100)] = 50) -> object:
        return db.releases(limit)

    @app.get(
        "/v2/releases/{release_id}",
        response_model=ReleaseV2,
        tags=["catalog v2"],
        responses={404: {"model": Problem}},
    )
    def release_v2(release_id: UUID, db: RepoV2) -> object:
        item = db.release(release_id)
        if item is None:
            raise HTTPException(404, "Published release not found")
        return item

    @app.get(
        "/v2/releases/{release_id}/quality",
        response_model=list[Quality],
        tags=["quality v2"],
        responses={404: {"model": Problem}},
    )
    def quality_v2(release_id: UUID, db: RepoV2) -> object:
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        return db.quality(release_id)

    @app.get(
        "/v2/releases/{release_id}/artifacts",
        response_model=list[Artifact],
        tags=["catalog v2"],
        responses={404: {"model": Problem}},
    )
    def artifacts_v2(release_id: UUID, db: RepoV2) -> object:
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        return db.artifacts(release_id)

    @app.get(
        "/v2/observations",
        response_model=ObservationPageV2,
        tags=["statistics v2"],
        responses={404: {"model": Problem}},
    )
    def observations_v2(
        db: RepoV2,
        release_id: UUID,
        period: date,
        series: Annotated[str, Query(pattern=r"^[a-z][a-z0-9_]{0,63}$")],
        level: Literal["country", "region", "province", "municipality"] | None = None,
        after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> object:
        """Keep release, series and period fixed across pages. Country totals overlap regions."""
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        rows = (
            db.observations(release_id, series, period, after, limit + 1)
            if level is None
            else db.observations_at_level(release_id, series, period, level, after, limit + 1)
        )
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["territory_id"] if len(rows) > limit else None,
        }

    @app.get(
        "/v2/releases/{release_id}/coverage",
        response_model=list[CoverageItem],
        tags=["coverage v2"],
    )
    def coverage_v2(release_id: UUID, db: RepoV2) -> object:
        """Explicit available selections; published contracts support at most 500 cells."""
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        return db.coverage(release_id)

    @app.get("/v2/territories", response_model=TerritoryPage, tags=["geography v2"])
    def territories_v2(
        db: RepoV2,
        release_id: UUID,
        snapshot: date,
        level: Literal["country", "region", "province", "municipality"],
        after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> object:
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        rows = db.territories(release_id, snapshot, level, after, limit + 1)
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["territory_id"] if len(rows) > limit else None,
        }

    @app.get("/v2/crosswalks", response_model=CrosswalkPage, tags=["geography v2"])
    def crosswalks_v2(
        db: RepoV2,
        release_id: UUID,
        after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> object:
        if db.release(release_id) is None:
            raise HTTPException(404, "Published release not found")
        rows = db.crosswalks(release_id, after, limit + 1)
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    @app.get(
        "/v2/releases/{release_id}/territories/{territory_id}/boundary",
        response_model=BoundaryItem,
        tags=["geography v2"],
    )
    def boundary_v2(
        release_id: UUID,
        territory_id: Annotated[int, ApiPath(ge=1, le=9223372036854775807)],
        db: RepoV2,
    ) -> object:
        item = db.boundary(release_id, territory_id)
        if item is None:
            raise HTTPException(404, "Boundary unavailable within the 20000 vertex response budget")
        return item

    return app


app = create_app()
