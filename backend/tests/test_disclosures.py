import json
import subprocess
import sys
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import TelegramIdentity
from app.config import Settings
from app.db import get_db
from app.main import app
from app.models import (
    Bet,
    Disclosure,
    DrandProof,
    MarketSnapshot,
    PoolVersion,
    Round,
    User,
    VirtualGift,
)
from app.seeds import seed_demo_catalog
from app.services.accounts import get_or_create_account
from app.services.bets import create_bet
from app.services.disclosure_verification import (
    DisclosureVerificationError,
    verify_disclosure,
    verify_disclosure_json,
)
from app.services.disclosures import (
    DisclosurePackage,
    canonical_disclosure_json,
    disclose_round,
    disclosure_package_hash,
)
from app.services.drand_adapter import DrandAdapter, round_available_at
from app.services.draws import resolve_bet
from app.services.market import import_market_snapshot
from app.services.pools import create_pool_version

ROUND_TIME = round_available_at(1)
NOW = ROUND_TIME - timedelta(seconds=4)
SIGNATURE = (
    "b55e7cb2d5c613ee0b2e28d6750aabbb78c39dcc96bd9d38c2c2e12198df95571d"
    "e8e8e402a0cc48871c7089a2b3af4b"
)
RANDOMNESS = "1466a6cd24e327188770752f6134001c64d6efcc590ccc26b721611ad96f165a"
BEACON = {"round": 1, "signature": SIGNATURE, "randomness": RANDOMNESS}


def settings() -> Settings:
    return Settings(_env_file=None, environment="test")


def adapter() -> DrandAdapter:
    return DrandAdapter(
        relays=("https://test.invalid",),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=BEACON)),
    )


def import_snapshot(session: Session) -> MarketSnapshot:
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
    return import_market_snapshot(
        session,
        "plush-pepe",
        manual,
        external,
        stars_per_gram=Decimal(1),
        settings=settings(),
        now=NOW,
    )


def prepare_round(session: Session) -> tuple[str, str, str]:
    seed_demo_catalog(session, now=NOW)
    round_ = session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    session.commit()
    snapshot = import_snapshot(session)
    pool = create_pool_version(session, round_.id, snapshot.id, settings=settings(), now=NOW)
    user = get_or_create_account(
        session, TelegramIdentity(telegram_user_id=1001, username="player"), 10_000
    )
    return round_.id, pool.id, user.id


def latest_pool(session: Session, round_id: str) -> PoolVersion:
    pool = session.scalar(
        select(PoolVersion)
        .where(PoolVersion.round_id == round_id)
        .order_by(PoolVersion.version.desc())
    )
    assert pool is not None
    session.commit()
    return pool


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    def override_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def sell_out_round(session: Session) -> tuple[Disclosure, list[Bet]]:
    round_id, _, user_id = prepare_round(session)
    completed: list[Bet] = []
    for index in range(4):
        pool = latest_pool(session, round_id)
        bet = create_bet(
            session,
            user_id=user_id,
            collection_id="plush-pepe",
            idempotency_key=f"disclosure-{index}",
            expected_pool_version_id=pool.id,
            settings=settings(),
            now=NOW,
        )
        completed.append(
            resolve_bet(
                session,
                bet.id,
                adapter=adapter(),
                settings=settings(),
                now=ROUND_TIME,
            )
        )
        if index < 3:
            assert session.scalar(select(Disclosure).where(Disclosure.round_id == round_id)) is None
            session.commit()
        if index == 0:
            snapshot = import_snapshot(session)
            create_pool_version(session, round_id, snapshot.id, settings=settings(), now=ROUND_TIME)
    disclosure = session.scalar(select(Disclosure).where(Disclosure.round_id == round_id))
    assert disclosure is not None
    return disclosure, completed


