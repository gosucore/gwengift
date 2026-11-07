from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import TelegramIdentity
from app.models import (
    Bet,
    Collection,
    Disclosure,
    LedgerEntry,
    MarketSnapshot,
    PoolVersion,
    Round,
    VirtualGift,
)
from app.services.accounts import (
    InsufficientDemoBalanceError,
    debit_demo_balance,
    get_or_create_account,
    list_active_inventory,
    list_attempt_history,
    reset_demo_account,
)

NOW = datetime.now(UTC).replace(tzinfo=None)


def test_account_creation_is_idempotent_and_creates_starting_ledger(
    db_session: Session,
) -> None:
    identity = TelegramIdentity(telegram_user_id=123, username="first")

    user = get_or_create_account(db_session, identity, 10_000)
    same_user = get_or_create_account(
        db_session, TelegramIdentity(telegram_user_id=123, username="renamed"), 10_000
    )

    assert same_user.id == user.id
    assert same_user.username == "renamed"
    assert same_user.demo_balance == 10_000
    entries = list(db_session.scalars(select(LedgerEntry)).all())
    assert len(entries) == 1
    assert entries[0].kind == "RESET"
    assert entries[0].amount == 10_000


def test_debit_and_insufficient_balance_preserve_conservation(db_session: Session) -> None:
    user = get_or_create_account(
        db_session, TelegramIdentity(telegram_user_id=123, username=None), 100
    )

    debit = debit_demo_balance(db_session, user.id, 40)

    assert debit.amount == -40
    assert debit.balance_after == 60
    with pytest.raises(InsufficientDemoBalanceError):
        debit_demo_balance(db_session, user.id, 61)

    persisted_user = db_session.get(type(user), user.id)
    assert persisted_user is not None
    assert persisted_user.demo_balance == 60
    debits = list(db_session.scalars(select(LedgerEntry).where(LedgerEntry.kind == "DEBIT")).all())
    assert len(debits) == 1


def create_completed_history(db_session: Session, user_id: str) -> None:
    def add(entity: object) -> None:
        db_session.add(entity)
        db_session.flush()

    with db_session.begin():
        add(Collection(id="plush", name="Plush", description="Demo", status="OPEN"))
        add(
            Round(
                id="round-1",
                collection_id="plush",
                status="DISCLOSED",
                opens_at=NOW - timedelta(days=1),
                closes_at=NOW,
                disclosure_deadline=NOW,
                disclosed_at=NOW,
            )
        )
        add(
            MarketSnapshot(
                id="market-1",
                collection_id="plush",
                primary_source="manual-test",
                external_source="tg-gifts-test",
                source_currency="STARS",
                conversion_rule="1:1",
                liquidity_discount=Decimal("0.1"),
                source_payload_json="{}",
                provenance_json="{}",
                observed_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )
        )
        add(
            PoolVersion(
                id="pool-1",
                round_id="round-1",
                version=1,
                manifest_json="[]",
                commitment="a" * 64,
                price=50,
                expected_value=Decimal("45"),
                actual_rtp=Decimal("0.9"),
                operator_margin=Decimal("5"),
                remaining_count=0,
                value_distribution_json="{}",
                market_snapshot_id="market-1",
            )
        )
        add(
            VirtualGift(
                id="gift-1",
                collection_id="plush",
                round_id="round-1",
                model="Model",
                backdrop="Backdrop",
                symbol="Symbol",
                rarity="Rare",
                number=1,
                player_sale_estimate=60,
                replacement_cost=55,
                lifecycle="AWARDED",
                owner_user_id=user_id,
                owner_epoch=1,
            )
        )
        add(
            Bet(
                id="bet-1",
                user_id=user_id,
                user_epoch=1,
                collection_id="plush",
                round_id="round-1",
                pool_version_id="pool-1",
                pool_version_hash="a" * 64,
                idempotency_key="attempt-1",
                future_beacon_round=100,
                acceptance_cutoff=NOW,
                resolution_deadline=NOW + timedelta(minutes=1),
                state="COMPLETED",
                price=50,
                remaining_count=1,
                selected_gift_id="gift-1",
                resolved_at=NOW,
            )
        )
        add(
            Disclosure(
                id="disclosure-1",
                round_id="round-1",
                package_json="{}",
                package_hash="b" * 64,
            )
        )


def test_reset_hides_active_history_and_preserves_global_audit(db_session: Session) -> None:
    user = get_or_create_account(
        db_session, TelegramIdentity(telegram_user_id=123, username=None), 100
    )
    create_completed_history(db_session, user.id)
    debit_demo_balance(db_session, user.id, 50, bet_id="bet-1")

    assert len(list_active_inventory(db_session, user.id)) == 1
    assert len(list_attempt_history(db_session, user.id)) == 1

    reset_demo_account(db_session, user.id, 100)

    assert list_active_inventory(db_session, user.id) == []
    assert list_attempt_history(db_session, user.id) == []
    assert user.active_epoch == 2
    assert user.demo_balance == 100
    assert db_session.get(Bet, "bet-1") is not None
    assert db_session.get(Disclosure, "disclosure-1") is not None
    persisted_gift = db_session.get(VirtualGift, "gift-1")
    assert persisted_gift is not None
    assert persisted_gift.owner_epoch == 1
    assert db_session.scalar(select(func.count()).select_from(Bet)) == 1
