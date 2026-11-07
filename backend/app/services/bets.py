from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import (
    Bet,
    Collection,
    DrawLease,
    MarketSnapshot,
    PoolVersion,
    Round,
    User,
    new_uuid,
    utc_now,
)
from app.services.accounts import apply_demo_debit
from app.services.drand_adapter import select_future_round
from app.telemetry import operation_span, set_operation_attribute


class BetCreationError(ValueError):
    pass


class IdempotencyConflictError(BetCreationError):
    pass


class CollectionUnavailableError(BetCreationError):
    pass


class StalePoolVersionError(BetCreationError):
    pass


class CollectionBusyError(BetCreationError):
    pass


class LateAttemptError(BetCreationError):
    pass


def create_bet(
    session: Session,
    *,
    user_id: str,
    collection_id: str,
    idempotency_key: str,
    expected_pool_version_id: str | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> Bet:
    with operation_span("bet.create") as span:
        bet = _create_bet(
            session,
            user_id=user_id,
            collection_id=collection_id,
            idempotency_key=idempotency_key,
            expected_pool_version_id=expected_pool_version_id,
            settings=settings,
            now=now,
        )
        if span is not None:
            set_operation_attribute(span, "gwengift.collection_id", bet.collection_id)
            set_operation_attribute(span, "gwengift.bet_id", bet.id)
            set_operation_attribute(span, "gwengift.round_id", bet.round_id)
            set_operation_attribute(span, "gwengift.drand_round", bet.future_beacon_round)
            set_operation_attribute(span, "gwengift.outcome", bet.state)
        return bet


def _create_bet(
    session: Session,
    *,
    user_id: str,
    collection_id: str,
    idempotency_key: str,
    expected_pool_version_id: str | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> Bet:
    if not 1 <= len(idempotency_key) <= 128:
        raise BetCreationError("Idempotency key must contain 1 to 128 characters")
    config = get_settings() if settings is None else settings
    current_time = utc_now() if now is None else now

    with session.begin():
        user = session.get(User, user_id)
        if user is None:
            raise BetCreationError("Demo account does not exist")
        existing = session.scalar(
            select(Bet).where(Bet.user_id == user_id, Bet.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.collection_id != collection_id:
                raise IdempotencyConflictError(
                    "Idempotency key was already used for another collection"
                )
            return existing

        collection = session.get(Collection, collection_id)
        round_ = session.scalar(
            select(Round)
            .where(Round.collection_id == collection_id)
            .order_by(Round.created_at.desc(), Round.id.desc())
            .limit(1)
        )
        if (
            collection is None
            or collection.status != "OPEN"
            or round_ is None
            or round_.status != "OPEN"
            or not round_.opens_at <= current_time < round_.closes_at
        ):
            raise CollectionUnavailableError("Collection is not accepting demo attempts")
        pool = session.scalar(
            select(PoolVersion)
            .where(PoolVersion.round_id == round_.id)
            .order_by(PoolVersion.version.desc())
            .limit(1)
        )
        if pool is None or pool.remaining_count < 1:
            raise CollectionUnavailableError("Collection has no available pool")
        if expected_pool_version_id is not None and pool.id != expected_pool_version_id:
            raise StalePoolVersionError("Pool quote changed; review the updated statistics")
        snapshot = session.get(MarketSnapshot, pool.market_snapshot_id)
        if snapshot is None or current_time >= snapshot.expires_at:
            raise CollectionUnavailableError("Pool valuation is stale")
        if session.get(DrawLease, collection_id) is not None:
            raise CollectionBusyError("Another draw is pending for this collection")

        target = select_future_round(
            current_time,
            minimum_delay_seconds=config.drand_minimum_delay_seconds,
            acceptance_margin_seconds=config.drand_acceptance_margin_seconds,
        )
        if current_time >= target.acceptance_cutoff:
            raise LateAttemptError("Beacon acceptance cutoff has passed")
        resolution_deadline = target.available_at + timedelta(
            seconds=config.drand_resolution_grace_seconds
        )
        bet = Bet(
            id=new_uuid(),
            user_id=user.id,
            user_epoch=user.active_epoch,
            collection_id=collection_id,
            round_id=round_.id,
            pool_version_id=pool.id,
            pool_version_hash=pool.commitment,
            idempotency_key=idempotency_key,
            future_beacon_round=target.round_number,
            acceptance_cutoff=target.acceptance_cutoff,
            resolution_deadline=resolution_deadline,
            state="PENDING_RANDOMNESS",
            price=pool.price,
            remaining_count=pool.remaining_count,
            created_at=current_time,
            updated_at=current_time,
        )
        session.add(bet)
        session.flush()
        apply_demo_debit(session, user, pool.price, bet_id=bet.id)
        session.add(
            DrawLease(
                collection_id=collection_id,
                bet_id=bet.id,
                acquired_at=current_time,
                expires_at=resolution_deadline + timedelta(seconds=config.draw_lease_grace_seconds),
            )
        )
        session.flush()
        return bet
