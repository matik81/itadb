from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class Source(BaseModel):
    id: str
    name: str
    homepage: str
    license_url: str
    is_demo: bool


class Release(BaseModel):
    id: UUID
    dataset_id: str
    title: str
    limitations: str
    source_id: str
    is_demo: bool
    reference_period: date
    retrieved_at: datetime
    published_at: datetime
    upstream_url: str
    raw_sha256: str
    transform_version: str
    contract_sha256: str
    license_url: str
    row_count: int


class ReleaseV2(Release):
    metadata_sha256: str
    upstream_last_update: datetime | None
    upstream_published_at: datetime | None
    supersedes_release_id: UUID | None
    revision_reason: str | None
    territory_snapshot: date | None
    series_code: str
    attribution: str | None


class ObservationBase(BaseModel):
    release_id: UUID
    series_code: str
    unit: str
    territory_id: int
    territory_code: str
    territory_name: str
    scheme: str
    period: date
    value: Decimal | None


class Observation(ObservationBase):
    status: Literal["observed", "estimated", "missing", "suppressed", "demo"]


class ObservationPage(BaseModel):
    items: list[Observation]
    next_cursor: int | None


class ObservationV2(ObservationBase):
    status: Literal["observed", "estimated", "missing", "suppressed", "demo", "unflagged_upstream"]
    level: Literal["country", "region", "province", "municipality"]
    parent_code: str | None
    upstream_status: str
    upstream_note: str
    upstream_unit: str
    upstream_unit_multiplier: str


class ObservationPageV2(BaseModel):
    items: list[ObservationV2]
    next_cursor: int | None


class Artifact(BaseModel):
    release_id: UUID
    kind: str
    sha256: str
    byte_size: int


class CoverageItem(BaseModel):
    release_id: UUID
    series_code: str
    title: str
    unit: str
    dimensions: dict[str, str]
    period: date
    scheme: str | None
    territory_snapshot: date | None
    row_count: int


class TerritoryItem(BaseModel):
    release_id: UUID
    territory_id: int
    scheme: str
    code: str
    name: str
    level: Literal["country", "region", "province", "municipality"]
    valid_from: date
    valid_to: date | None
    parent_code: str | None
    snapshot: date
    has_boundary: bool


class TerritoryPage(BaseModel):
    items: list[TerritoryItem]
    next_cursor: int | None


class CrosswalkItem(BaseModel):
    id: int
    release_id: UUID
    event_id: str
    kind: Literal["merger", "split", "recode", "transfer"]
    effective_date: date
    source_url: str
    evidence_sha256: str
    description: str
    from_code: str
    from_scheme: str
    to_code: str
    to_scheme: str
    allocation_weight: Decimal | None
    weight_basis: Literal["exact", "structural"]


class CrosswalkPage(BaseModel):
    items: list[CrosswalkItem]
    next_cursor: int | None


class BoundaryItem(BaseModel):
    release_id: UUID
    territory_id: int
    geometry: dict[str, Any]
    simplification_degrees: float


class Quality(BaseModel):
    release_id: UUID
    check_name: str
    passed: bool
    details: dict[str, Any]


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    request_id: str
