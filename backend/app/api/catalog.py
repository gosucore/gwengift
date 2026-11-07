import json
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import AppSettings, DbSession
from app.config import Settings
from app.models import Collection, MarketSnapshot, PoolVersion, Round, utc_now

router = APIRouter(prefix="/api/collections", tags=["collections"])


class ValueDistribution(BaseModel):
    minimum: str
    median: str
    maximum: str
    below_ticket_count: int
    at_or_above_ticket_count: int


class PublicValuation(BaseModel):
    primary_source: str
    external_source: str
    external_attribution: str
    external_license: Literal["CC BY 4.0"] = "CC BY 4.0"
    source_currency: str
    conversion_rule: dict[str, str]
    liquidity_discount: Decimal
    observed_at: datetime
    expires_at: datetime
    stale: bool
    cross_check_discrepancy: Decimal | None
    discrepancy_threshold: Decimal | None
    discrepancy_action: str | None


class PublicPoolVersion(BaseModel):
    id: str
    version: int
    commitment: str
    price: int
    expected_value: Decimal
    actual_rtp: Decimal
    rounding_premium_stars: Decimal
    operator_margin: Decimal
    remaining_count: int
    value_distribution: ValueDistribution
    commitment_algorithm: Literal["SHA-256/gift-pool-v1"] = "SHA-256/gift-pool-v1"
    draw_algorithm: Literal["gift-draw-v1"] = "gift-draw-v1"


class PublicRound(BaseModel):
    id: str
    status: str
    opens_at: datetime
    closes_at: datetime
    disclosure_deadline: datetime


class CollectionSummary(BaseModel):
    id: str
    name: str
    description: str
    status: str
    asset_mode: Literal["simulated"] = "simulated"
    available: bool
    pool: PublicPoolVersion | None
    valuation: PublicValuation | None


class CollectionDetail(CollectionSummary):
    round: PublicRound | None


class CatalogResponse(BaseModel):
    asset_mode: Literal["simulated"] = "simulated"
    collections: list[CollectionSummary]


def _latest_round(db: Session, collection_id: str) -> Round | None:
    return db.scalar(
        select(Round)
        .where(Round.collection_id == collection_id)
        .order_by(Round.created_at.desc(), Round.id.desc())
        .limit(1)
    )


def _latest_pool(db: Session, round_id: str) -> PoolVersion | None:
    return db.scalar(
        select(PoolVersion)
        .where(PoolVersion.round_id == round_id)
        .order_by(PoolVersion.version.desc())
        .limit(1)
    )


def _public_valuation(snapshot: MarketSnapshot, now: datetime) -> PublicValuation:
    provenance = json.loads(snapshot.provenance_json)
    conversion_rule = json.loads(snapshot.conversion_rule)
    return PublicValuation(
        primary_source=snapshot.primary_source,
        external_source=snapshot.external_source,
        external_attribution=snapshot.external_source,
        source_currency=snapshot.source_currency,
        conversion_rule=conversion_rule,
        liquidity_discount=snapshot.liquidity_discount,
        observed_at=snapshot.observed_at,
        expires_at=snapshot.expires_at,
        stale=now >= snapshot.expires_at,
        cross_check_discrepancy=snapshot.cross_check_discrepancy,
        discrepancy_threshold=provenance.get("discrepancy_threshold"),
        discrepancy_action=provenance.get("discrepancy_action"),
    )


def _public_pool(pool: PoolVersion, settings: Settings) -> PublicPoolVersion:
    exact_price = pool.expected_value / settings.target_rtp
    return PublicPoolVersion(
        id=pool.id,
        version=pool.version,
        commitment=pool.commitment,
        price=pool.price,
        expected_value=pool.expected_value,
        actual_rtp=pool.actual_rtp,
        rounding_premium_stars=Decimal(pool.price) - exact_price,
        operator_margin=pool.operator_margin,
        remaining_count=pool.remaining_count,
        value_distribution=ValueDistribution.model_validate(
            json.loads(pool.value_distribution_json)
        ),
    )


def _collection_summary(
    db: Session, collection: Collection, settings: Settings, now: datetime
) -> CollectionSummary:
    round_ = _latest_round(db, collection.id)
    pool = _latest_pool(db, round_.id) if round_ is not None else None
    snapshot = db.get(MarketSnapshot, pool.market_snapshot_id) if pool is not None else None
    valuation = _public_valuation(snapshot, now) if snapshot is not None else None
    available = (
        collection.status == "OPEN"
        and round_ is not None
        and round_.status == "OPEN"
        and pool is not None
        and pool.remaining_count > 0
        and valuation is not None
        and not valuation.stale
    )
    return CollectionSummary(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        status=collection.status,
        available=available,
        pool=_public_pool(pool, settings) if pool is not None else None,
        valuation=valuation,
    )


@router.get(
    "",
    response_model=CatalogResponse,
    summary="List all demo collections",
    description=(
        "Returns aggregate pool statistics and public provenance, never hidden gift manifests."
    ),
)
def list_collections(db: DbSession, settings: AppSettings) -> CatalogResponse:
    now = utc_now()
    collections = db.scalars(select(Collection).order_by(Collection.id)).all()
    return CatalogResponse(
        collections=[_collection_summary(db, item, settings, now) for item in collections]
    )


@router.get(
    "/{collection_id}",
    response_model=CollectionDetail,
    summary="Get public collection economics and provenance",
    description=(
        "Excludes gift identities, attributes, evidence links, and valuation internals "
        "until disclosure."
    ),
)
def get_collection(collection_id: str, db: DbSession, settings: AppSettings) -> CollectionDetail:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    summary = _collection_summary(db, collection, settings, utc_now())
    round_ = _latest_round(db, collection.id)
    public_round = (
        PublicRound(
            id=round_.id,
            status=round_.status,
            opens_at=round_.opens_at,
            closes_at=round_.closes_at,
            disclosure_deadline=round_.disclosure_deadline,
        )
        if round_ is not None
        else None
    )
    return CollectionDetail(**summary.model_dump(), round=public_round)
