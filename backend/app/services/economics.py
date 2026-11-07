import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from statistics import median

from app.config import Settings
from app.models import MarketSnapshot, VirtualGift, utc_now
from app.services.market import ManualStarsFloor


@dataclass(frozen=True)
class GiftValuation:
    gift_id: str
    gift_number: int
    acquisition_cost: Decimal
    expected_fees: Decimal
    replacement_cost: Decimal
    player_sale_estimate: Decimal


@dataclass(frozen=True)
class PoolEconomics:
    price: int
    expected_value: Decimal
    actual_rtp: Decimal
    rounding_premium_stars: Decimal
    mean_replacement_cost: Decimal
    mean_expected_fees: Decimal
    operator_margin: Decimal
    worst_outcome_ratio: Decimal
    value_distribution: dict[str, object]
    eligible: bool
    ineligibility_reasons: tuple[str, ...]


def calculate_gift_valuations(
    gifts: list[VirtualGift],
    snapshot: MarketSnapshot,
    settings: Settings,
) -> list[GiftValuation]:
    provenance = json.loads(snapshot.provenance_json)
    manual = ManualStarsFloor.model_validate(provenance["manual"])
    floors = {gift.number: Decimal(gift.floor_stars) for gift in manual.gifts}
    valuations: list[GiftValuation] = []
    for gift in gifts:
        if gift.number not in floors:
            raise ValueError(f"Missing manual floor for gift number {gift.number}")
        acquisition = floors[gift.number]
        fees = acquisition * settings.replacement_fee_rate
        player_sale = acquisition * (Decimal("1") - snapshot.liquidity_discount)
        valuations.append(
            GiftValuation(
                gift_id=gift.id,
                gift_number=gift.number,
                acquisition_cost=acquisition,
                expected_fees=fees,
                replacement_cost=acquisition + fees,
                player_sale_estimate=player_sale,
            )
        )
    return valuations


def calculate_pool_economics(
    valuations: list[GiftValuation],
    snapshot: MarketSnapshot,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> PoolEconomics:
    if not valuations:
        raise ValueError("Cannot price an empty pool")
    current_time = utc_now() if now is None else now
    count = Decimal(len(valuations))
    expected_value = sum((item.player_sale_estimate for item in valuations), Decimal(0)) / count
    exact_price = expected_value / settings.target_rtp
    price = int(exact_price.to_integral_value(rounding=ROUND_CEILING))
    actual_rtp = expected_value / Decimal(price)
    mean_replacement = sum((item.replacement_cost for item in valuations), Decimal(0)) / count
    mean_fees = sum((item.expected_fees for item in valuations), Decimal(0)) / count
    operator_margin = Decimal(price) - mean_replacement
    worst_outcome = min(item.player_sale_estimate for item in valuations)
    worst_outcome_ratio = worst_outcome / Decimal(price)
    sale_estimates = [item.player_sale_estimate for item in valuations]
    distribution: dict[str, object] = {
        "minimum": str(min(sale_estimates)),
        "median": str(median(sale_estimates)),
        "maximum": str(max(sale_estimates)),
        "below_ticket_count": sum(value < price for value in sale_estimates),
        "at_or_above_ticket_count": sum(value >= price for value in sale_estimates),
    }

    reasons: list[str] = []
    provenance = json.loads(snapshot.provenance_json)
    if current_time >= snapshot.expires_at:
        reasons.append("stale_valuation")
    if actual_rtp < settings.minimum_rtp:
        reasons.append("rtp_below_minimum")
    if operator_margin < settings.minimum_operator_margin:
        reasons.append("negative_or_insufficient_operator_margin")
    if worst_outcome_ratio < settings.minimum_worst_outcome_ratio:
        reasons.append("worst_outcome_below_minimum")
    if provenance.get("availability") == "paused":
        reasons.append("market_discrepancy_pause")
    external = provenance.get("external", {})
    recent_sales = external.get("recent_sales")
    if not isinstance(recent_sales, int) or recent_sales < settings.minimum_recent_sales:
        reasons.append("insufficient_liquidity")
    if snapshot.liquidity_discount > settings.maximum_liquidity_discount:
        reasons.append("liquidity_discount_above_maximum")

    return PoolEconomics(
        price=price,
        expected_value=expected_value,
        actual_rtp=actual_rtp,
        rounding_premium_stars=Decimal(price) - exact_price,
        mean_replacement_cost=mean_replacement,
        mean_expected_fees=mean_fees,
        operator_margin=operator_margin,
        worst_outcome_ratio=worst_outcome_ratio,
        value_distribution=distribution,
        eligible=not reasons,
        ineligibility_reasons=tuple(reasons),
    )
