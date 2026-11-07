from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import TelegramIdentity
from app.config import Settings
from app.models import Bet, DrawLease, LedgerEntry, MarketSnapshot, Round, User
from app.seeds import seed_demo_catalog
from app.services.accounts import InsufficientDemoBalanceError, get_or_create_account
from app.services.bets import (
    CollectionBusyError,
    CollectionUnavailableError,
    IdempotencyConflictError,
    LateAttemptError,
    StalePoolVersionError,
    create_bet,
)
from app.services.drand_adapter import BeaconTarget
from app.services.market import import_market_snapshot
from app.services.pools import create_pool_version

NOW = datetime(2026, 11, 6, 12, 0, 0)


def settings() -> Settings:
    return Settings(_env_file=None, environment="test")


def prepare_pool(session: Session, *, balance: int = 10_000) -> tuple[str, str]:
    seed_demo_catalog(session, now=NOW)
    round_ = session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    session.commit()
    manual = {
        "schema_version": 1,
        "collection_id": "plush-pepe",
        "observed_at": NOW.isoformat(),
        "liquidity_discount": "0",
        "gifts": [
            {
                "number": number,
                "floor_stars": floor,
                "evidence_url": f"https://evidence.example/{number}",
            }
            for number, floor in enumerate((90, 110, 135, 180), start=1)
        ],
    }
    external = {
        "source": "TG Gifts (tggifts.com)",
        "license": "CC BY 4.0",
        "generated": NOW.isoformat(),
        "collections": {
            "plush-pepe": {
                "name": "Plush Pepe",
                "days": [[NOW.date().isoformat(), 90, 5]],
            }
        },
    }
    snapshot = import_market_snapshot(
        session,
        "plush-pepe",
        manual,
        external,
        stars_per_gram=Decimal(1),
        settings=settings(),
        now=NOW,
    )
    pool = create_pool_version(session, round_.id, snapshot.id, settings=settings(), now=NOW)
    user = get_or_create_account(
        session, TelegramIdentity(telegram_user_id=1001, username="player"), balance
    )
    return user.id, pool.id


def test_creation_binds_quote_and_future_beacon_with_one_atomic_debit(
    db_session: Session,
) -> None:
    user_id, pool_id = prepare_pool(db_session)

    bet = create_bet(
        db_session,
        user_id=user_id,
        collection_id="plush-pepe",
        idempotency_key="attempt-1",
        expected_pool_version_id=pool_id,
        settings=settings(),
        now=NOW,
    )
    duplicate = create_bet(
        db_session,
        user_id=user_id,
        collection_id="plush-pepe",
        idempotency_key="attempt-1",
        expected_pool_version_id="a-newer-quote-is-ignored-on-idempotent-retry",
        settings=settings(),
        now=NOW + timedelta(hours=1),
    )

    assert duplicate.id == bet.id
    assert bet.pool_version_id == pool_id
    assert len(bet.pool_version_hash) == 64
    assert bet.price == 144
    assert bet.remaining_count == 4
    assert bet.acceptance_cutoff > NOW
    assert bet.future_beacon_round >= 1
    assert bet.resolution_deadline > bet.acceptance_cutoff
    user = db_session.get(User, user_id)
    lease = db_session.get(DrawLease, "plush-pepe")
    entries = list(db_session.scalars(select(LedgerEntry).where(LedgerEntry.bet_id == bet.id)))
    assert user is not None and user.demo_balance == 9856
    assert lease is not None and lease.bet_id == bet.id
    assert len(entries) == 1
    assert entries[0].kind == "DEBIT" and entries[0].amount == -144


def test_idempotency_key_cannot_be_rebound_to_another_collection(
    db_session: Session,
) -> None:
    user_id, _ = prepare_pool(db_session)
    create_bet(
        db_session,
        user_id=user_id,
        collection_id="plush-pepe",
        idempotency_key="shared-key",
        settings=settings(),
        now=NOW,
    )

    with pytest.raises(IdempotencyConflictError):
        create_bet(
            db_session,
            user_id=user_id,
            collection_id="heart-of-rose",
            idempotency_key="shared-key",
            settings=settings(),
            now=NOW,
        )

    assert db_session.scalar(select(func.count(Bet.id))) == 1
    assert db_session.get(User, user_id).demo_balance == 9856  # type: ignore[union-attr]


def test_insufficient_balance_rolls_back_bet_debit_and_lease(db_session: Session) -> None:
    user_id, _ = prepare_pool(db_session, balance=100)

    with pytest.raises(InsufficientDemoBalanceError):
        create_bet(
            db_session,
            user_id=user_id,
            collection_id="plush-pepe",
            idempotency_key="too-expensive",
            settings=settings(),
            now=NOW,
        )

    assert db_session.get(User, user_id).demo_balance == 100  # type: ignore[union-attr]
    assert db_session.scalar(select(func.count(Bet.id))) == 0
    assert (
        db_session.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "DEBIT"))
        == 0
    )
    assert db_session.scalar(select(func.count(DrawLease.collection_id))) == 0


