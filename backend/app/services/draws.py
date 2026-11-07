from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import (
    Bet,
    Collection,
    DrandProof,
    DrawLease,
    LedgerEntry,
    PoolVersion,
    Round,
    User,
    VirtualGift,
    utc_now,
)
from app.services.commitments import PoolManifest, verify_pool_commitment
from app.services.disclosures import disclose_round_in_transaction
from app.services.drand_adapter import DrandAdapter, DrandAdapterError
from app.services.pools import create_pool_version_in_transaction
from app.services.selection import select_gift


class DrawResolutionError(RuntimeError):
    pass


def _release_lease(session: Session, bet: Bet) -> None:
    lease = session.get(DrawLease, bet.collection_id)
    if lease is not None and lease.bet_id == bet.id:
        session.delete(lease)


def _cancel_in_transaction(session: Session, bet: Bet, now: datetime, reason: str) -> Bet:
    if bet.state == "CANCELLED":
        return bet
    if bet.state == "COMPLETED":
        raise DrawResolutionError("A completed bet cannot be cancelled")
    user = session.get(User, bet.user_id)
    if user is None or user.active_epoch != bet.user_epoch:
        raise DrawResolutionError("Cannot restore a debit outside its active demo epoch")
    user.demo_balance += bet.price
    session.add(
        LedgerEntry(
            user_id=user.id,
            user_epoch=user.active_epoch,
            bet_id=bet.id,
            kind="RESTORATION",
            amount=bet.price,
            balance_after=user.demo_balance,
            created_at=now,
        )
    )
    bet.state = "CANCELLED"
    bet.cancellation_reason = reason
    bet.resolved_at = now
    bet.updated_at = now
    _release_lease(session, bet)
    session.flush()
    return bet


def resolve_bet(
    session: Session,
    bet_id: str,
    *,
    adapter: DrandAdapter,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> Bet:
    config = get_settings() if settings is None else settings
    current_time = utc_now() if now is None else now
    with session.begin():
        bet = session.get(Bet, bet_id)
        if bet is None:
            raise DrawResolutionError("Bet does not exist")
        if bet.state in {"COMPLETED", "CANCELLED"}:
            return bet
        if current_time >= bet.resolution_deadline:
            return _cancel_in_transaction(
                session, bet, current_time, "verified_randomness_unavailable_by_deadline"
            )
        bet.state = "RESOLVING"
        bet.updated_at = current_time
        session.flush()

    try:
        beacon = adapter.fetch_verified_beacon(bet.future_beacon_round, now=current_time)
    except DrandAdapterError:
        # Persisted RESOLVING state is retryable; never substitute another RNG.
        return bet
    if beacon.round_number != bet.future_beacon_round:
        raise DrawResolutionError("Verified beacon does not match the committed round")

    with session.begin():
        bet = session.get(Bet, bet_id)
        if bet is None:
            raise DrawResolutionError("Bet disappeared during resolution")
        if bet.state in {"COMPLETED", "CANCELLED"}:
            return bet
        pool = session.get(PoolVersion, bet.pool_version_id)
        if pool is None or not verify_pool_commitment(
            bet.round_id, pool.version, pool.manifest_json, bet.pool_version_hash
        ):
            raise DrawResolutionError("Committed pool manifest failed verification")
        manifest = PoolManifest.model_validate_json(pool.manifest_json)
        if (
            pool.remaining_count != bet.remaining_count
            or len(manifest.gifts) != bet.remaining_count
        ):
            raise DrawResolutionError("Bet binding does not match the remaining manifest")
        selection = select_gift(
            drand_randomness_hex=beacon.randomness,
            bet_id=bet.id,
            pool_version_hash=bet.pool_version_hash,
            remaining_manifest=manifest,
        )
        gift = session.get(VirtualGift, selection.gift_id)
        if gift is None or gift.round_id != bet.round_id or gift.lifecycle != "AVAILABLE":
            raise DrawResolutionError("Selected gift is not available in the committed pool")

        session.add(
            DrandProof(
                bet_id=bet.id,
                network=beacon.network.chain_hash,
                beacon_round=beacon.round_number,
                signature=beacon.signature,
                randomness=beacon.randomness,
                verification_result=True,
                response_json=beacon.response_json,
                verified_at=current_time,
                created_at=current_time,
            )
        )
        gift.lifecycle = "AWARDED"
        gift.owner_user_id = bet.user_id
        gift.owner_epoch = bet.user_epoch
        bet.selected_gift_id = gift.id
        bet.state = "COMPLETED"
        bet.resolved_at = current_time
        bet.updated_at = current_time
        session.flush()

        round_ = session.get(Round, bet.round_id)
        collection = session.get(Collection, bet.collection_id)
        if round_ is None or collection is None:
            raise DrawResolutionError("Bet round or collection does not exist")
        remaining_count = len(
            list(
                session.scalars(
                    select(VirtualGift.id).where(
                        VirtualGift.round_id == bet.round_id,
                        VirtualGift.lifecycle == "AVAILABLE",
                    )
                ).all()
            )
        )
        if remaining_count == 0:
            round_.status = "CLOSED"
            collection.status = "PAUSED"
            disclose_round_in_transaction(session, bet.round_id, now=current_time)
        else:
            create_pool_version_in_transaction(
                session,
                bet.round_id,
                pool.market_snapshot_id,
                settings=config,
                now=current_time,
            )
        _release_lease(session, bet)
        session.flush()
        return bet


def recover_pending_bets(
    session: Session,
    *,
    adapter: DrandAdapter,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> list[Bet]:
    """Resume all persisted pending/interrupted bets after a process restart."""
    with session.begin():
        bet_ids = list(
            session.scalars(
                select(Bet.id)
                .where(Bet.state.in_(["PENDING_RANDOMNESS", "RESOLVING"]))
                .order_by(Bet.created_at)
            ).all()
        )
    return [
        resolve_bet(session, bet_id, adapter=adapter, settings=settings, now=now)
        for bet_id in bet_ids
    ]
