import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.config import Settings
from app.models import MarketSnapshot, VirtualGift
from app.services.economics import calculate_gift_valuations, calculate_pool_economics

NOW = datetime(2026, 11, 6, 12, 0, 0)


def settings() -> Settings:
    return Settings(_env_file=None, environment="test")


def make_gifts(count: int) -> list[VirtualGift]:
    return [
        VirtualGift(
            id=f"gift-{number}",
            collection_id="test",
            round_id="round",
            model=f"Model {number}",
            backdrop="Backdrop",
            symbol="Symbol",
            rarity="Epic" if number % 2 else "Common",
            number=number,
            player_sale_estimate=0,
            replacement_cost=0,
        )
        for number in range(1, count + 1)
    ]


def make_snapshot(
    floors: list[int],
    *,
    discount: str = "0",
    recent_sales: int = 5,
    expires_at: datetime | None = None,
) -> MarketSnapshot:
    manual = {
        "schema_version": 1,
        "collection_id": "test",
        "observed_at": NOW.isoformat(),
        "liquidity_discount": discount,
        "gifts": [
            {
                "number": number,
                "floor_stars": floor,
                "evidence_url": f"https://evidence.example/{number}",
            }
            for number, floor in enumerate(floors, start=1)
        ],
    }
    provenance = {
        "manual": manual,
        "availability": "open",
        "external": {"recent_sales": recent_sales},
    }
    return MarketSnapshot(
        collection_id="test",
        primary_source="manual",
        external_source="TG Gifts",
        source_currency="STARS",
        conversion_rule="{}",
        liquidity_discount=Decimal(discount),
        source_payload_json="{}",
        provenance_json=json.dumps(provenance),
        observed_at=NOW,
        expires_at=expires_at or NOW + timedelta(hours=24),
    )


def test_formula_example_and_rounding_disclosure() -> None:
    snapshot = make_snapshot([100, 200, 300, 400])
    valuations = calculate_gift_valuations(make_gifts(4), snapshot, settings())

    economics = calculate_pool_economics(valuations, snapshot, settings(), now=NOW)

    assert economics.expected_value == 250
    assert economics.price == 278
    assert economics.actual_rtp == Decimal(250) / Decimal(278)
    assert economics.rounding_premium_stars == Decimal(278) - Decimal(250) / Decimal("0.9")
    assert economics.actual_rtp < Decimal("0.90")
    assert economics.mean_expected_fees == Decimal("12.5")
    assert economics.mean_replacement_cost == Decimal("262.5")
    assert economics.operator_margin == Decimal("15.5")
    assert economics.eligible is True
    assert economics.value_distribution["below_ticket_count"] == 2


def test_conservative_discount_and_no_unsupported_attribute_premium() -> None:
    snapshot = make_snapshot([100, 100], discount="0.10")

    valuations = calculate_gift_valuations(make_gifts(2), snapshot, settings())

    assert [item.player_sale_estimate for item in valuations] == [Decimal(90), Decimal(90)]
    assert [item.replacement_cost for item in valuations] == [Decimal(105), Decimal(105)]


def test_negative_operator_margin_rejects_pool() -> None:
    snapshot = make_snapshot([100, 200, 300, 400])
    high_fees = Settings(
        _env_file=None,
        environment="test",
        replacement_fee_rate=Decimal("1"),
    )
    valuations = calculate_gift_valuations(make_gifts(4), snapshot, high_fees)

    economics = calculate_pool_economics(valuations, snapshot, high_fees, now=NOW)

    assert economics.operator_margin < 0
    assert economics.eligible is False
    assert "negative_or_insufficient_operator_margin" in economics.ineligibility_reasons


def test_weak_worst_outcome_rejects_pool() -> None:
    snapshot = make_snapshot([10, 1000])
    valuations = calculate_gift_valuations(make_gifts(2), snapshot, settings())

    economics = calculate_pool_economics(valuations, snapshot, settings(), now=NOW)

    assert economics.worst_outcome_ratio < Decimal("0.20")
    assert "worst_outcome_below_minimum" in economics.ineligibility_reasons
    assert economics.eligible is False


def test_stale_valuation_rejects_pool() -> None:
    snapshot = make_snapshot([100, 200], expires_at=NOW)
    valuations = calculate_gift_valuations(make_gifts(2), snapshot, settings())

    economics = calculate_pool_economics(valuations, snapshot, settings(), now=NOW)

    assert "stale_valuation" in economics.ineligibility_reasons
    assert economics.eligible is False


def test_low_liquidity_rejects_pool() -> None:
    snapshot = make_snapshot([100, 200], recent_sales=1)
    valuations = calculate_gift_valuations(make_gifts(2), snapshot, settings())

    economics = calculate_pool_economics(valuations, snapshot, settings(), now=NOW)

    assert "insufficient_liquidity" in economics.ineligibility_reasons
    assert economics.eligible is False


def test_empty_pool_cannot_be_priced() -> None:
    with pytest.raises(ValueError, match="empty pool"):
        calculate_pool_economics([], make_snapshot([100]), settings(), now=NOW)
