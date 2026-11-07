import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Bet, Collection, PoolVersion, Round, User, VirtualGift
from app.seeds import load_seed_catalog, seed_demo_catalog
from app.services.market import import_market_snapshot
from app.services.pools import create_pool_version

NOW = datetime(2026, 11, 6, 12, 0, 0)


def settings() -> Settings:
    return Settings(_env_file=None, environment="test")


def import_snapshot(
    session: Session,
    *,
    observed_at: datetime = NOW,
    floors: tuple[int, int, int, int] = (90, 110, 135, 180),
) -> str:
    manual = {
        "schema_version": 1,
        "collection_id": "plush-pepe",
        "observed_at": observed_at.isoformat(),
        "liquidity_discount": "0",
        "gifts": [
            {
                "number": number,
                "floor_stars": floor,
                "evidence_url": f"https://evidence.example/{number}",
            }
            for number, floor in enumerate(floors, start=1)
        ],
    }
    external = {
        "source": "TG Gifts (tggifts.com)",
        "license": "CC BY 4.0",
        "generated": observed_at.isoformat(),
        "collections": {
            "plush-pepe": {
                "name": "Plush Pepe",
                "days": [[observed_at.date().isoformat(), floors[0], 5]],
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
        now=observed_at,
    )
    return snapshot.id


def seed_round(session: Session) -> str:
    seed_demo_catalog(session, now=NOW)
    seed = load_seed_catalog()
    collection = next(item for item in seed.collections if item.id == "plush-pepe")
    round_id = str(session.query(Round).filter(Round.collection_id == collection.id).one().id)
    session.commit()
    return round_id


def test_gift_and_market_changes_create_versions_without_mutating_old_bet_quote(
    db_session: Session,
) -> None:
    round_id = seed_round(db_session)
    first_snapshot_id = import_snapshot(db_session)

    first = create_pool_version(
        db_session, round_id, first_snapshot_id, settings=settings(), now=NOW
    )

    assert first.version == 1
    assert first.remaining_count == 4
    assert first.price == 144
    assert db_session.get(Round, round_id).status == "OPEN"  # type: ignore[union-attr]
    assert db_session.get(Collection, "plush-pepe").status == "OPEN"  # type: ignore[union-attr]
    first_manifest = json.loads(first.manifest_json)
    assert [gift["id"] for gift in first_manifest["gifts"]] == sorted(
        gift["id"] for gift in first_manifest["gifts"]
    )
    gifts_by_number = {
        gift.number: gift
        for gift in db_session.query(VirtualGift).filter(VirtualGift.round_id == round_id)
    }
    assert gifts_by_number[1].replacement_cost == 95
    assert gifts_by_number[3].replacement_cost == 142

    db_session.commit()
    with db_session.begin():
        user = User(id="user-1", telegram_user_id=1001, active_epoch=1, demo_balance=10_000)
        db_session.add(user)
        db_session.flush()
        db_session.add(
            Bet(
                id="bet-1",
                user_id=user.id,
                user_epoch=user.active_epoch,
                collection_id="plush-pepe",
                round_id=round_id,
                pool_version_id=first.id,
                pool_version_hash=first.commitment,
                idempotency_key="first-attempt",
                future_beacon_round=100,
                acceptance_cutoff=NOW + timedelta(minutes=1),
                resolution_deadline=NOW + timedelta(minutes=5),
                state="PENDING_RANDOMNESS",
                price=first.price,
                remaining_count=first.remaining_count,
            )
        )
        db_session.flush()

    awarded_id = first_manifest["gifts"][0]["id"]
    with db_session.begin():
        bet = db_session.get(Bet, "bet-1")
        gift = db_session.get(VirtualGift, awarded_id)
        assert bet is not None and gift is not None
        bet.state = "COMPLETED"
        bet.selected_gift_id = gift.id
        bet.resolved_at = NOW + timedelta(minutes=1)
        gift.lifecycle = "AWARDED"
        gift.owner_user_id = user.id
        gift.owner_epoch = user.active_epoch

    second = create_pool_version(
        db_session, round_id, first_snapshot_id, settings=settings(), now=NOW
    )

    old_bet = db_session.get(Bet, "bet-1")
    assert old_bet is not None
    assert second.version == 2
    assert second.remaining_count == 3
    assert second.id != first.id
    assert second.commitment != first.commitment
    assert awarded_id not in second.manifest_json
    assert old_bet.pool_version_id == first.id
    assert old_bet.pool_version_hash == first.commitment
    assert old_bet.price == 144
    assert old_bet.remaining_count == 4
    assert first.price == 144
    assert first.remaining_count == 4
    assert awarded_id in first.manifest_json

    later = NOW + timedelta(hours=1)
    db_session.commit()
    second_snapshot_id = import_snapshot(db_session, observed_at=later, floors=(180, 220, 270, 360))
    third = create_pool_version(
        db_session, round_id, second_snapshot_id, settings=settings(), now=later
    )

    assert third.version == 3
    assert third.market_snapshot_id == second_snapshot_id
    assert third.price > second.price
    assert second.market_snapshot_id == first_snapshot_id
    assert old_bet.price == 144
    assert old_bet.pool_version_id == first.id


def test_pool_versions_are_append_only(db_session: Session) -> None:
    round_id = seed_round(db_session)
    snapshot_id = import_snapshot(db_session)
    pool_version = create_pool_version(
        db_session, round_id, snapshot_id, settings=settings(), now=NOW
    )

    with pytest.raises(IntegrityError, match="append-only"):
        with db_session.begin():
            pool_version.price += 1
            db_session.flush()
    db_session.rollback()

    unchanged = db_session.get(PoolVersion, pool_version.id)
    assert unchanged is not None
    assert unchanged.price == 144


def test_ineligible_update_pauses_new_attempts_without_rewriting_current_version(
    db_session: Session,
) -> None:
    round_id = seed_round(db_session)
    first_snapshot_id = import_snapshot(db_session)
    first = create_pool_version(
        db_session, round_id, first_snapshot_id, settings=settings(), now=NOW
    )
    later = NOW + timedelta(hours=1)
    weak_snapshot_id = import_snapshot(db_session, observed_at=later, floors=(1, 1, 1, 1000))

    second = create_pool_version(
        db_session, round_id, weak_snapshot_id, settings=settings(), now=later
    )

    assert second.version == 2
    assert db_session.get(Collection, "plush-pepe").status == "PAUSED"  # type: ignore[union-attr]
    assert first.price == 144
    assert first.manifest_json != second.manifest_json
