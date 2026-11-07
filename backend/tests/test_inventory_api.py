from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_db
from app.main import app
from app.models import Bet, Round, VirtualGift
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


def create_and_resolve(client: TestClient, db_session: Session, pool_id: str) -> dict[str, object]:
    created = client.post(
        "/api/bets",
        json={
            "collection_id": "plush-pepe",
            "pool_version_id": pool_id,
            "idempotency_key": "inventory-attempt",
        },
        headers=dev_header(),
    )
    assert created.status_code == 201
    bet_id = created.json()["id"]
    pending = client.get("/api/account/attempts", headers=dev_header()).json()
    assert pending["asset_mode"] == "simulated"
    assert [attempt["id"] for attempt in pending["attempts"]] == [bet_id]
    assert pending["attempts"][0]["state"] == "PENDING_RANDOMNESS"
    db_session.commit()
    adapter = DrandAdapter(
        relays=("https://test.invalid",),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=BEACON)),
    )
    resolve_bet(db_session, bet_id, adapter=adapter, settings=settings(), now=ROUND_TIME)
    body: dict[str, object] = created.json()
    return body


def test_inventory_and_history_include_award_attributes_and_ticket_comparison(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_id = prepare_pool(db_session, monkeypatch)
    created = create_and_resolve(client, db_session, pool_id)
    selected_id = client.get(f"/api/bets/{created['id']}", headers=dev_header()).json()["gift"][
        "id"
    ]
    awarded = db_session.get(VirtualGift, selected_id)
    assert awarded is not None
    db_session.commit()

    inventory_response = client.get("/api/account/inventory", headers=dev_header())
    history_response = client.get("/api/account/attempts", headers=dev_header())

    assert inventory_response.status_code == 200
    inventory = inventory_response.json()
    assert inventory["asset_mode"] == "simulated"
    assert len(inventory["gifts"]) == 1
    item = inventory["gifts"][0]
    assert item["id"] == selected_id and item["bet_id"] == created["id"]
    assert item["collection_id"] == "plush-pepe"
    assert item["model"] == awarded.model
    assert item["backdrop"] == awarded.backdrop
    assert item["symbol"] == awarded.symbol
    assert item["rarity"] == awarded.rarity
    assert item["number"] == awarded.number
    assert item["player_sale_estimate"] == awarded.player_sale_estimate
    assert item["ticket_price"] == 144
    assert item["value_minus_ticket"] == awarded.player_sale_estimate - 144
    assert item["awarded_at"]
    history = history_response.json()
    assert [attempt["id"] for attempt in history["attempts"]] == [created["id"]]
    assert history["attempts"][0]["state"] == "COMPLETED"
    assert history["attempts"][0]["gift"]["id"] == selected_id
    assert history["attempts"][0]["beacon"]["round"] == 1


def test_inventory_and_history_are_isolated_and_filtered_by_active_epoch(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_id = prepare_pool(db_session, monkeypatch)
    created = create_and_resolve(client, db_session, pool_id)

    other_inventory = client.get("/api/account/inventory", headers=dev_header(2002)).json()
    other_history = client.get("/api/account/attempts", headers=dev_header(2002)).json()
    assert other_inventory == {"gifts": [], "asset_mode": "simulated"}
    assert other_history == {"attempts": [], "asset_mode": "simulated"}

    reset = client.post("/api/account/reset", headers=dev_header())
    inventory = client.get("/api/account/inventory", headers=dev_header()).json()
    history = client.get("/api/account/attempts", headers=dev_header()).json()

    assert reset.status_code == 200 and reset.json()["active_epoch"] == 2
    assert inventory == {"gifts": [], "asset_mode": "simulated"}
    assert history == {"attempts": [], "asset_mode": "simulated"}
    bet = db_session.get(Bet, created["id"])
    assert bet is not None and bet.user_epoch == 1 and bet.state == "COMPLETED"
    assert bet.selected_gift_id is not None
    old_gift = db_session.get(VirtualGift, bet.selected_gift_id)
    assert old_gift is not None and old_gift.owner_epoch == 1
