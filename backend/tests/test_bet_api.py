from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_db
from app.main import app
from app.models import Bet, LedgerEntry, Round, User
from app.seeds import seed_demo_catalog
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
    return Settings(_env_file=None, environment="test", dev_identity_enabled=True)


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    def override_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def dev_header(user_id: int = 1001) -> dict[str, str]:
    return {"X-Dev-Telegram-User-Id": str(user_id), "X-Dev-Username": "player"}


def prepare_pool(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("app.services.bets.utc_now", lambda: NOW)
    seed_demo_catalog(db_session, now=NOW)
    round_ = db_session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    db_session.commit()
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
        db_session,
        "plush-pepe",
        manual,
        external,
        stars_per_gram=Decimal(1),
        settings=settings(),
        now=NOW,
    )
    pool = create_pool_version(db_session, round_.id, snapshot.id, settings=settings(), now=NOW)
    return pool.id


def request_body(pool_id: str, key: str = "api-attempt") -> dict[str, str]:
    return {
        "collection_id": "plush-pepe",
        "pool_version_id": pool_id,
        "idempotency_key": key,
    }


def verified_adapter() -> DrandAdapter:
    return DrandAdapter(
        relays=("https://test.invalid",),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=BEACON)),
    )


def test_pending_polling_and_idempotent_retry_do_not_change_outcome_or_balance(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_id = prepare_pool(db_session, monkeypatch)

    created = client.post("/api/bets", json=request_body(pool_id), headers=dev_header())
    first_poll = client.get(f"/api/bets/{created.json()['id']}", headers=dev_header())
    second_poll = client.get(f"/api/bets/{created.json()['id']}", headers=dev_header())
    retry = client.post("/api/bets", json=request_body(pool_id), headers=dev_header())

    assert created.status_code == 201
    assert created.json()["state"] == "PENDING_RANDOMNESS"
    assert created.json()["gift"] is None and created.json()["beacon"] is None
    assert first_poll.json() == second_poll.json() == created.json()
    assert retry.status_code == 201 and retry.json() == created.json()
    assert db_session.scalar(select(func.count(Bet.id))) == 1
    user = db_session.scalar(select(User).where(User.telegram_user_id == 1001))
    assert user is not None and user.demo_balance == 9856
    assert (
        db_session.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "DEBIT"))
        == 1
    )


def test_completed_lifecycle_returns_gift_and_proof_and_retry_is_safe(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_id = prepare_pool(db_session, monkeypatch)
    created = client.post("/api/bets", json=request_body(pool_id), headers=dev_header()).json()
    db_session.commit()
    resolve_bet(
        db_session,
        created["id"],
        adapter=verified_adapter(),
        settings=settings(),
        now=ROUND_TIME,
    )

    response = client.get(f"/api/bets/{created['id']}", headers=dev_header())
    retry = client.post("/api/bets", json=request_body(pool_id), headers=dev_header())
    other_user = client.get(f"/api/bets/{created['id']}", headers=dev_header(2002))

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "COMPLETED"
    assert body["gift"]["id"]
    assert body["gift"]["ticket_price"] == 144
    assert body["gift"]["value_minus_ticket"] == body["gift"]["player_sale_estimate"] - 144
    assert body["beacon"]["round"] == 1
    assert body["beacon"]["randomness"] == RANDOMNESS
    assert retry.json()["state"] == "COMPLETED"
    assert retry.json()["gift"] == body["gift"]
    assert other_user.status_code == 404
    assert db_session.scalar(select(func.count(Bet.id))) == 1
    assert (
        db_session.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "DEBIT"))
        == 1
    )


def test_cancelled_lifecycle_is_pollable_and_retryable_without_new_debit(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_id = prepare_pool(db_session, monkeypatch)
    created = client.post("/api/bets", json=request_body(pool_id), headers=dev_header()).json()
    db_session.commit()
    resolve_bet(
        db_session,
        created["id"],
        adapter=verified_adapter(),
        settings=settings(),
        now=ROUND_TIME + timedelta(seconds=60),
    )

    response = client.get(f"/api/bets/{created['id']}", headers=dev_header())
    retry = client.post("/api/bets", json=request_body(pool_id), headers=dev_header())

    assert response.status_code == 200
    assert response.json()["state"] == "CANCELLED"
    assert response.json()["gift"] is None and response.json()["beacon"] is None
    assert response.json()["cancellation_reason"] == "verified_randomness_unavailable_by_deadline"
    assert retry.json() == response.json()
    user = db_session.scalar(select(User).where(User.telegram_user_id == 1001))
    assert user is not None and user.demo_balance == 10_000
    assert (
        db_session.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "DEBIT"))
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "RESTORATION")
        )
        == 1
    )
