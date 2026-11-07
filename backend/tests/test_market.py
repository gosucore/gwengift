import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Collection, MarketSnapshot
from app.seeds import seed_demo_catalog
from app.services.market import (
    MarketDataError,
    fetch_tg_gifts_daily,
    import_market_snapshot,
)

NOW = datetime(2026, 11, 6, 12, 0, 0)
COLLECTION_ID = "plush-pepe"


def manual_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "collection_id": COLLECTION_ID,
        "observed_at": (NOW - timedelta(hours=1)).isoformat(),
        "liquidity_discount": "0.10",
        "gifts": [
            {
                "number": number,
                "floor_stars": floor,
                "evidence_url": f"https://evidence.example/{COLLECTION_ID}/{number}",
            }
            for number, floor in enumerate((90, 110, 135, 180), start=1)
        ],
    }


def external_payload(floor_gram: int = 90) -> dict[str, object]:
    return {
        "source": "Fragment public pages via TG Gifts (tggifts.com)",
        "license": "CC BY 4.0, attribution: TG Gifts (tggifts.com)",
        "generated": NOW.isoformat() + "Z",
        "collections": {
            COLLECTION_ID: {
                "name": "Plush Pepe",
                "days": [[NOW.date().isoformat(), floor_gram, 2, "b"]],
            }
        },
    }


def import_settings(action: str = "pause") -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        market_discrepancy_threshold=Decimal("0.20"),
        market_discrepancy_action=action,
    )


def test_valid_import_records_provenance_and_attribution(db_session: Session) -> None:
    seed_demo_catalog(db_session, now=NOW)

    snapshot = import_market_snapshot(
        db_session,
        COLLECTION_ID,
        manual_payload(),
        external_payload(),
        stars_per_gram=Decimal("1"),
        settings=import_settings(),
        now=NOW,
    )

    assert snapshot.observed_at == NOW - timedelta(hours=1)
    assert snapshot.cross_check_discrepancy == 0
    provenance = json.loads(snapshot.provenance_json)
    assert provenance["external"]["license"].startswith("CC BY 4.0")
    assert provenance["external"]["recent_sales"] == 2
    assert provenance["availability"] == "open"
    collection = db_session.get(Collection, COLLECTION_ID)
    assert collection is not None
    assert collection.status == "OPEN"


@pytest.mark.parametrize("problem", ["malformed", "missing", "stale"])
def test_bad_inputs_pause_collection_without_snapshot(db_session: Session, problem: str) -> None:
    seed_demo_catalog(db_session, now=NOW)
    manual = manual_payload()
    external = external_payload()
    if problem == "malformed":
        del manual["gifts"]
    elif problem == "missing":
        external["collections"] = {}
    else:
        manual["observed_at"] = (NOW - timedelta(hours=25)).isoformat()

    with pytest.raises(MarketDataError):
        import_market_snapshot(
            db_session,
            COLLECTION_ID,
            manual,
            external,
            stars_per_gram=Decimal("1"),
            settings=import_settings(),
            now=NOW,
        )

    collection = db_session.get(Collection, COLLECTION_ID)
    assert collection is not None
    assert collection.status == "PAUSED"
    assert db_session.scalar(select(func.count()).select_from(MarketSnapshot)) == 0


def test_material_disagreement_records_snapshot_and_pauses(db_session: Session) -> None:
    seed_demo_catalog(db_session, now=NOW)

    snapshot = import_market_snapshot(
        db_session,
        COLLECTION_ID,
        manual_payload(),
        external_payload(floor_gram=200),
        stars_per_gram=Decimal("1"),
        settings=import_settings("pause"),
        now=NOW,
    )

    assert snapshot.cross_check_discrepancy == Decimal("0.55")
    collection = db_session.get(Collection, COLLECTION_ID)
    assert collection is not None
    assert collection.status == "PAUSED"
    assert json.loads(snapshot.provenance_json)["availability"] == "paused"


def test_material_disagreement_can_apply_conservative_discount(db_session: Session) -> None:
    seed_demo_catalog(db_session, now=NOW)

    snapshot = import_market_snapshot(
        db_session,
        COLLECTION_ID,
        manual_payload(),
        external_payload(floor_gram=200),
        stars_per_gram=Decimal("1"),
        settings=import_settings("discount"),
        now=NOW,
    )

    assert snapshot.liquidity_discount == Decimal("0.35")
    collection = db_session.get(Collection, COLLECTION_ID)
    assert collection is not None
    assert collection.status == "OPEN"
    assert json.loads(snapshot.provenance_json)["discrepancy_action"] == "discount"


def test_daily_import_uses_fresh_cache_when_network_fails(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache" / "floors.json"

    def successful(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=external_payload())

    fresh = fetch_tg_gifts_daily(
        url="https://tggifts.com/data/floors-daily.json",
        cache_path=cache_path,
        transport=httpx.MockTransport(successful),
        now=NOW,
    )
    assert fresh.from_cache is False
    assert cache_path.exists()

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    cached = fetch_tg_gifts_daily(
        url="https://tggifts.com/data/floors-daily.json",
        cache_path=cache_path,
        transport=httpx.MockTransport(offline),
        now=NOW + timedelta(hours=1),
    )
    assert cached.from_cache is True
    assert cached.payload == external_payload()

    with pytest.raises(MarketDataError, match="no fresh cache"):
        fetch_tg_gifts_daily(
            url="https://tggifts.com/data/floors-daily.json",
            cache_path=cache_path,
            transport=httpx.MockTransport(offline),
            now=NOW + timedelta(hours=7),
        )
