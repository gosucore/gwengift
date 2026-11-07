import logging
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_db
from app.main import app
from app.models import MarketSnapshot, Round, VirtualGift, utc_now
from app.seeds import seed_demo_catalog
from app.services.market import import_market_snapshot
from app.services.pools import create_pool_version

SECRET_MODEL = "HIDDEN-MODEL-7f38cb62"
SECRET_EVIDENCE = "https://evidence.example/private-gift-7f38cb62"


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, environment="test")
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    def override_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def prepare_catalog(db_session: Session) -> tuple[str, str]:
    now = utc_now()
    seed_demo_catalog(db_session, now=now)
    round_ = db_session.scalar(select(Round).where(Round.collection_id == "plush-pepe"))
    assert round_ is not None
    gift = db_session.scalar(select(VirtualGift).where(VirtualGift.round_id == round_.id))
    assert gift is not None
    gift_id = gift.id
    gift.model = SECRET_MODEL
    db_session.commit()

    manual = {
        "schema_version": 1,
        "collection_id": "plush-pepe",
        "observed_at": now.isoformat(),
        "liquidity_discount": "0",
        "gifts": [
            {
                "number": number,
                "floor_stars": floor,
                "evidence_url": SECRET_EVIDENCE
                if number == 1
                else f"https://evidence.example/{number}",
            }
            for number, floor in enumerate((90, 110, 135, 180), start=1)
        ],
    }
    external = {
        "source": "TG Gifts (tggifts.com)",
        "license": "CC BY 4.0",
        "generated": now.isoformat(),
        "collections": {
            "plush-pepe": {
                "name": "Plush Pepe",
                "days": [[now.date().isoformat(), 90, 5]],
            }
        },
    }
    settings = Settings(_env_file=None, environment="test")
    snapshot = import_market_snapshot(
        db_session,
        "plush-pepe",
        manual,
        external,
        stars_per_gram=Decimal(1),
        settings=settings,
        now=now,
    )
    create_pool_version(db_session, round_.id, snapshot.id, settings=settings, now=now)
    return round_.id, gift_id


def test_catalog_returns_all_ten_collections_with_aggregate_stats(
    client: TestClient, db_session: Session
) -> None:
    prepare_catalog(db_session)

    response = client.get("/api/collections")

    assert response.status_code == 200
    body = response.json()
    assert body["asset_mode"] == "simulated"
    assert len(body["collections"]) == 10
    assert len({item["id"] for item in body["collections"]}) == 10
    active = next(item for item in body["collections"] if item["id"] == "plush-pepe")
    assert active["available"] is True
    assert active["pool"]["version"] == 1
    assert active["pool"]["price"] == 144
    assert active["pool"]["remaining_count"] == 4
    assert active["pool"]["value_distribution"]["below_ticket_count"] == 3
    unpriced = next(item for item in body["collections"] if item["id"] != "plush-pepe")
    assert unpriced["pool"] is None
    assert unpriced["available"] is False


def test_detail_exposes_provenance_but_no_hidden_gift_data_or_logs(
    client: TestClient,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, gift_id = prepare_catalog(db_session)
    caplog.set_level(logging.DEBUG)

    response = client.get("/api/collections/plush-pepe")

    assert response.status_code == 200
    body = response.json()
    serialized = response.text
    assert body["pool"]["commitment_algorithm"] == "SHA-256/gift-pool-v1"
    assert body["pool"]["draw_algorithm"] == "gift-draw-v1"
    assert body["valuation"]["primary_source"] == "manual Stars-floor evidence"
    assert body["valuation"]["external_attribution"] == "Data: TG Gifts (https://tggifts.com)"
    assert body["valuation"]["external_license"] == "CC BY 4.0"
    assert body["valuation"]["conversion_rule"]["stars_per_gram"] == "1"
    assert body["valuation"]["stale"] is False
    assert body["round"]["disclosure_deadline"]
    for forbidden in (
        SECRET_MODEL,
        SECRET_EVIDENCE,
        gift_id,
        "manifest_json",
        "source_payload_json",
        "provenance_json",
        "evidence_url",
        '"gifts"',
    ):
        assert forbidden not in serialized
        assert forbidden not in caplog.text


def test_stale_valuation_is_visible_and_not_available(
    client: TestClient, db_session: Session
) -> None:
    prepare_catalog(db_session)
    snapshot = db_session.scalar(
        select(MarketSnapshot).where(MarketSnapshot.collection_id == "plush-pepe")
    )
    assert snapshot is not None
    snapshot.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    response = client.get("/api/collections/plush-pepe")

    assert response.status_code == 200
    assert response.json()["valuation"]["stale"] is True
    assert response.json()["available"] is False


def test_unknown_collection_returns_404(client: TestClient) -> None:
    response = client.get("/api/collections/not-a-collection")

    assert response.status_code == 404
    assert response.json() == {"detail": "Collection not found"}
