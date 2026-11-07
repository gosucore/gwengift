import json
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Collection, MarketSnapshot, PoolVersion, Round, VirtualGift, utc_now
from app.services.commitments import create_pool_commitment
from app.services.economics import (
    GiftValuation,
    calculate_gift_valuations,
    calculate_pool_economics,
)


def _store_valuations(
    gifts: list[VirtualGift], valuations: list[GiftValuation]
) -> list[GiftValuation]:
    by_gift_id = {valuation.gift_id: valuation for valuation in valuations}
    stored: list[GiftValuation] = []
    for gift in gifts:
        valuation = by_gift_id[gift.id]
        gift.player_sale_estimate = int(
            valuation.player_sale_estimate.to_integral_value(rounding=ROUND_FLOOR)
        )
        gift.replacement_cost = int(
            valuation.replacement_cost.to_integral_value(rounding=ROUND_CEILING)
        )
        stored.append(
            GiftValuation(
                gift_id=gift.id,
                gift_number=gift.number,
                acquisition_cost=valuation.acquisition_cost,
                expected_fees=valuation.expected_fees,
                replacement_cost=Decimal(gift.replacement_cost),
                player_sale_estimate=Decimal(gift.player_sale_estimate),
            )
        )
    return stored


def create_pool_version_in_transaction(
    session: Session,
    round_id: str,
    market_snapshot_id: str,
    *,
    settings: Settings,
    now: datetime,
) -> PoolVersion:
    round_ = session.get(Round, round_id)
    snapshot = session.get(MarketSnapshot, market_snapshot_id)
    if round_ is None or snapshot is None:
        raise ValueError("Round and market snapshot must exist")
    if round_.status in {"CLOSED", "DISCLOSED"}:
        raise ValueError("Cannot add a pool version to a closed round")
    if snapshot.collection_id != round_.collection_id:
        raise ValueError("Market snapshot must belong to the round's collection")

    gifts = list(
        session.scalars(
            select(VirtualGift)
            .where(
                VirtualGift.round_id == round_id,
                VirtualGift.lifecycle == "AVAILABLE",
            )
            .order_by(VirtualGift.id)
        ).all()
    )
    valuations = calculate_gift_valuations(gifts, snapshot, settings)
    stored_valuations = _store_valuations(gifts, valuations)
    economics = calculate_pool_economics(stored_valuations, snapshot, settings, now=now)
    previous_version = session.scalar(
        select(func.max(PoolVersion.version)).where(PoolVersion.round_id == round_id)
    )
    version = (previous_version or 0) + 1
    _, manifest_json, commitment = create_pool_commitment(round_id, version, gifts)
    pool_version = PoolVersion(
        round_id=round_id,
        version=version,
        manifest_json=manifest_json,
        commitment=commitment,
        price=economics.price,
        expected_value=economics.expected_value,
        actual_rtp=economics.actual_rtp,
        operator_margin=economics.operator_margin,
        remaining_count=len(gifts),
        value_distribution_json=json.dumps(
            economics.value_distribution, sort_keys=True, separators=(",", ":")
        ),
        market_snapshot_id=snapshot.id,
    )
    session.add(pool_version)

    collection = session.get(Collection, round_.collection_id)
    if collection is None:
        raise ValueError("Round collection does not exist")
    playable = (
        economics.eligible
        and round_.opens_at <= now < round_.closes_at
        and round_.status in {"DRAFT", "OPEN"}
    )
    collection.status = "OPEN" if playable else "PAUSED"
    if playable and round_.status == "DRAFT":
        round_.status = "OPEN"
    session.flush()
    return pool_version


def create_pool_version(
    session: Session,
    round_id: str,
    market_snapshot_id: str,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> PoolVersion:
    """Insert a new economic snapshot without mutating previous pool versions or bets."""
    config = get_settings() if settings is None else settings
    current_time = utc_now() if now is None else now
    with session.begin():
        return create_pool_version_in_transaction(
            session,
            round_id,
            market_snapshot_id,
            settings=config,
            now=current_time,
        )