def test_sellout_atomically_publishes_complete_canonical_disclosure(
    db_session: Session,
) -> None:
    disclosure, completed = sell_out_round(db_session)
    round_id = disclosure.round_id
    package = DisclosurePackage.model_validate_json(disclosure.package_json)
    round_ = db_session.get(Round, round_id)

    assert round_ is not None and round_.status == "DISCLOSED"
    assert round_.disclosed_at == ROUND_TIME
    assert canonical_disclosure_json(package) == disclosure.package_json
    assert disclosure.package_hash == disclosure_package_hash(disclosure.package_json)
    assert [pool.version for pool in package.pool_versions] == [1, 2, 3, 4, 5]
    assert [pool.remaining_count for pool in package.pool_versions] == [4, 3, 3, 2, 1]
    assert len(package.market_snapshots) == 2
    assert {snapshot.id for snapshot in package.market_snapshots} == {
        pool.market_snapshot_id for pool in package.pool_versions
    }
    assert {bet.id for bet in package.bets} == {bet.id for bet in completed}
    assert all(bet.state == "COMPLETED" for bet in package.bets)
    assert all(bet.beacon_proof is not None for bet in package.bets)
    assert all([entry.kind for entry in bet.ledger_entries] == ["DEBIT"] for bet in package.bets)
    assert len(package.gifts) == 4
    assert all(gift.lifecycle == "AWARDED" for gift in package.gifts)
    assert {bet.selected_gift_id for bet in package.bets} == {gift.id for gift in package.gifts}
    assert db_session.scalar(select(DrandProof).where(DrandProof.bet_id == completed[-1].id))
    assert completed[0].user_id not in disclosure.package_json

    db_session.commit()
    repeated = disclose_round(db_session, round_id, now=ROUND_TIME + timedelta(hours=1))
    assert repeated.id == disclosure.id
    assert repeated.package_json == disclosure.package_json


def test_deadline_discloses_remaining_gifts_and_cancelled_restored_attempt(
    db_session: Session,
) -> None:
    round_id, pool_id, user_id = prepare_round(db_session)
    bet = create_bet(
        db_session,
        user_id=user_id,
        collection_id="plush-pepe",
        idempotency_key="deadline-cancelled",
        expected_pool_version_id=pool_id,
        settings=settings(),
        now=NOW,
    )
    resolve_bet(
        db_session,
        bet.id,
        adapter=adapter(),
        settings=settings(),
        now=ROUND_TIME + timedelta(seconds=60),
    )
    round_ = db_session.get(Round, round_id)
    assert round_ is not None
    deadline = round_.disclosure_deadline
    db_session.commit()

    with pytest.raises(ValueError, match="before its deadline"):
        disclose_round(db_session, round_id, now=deadline - timedelta(seconds=1))
    disclosure = disclose_round(db_session, round_id, now=deadline)
    package = DisclosurePackage.model_validate_json(disclosure.package_json)

    assert package.round.status == "DISCLOSED"
    assert len(package.pool_versions) == 1
    assert len(package.market_snapshots) == 1
    assert len(package.bets) == 1
    disclosed_bet = package.bets[0]
    assert disclosed_bet.state == "CANCELLED"
    assert disclosed_bet.selected_gift_id is None
    assert disclosed_bet.beacon_proof is None
    assert {entry.kind: entry.amount for entry in disclosed_bet.ledger_entries} == {
        "DEBIT": -144,
        "RESTORATION": 144,
    }
    assert len(package.gifts) == 4
    assert all(gift.lifecycle == "AVAILABLE" for gift in package.gifts)
    assert all(gift.owner_epoch is None for gift in package.gifts)
    assert db_session.get(User, user_id).demo_balance == 10_000  # type: ignore[union-attr]


def test_disclosure_refuses_to_finalize_an_active_attempt(db_session: Session) -> None:
    round_id, pool_id, user_id = prepare_round(db_session)
    create_bet(
        db_session,
        user_id=user_id,
        collection_id="plush-pepe",
        idempotency_key="still-pending",
        expected_pool_version_id=pool_id,
        settings=settings(),
        now=NOW,
    )

    with pytest.raises(ValueError, match="Pending attempts"):
        disclose_round(db_session, round_id, now=NOW + timedelta(days=30))

    assert db_session.scalar(select(Disclosure).where(Disclosure.round_id == round_id)) is None
    assert db_session.get(Round, round_id).status == "OPEN"  # type: ignore[union-attr]
    assert (
        len(list(db_session.scalars(select(VirtualGift).where(VirtualGift.round_id == round_id))))
        == 4
    )


def test_independent_verifier_replays_a_valid_soldout_round(db_session: Session) -> None:
    disclosure, _ = sell_out_round(db_session)

    package = verify_disclosure_json(disclosure.package_json)

    assert package.round.id == disclosure.round_id
    assert len(package.bets) == 4


