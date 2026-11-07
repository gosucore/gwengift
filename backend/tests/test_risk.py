import json
import sys
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.seeds import seed_demo_catalog
from app.services.market import import_market_snapshot
from app.services.risk import generate_collection_risk_report, report_json, simulate_pool_risk

NOW = datetime(2026, 11, 6, 12, 0, 0)


def test_identical_seeds_reproduce_drawdown_and_reserve_report() -> None:
    costs = [Decimal(100), Decimal(200), Decimal(300), Decimal(400)]

    first = simulate_pool_risk(
        costs,
        278,
        fee_per_draw=Decimal(5),
        volume=250,
        simulations=200,
        seed="repeatable",
    )
    second = simulate_pool_risk(
        costs,
        278,
        fee_per_draw=Decimal(5),
        volume=250,
        simulations=200,
        seed="repeatable",
    )

    assert first == second
    assert first.expected_margin_per_draw == 23
    assert first.p95_reserve_requirement >= 0
    assert first.maximum_reserve_requirement >= first.p95_reserve_requirement
    assert first.maximum_drawdown >= 0
    assert "not a short-term profit guarantee" in first.disclaimer
    assert json.loads(report_json(first))["disclaimer"] == first.disclaimer


def test_different_seed_changes_simulated_outcome() -> None:
    costs = [Decimal(50), Decimal(500)]

    first = simulate_pool_risk(costs, 300, volume=10, simulations=20, seed="a")
    second = simulate_pool_risk(costs, 300, volume=10, simulations=20, seed="b")

    assert first != second


def test_invalid_risk_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        simulate_pool_risk([], 100)
    with pytest.raises(ValueError):
        simulate_pool_risk([Decimal(100)], 100, volume=0)


def import_test_snapshot(db_session: Session) -> None:
    seed_demo_catalog(db_session, now=NOW)
    manual = {
        "schema_version": 1,
        "collection_id": "plush-pepe",
        "observed_at": NOW.isoformat(),
        "liquidity_discount": "0.10",
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
    import_market_snapshot(
        db_session,
        "plush-pepe",
        manual,
        external,
        stars_per_gram=Decimal(1),
        settings=Settings(_env_file=None, environment="test"),
        now=NOW,
    )


def test_documented_report_command(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import_test_snapshot(db_session)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "risk",
            "--collection-id",
            "plush-pepe",
            "--seed",
            "cli-test",
            "--volume",
            "20",
            "--simulations",
            "10",
        ],
    )

    from app.services import risk

    risk.main()
    output = json.loads(capsys.readouterr().out)

    assert output["pool_size"] == 4
    assert output["volume"] == 20
    assert output["simulations"] == 10
    assert "not a short-term profit guarantee" in output["disclaimer"]


def test_collection_report_uses_current_pool(db_session: Session) -> None:
    import_test_snapshot(db_session)

    report = generate_collection_risk_report(
        db_session,
        "plush-pepe",
        seed="database",
        volume=10,
        simulations=10,
        fee_per_draw=Decimal(0),
    )

    assert report.pool_size == 4
    assert report.ticket_price > 0
