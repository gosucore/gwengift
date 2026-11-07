from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.catalog import CollectionSummary, PublicRound, _collection_summary
from app.api.dependencies import AppSettings, DbSession
from app.models import Collection, Disclosure, Round, utc_now

router = APIRouter(prefix="/api/rounds", tags=["disclosures"])


class DisclosureSummary(BaseModel):
    sha256: str
    created_at: datetime
    download_url: str


class RoundAuditResponse(BaseModel):
    round: PublicRound
    collection: CollectionSummary
    disclosure: DisclosureSummary | None
    asset_mode: Literal["simulated"] = "simulated"


@router.get(
    "/{round_id}/audit",
    response_model=RoundAuditResponse,
    summary="Inspect current or disclosed round evidence",
    description="Exposes only public aggregates before disclosure and download metadata afterward.",
)
def read_round_audit(round_id: str, db: DbSession, settings: AppSettings) -> RoundAuditResponse:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(status_code=404, detail="Round not found")
    collection = db.get(Collection, round_.collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Round collection not found")
    disclosure = db.scalar(select(Disclosure).where(Disclosure.round_id == round_id))
    return RoundAuditResponse(
        round=PublicRound(
            id=round_.id,
            status=round_.status,
            opens_at=round_.opens_at,
            closes_at=round_.closes_at,
            disclosure_deadline=round_.disclosure_deadline,
        ),
        collection=_collection_summary(db, collection, settings, utc_now()),
        disclosure=DisclosureSummary(
            sha256=disclosure.package_hash,
            created_at=disclosure.created_at,
            download_url=f"/api/rounds/{round_id}/disclosure",
        )
        if disclosure
        else None,
    )