def test_busy_collection_rejects_second_attempt_without_another_debit(
    db_session: Session,
) -> None:
    user_id, _ = prepare_pool(db_session)
    create_bet(
        db_session,
        user_id=user_id,
        collection_id="plush-pepe",
        idempotency_key="first",
        settings=settings(),
        now=NOW,
    )

    with pytest.raises(CollectionBusyError):
        create_bet(
            db_session,
            user_id=user_id,
            collection_id="plush-pepe",
            idempotency_key="second",
            settings=settings(),
            now=NOW,
        )

    assert db_session.scalar(select(func.count(Bet.id))) == 1
    assert db_session.get(User, user_id).demo_balance == 9856  # type: ignore[union-attr]


def test_stale_pool_quote_and_stale_valuation_do_not_debit(db_session: Session) -> None:
    user_id, pool_id = prepare_pool(db_session)

    with pytest.raises(StalePoolVersionError):
        create_bet(
            db_session,
            user_id=user_id,
            collection_id="plush-pepe",
            idempotency_key="stale-quote",
            expected_pool_version_id=f"old-{pool_id}",
            settings=settings(),
            now=NOW,
        )

    snapshot = db_session.scalar(
        select(MarketSnapshot).where(MarketSnapshot.collection_id == "plush-pepe")
    )
    assert snapshot is not None
    snapshot.expires_at = NOW
    db_session.commit()
    with pytest.raises(CollectionUnavailableError, match="stale"):
        create_bet(
            db_session,
            user_id=user_id,
            collection_id="plush-pepe",
            idempotency_key="stale-valuation",
            expected_pool_version_id=pool_id,
            settings=settings(),
            now=NOW,
        )

    assert db_session.get(User, user_id).demo_balance == 10_000  # type: ignore[union-attr]
    assert db_session.scalar(select(func.count(Bet.id))) == 0


def test_late_cutoff_leaves_balance_unchanged(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, _ = prepare_pool(db_session)

    def late_target(
        now: datetime, *, minimum_delay_seconds: int, acceptance_margin_seconds: int
    ) -> BeaconTarget:
        return BeaconTarget(
            round_number=10,
            available_at=NOW + timedelta(seconds=10),
            acceptance_cutoff=NOW,
        )

    monkeypatch.setattr("app.services.bets.select_future_round", late_target)

    with pytest.raises(LateAttemptError):
        create_bet(
            db_session,
            user_id=user_id,
            collection_id="plush-pepe",
            idempotency_key="late",
            settings=settings(),
            now=NOW,
        )

    assert db_session.get(User, user_id).demo_balance == 10_000  # type: ignore[union-attr]
    assert db_session.scalar(select(func.count(Bet.id))) == 0


def test_database_rejects_mutation_of_immutable_bet_binding(db_session: Session) -> None:
    user_id, _ = prepare_pool(db_session)
    bet = create_bet(
        db_session,
        user_id=user_id,
        collection_id="plush-pepe",
        idempotency_key="immutable",
        settings=settings(),
        now=NOW,
    )

    with pytest.raises(IntegrityError, match="binding is immutable"):
        with db_session.begin():
            bet.price = 1
            db_session.flush()
    db_session.rollback()

    assert db_session.get(Bet, bet.id).price == 144  # type: ignore[union-attr]


def test_concurrent_duplicate_requests_create_one_bet_and_debit(db_session: Session) -> None:
    user_id, pool_id = prepare_pool(db_session)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    barrier = Barrier(2)

    def attempt() -> str:
        with factory() as session:
            barrier.wait()
            return create_bet(
                session,
                user_id=user_id,
                collection_id="plush-pepe",
                idempotency_key="concurrent-duplicate",
                expected_pool_version_id=pool_id,
                settings=settings(),
                now=NOW,
            ).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(lambda _: attempt(), range(2)))

    assert ids[0] == ids[1]
    assert db_session.scalar(select(func.count(Bet.id))) == 1
    assert (
        db_session.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "DEBIT"))
        == 1
    )
    assert db_session.get(User, user_id).demo_balance == 9856  # type: ignore[union-attr]


def test_concurrent_distinct_requests_preserve_collection_lease_invariant(
    db_session: Session,
) -> None:
    user_id, _ = prepare_pool(db_session)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    barrier = Barrier(2)

    def attempt(number: int) -> str:
        with factory() as session:
            barrier.wait()
            try:
                return create_bet(
                    session,
                    user_id=user_id,
                    collection_id="plush-pepe",
                    idempotency_key=f"concurrent-{number}",
                    settings=settings(),
                    now=NOW,
                ).id
            except CollectionBusyError:
                return "busy"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))

    assert sorted(result == "busy" for result in results) == [False, True]
    assert db_session.scalar(select(func.count(Bet.id))) == 1
    assert db_session.scalar(select(func.count(DrawLease.collection_id))) == 1
    assert (
        db_session.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "DEBIT"))
        == 1
    )
    assert db_session.get(User, user_id).demo_balance == 9856  # type: ignore[union-attr]