def test_verifier_rejects_manipulated_statistics(db_session: Session) -> None:
    disclosure, _ = sell_out_round(db_session)
    package = DisclosurePackage.model_validate_json(disclosure.package_json)
    package.pool_versions[0].actual_rtp = Decimal("0.01")

    with pytest.raises(DisclosureVerificationError, match="invalid RTP"):
        verify_disclosure(package)


def test_verifier_rejects_manifest_tampering(db_session: Session) -> None:
    disclosure, _ = sell_out_round(db_session)
    package = DisclosurePackage.model_validate_json(disclosure.package_json)
    package.pool_versions[0].manifest.gifts[0].model = "Manipulated model"

    with pytest.raises(DisclosureVerificationError, match="commitment"):
        verify_disclosure(package)


def test_verifier_rejects_invalid_beacon_proof(db_session: Session) -> None:
    disclosure, _ = sell_out_round(db_session)
    package = DisclosurePackage.model_validate_json(disclosure.package_json)
    proof = package.bets[0].beacon_proof
    assert proof is not None
    proof.signature = "00" * 48

    with pytest.raises(DisclosureVerificationError, match="inconsistent beacon evidence"):
        verify_disclosure(package)


def test_verifier_rejects_duplicate_awards_and_changed_outcomes(db_session: Session) -> None:
    disclosure, _ = sell_out_round(db_session)
    package = DisclosurePackage.model_validate_json(disclosure.package_json)
    package.bets[1].selected_gift_id = package.bets[0].selected_gift_id

    with pytest.raises(DisclosureVerificationError):
        verify_disclosure(package)


def test_verifier_rejects_noncanonical_encoding(db_session: Session) -> None:
    disclosure, _ = sell_out_round(db_session)

    with pytest.raises(DisclosureVerificationError, match="not canonical"):
        verify_disclosure_json(disclosure.package_json + "\n")


def test_disclosure_download_is_public_only_after_generation(
    client: TestClient, db_session: Session
) -> None:
    round_id, _, _ = prepare_round(db_session)
    missing = client.get(f"/api/rounds/{round_id}/disclosure")
    assert missing.status_code == 404

    round_ = db_session.get(Round, round_id)
    assert round_ is not None
    db_session.commit()
    disclosure = disclose_round(db_session, round_id, now=round_.disclosure_deadline)
    response = client.get(f"/api/rounds/{round_id}/disclosure")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-disclosure-sha256"] == disclosure.package_hash
    assert "attachment;" in response.headers["content-disposition"]
    assert response.text == disclosure.package_json
    assert verify_disclosure_json(response.text).round.id == round_id


def test_round_audit_keeps_manifest_hidden_until_disclosure(
    client: TestClient, db_session: Session
) -> None:
    round_id, _, _ = prepare_round(db_session)
    hidden_gift = db_session.scalar(select(VirtualGift).where(VirtualGift.round_id == round_id))
    assert hidden_gift is not None
    db_session.commit()

    active = client.get(f"/api/rounds/{round_id}/audit")
    assert active.status_code == 200
    active_body = active.json()
    assert active_body["round"]["status"] == "OPEN"
    assert active_body["collection"]["pool"]["commitment"]
    assert active_body["disclosure"] is None
    assert hidden_gift.id not in active.text and hidden_gift.model not in active.text

    round_ = db_session.get(Round, round_id)
    assert round_ is not None
    db_session.commit()
    disclosure = disclose_round(db_session, round_id, now=round_.disclosure_deadline)
    completed = client.get(f"/api/rounds/{round_id}/audit")
    assert completed.status_code == 200
    assert completed.json()["round"]["status"] == "DISCLOSED"
    assert completed.json()["disclosure"] == {
        "sha256": disclosure.package_hash,
        "created_at": disclosure.created_at.isoformat(),
        "download_url": f"/api/rounds/{round_id}/disclosure",
    }


def test_documented_cli_verifies_a_generated_disclosure(
    db_session: Session, tmp_path: Path
) -> None:
    disclosure, _ = sell_out_round(db_session)
    package_path = tmp_path / "disclosure.json"
    package_path.write_text(disclosure.package_json, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "app.verify_disclosure", str(package_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == {
        "completed_bets": 4,
        "remaining_gifts": 0,
        "round_id": disclosure.round_id,
        "sha256": disclosure.package_hash,
        "valid": True,
    }
