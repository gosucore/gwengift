import argparse
import json
import random
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Collection, MarketSnapshot, Round, VirtualGift
from app.services.economics import calculate_gift_valuations, calculate_pool_economics

DISCLAIMER = (
    "Expected margin is not a short-term profit guarantee; simulations describe adverse "
    "outcomes for virtual demo assets only."
)


@dataclass(frozen=True)
class RiskReport:
    seed: str
    volume: int
    simulations: int
    pool_size: int
    ticket_price: int
    fee_per_draw: Decimal
    expected_margin_per_draw: Decimal
    mean_final_margin: Decimal
    p05_final_margin: Decimal
    worst_final_margin: Decimal
    maximum_drawdown: Decimal
    p95_reserve_requirement: Decimal
    maximum_reserve_requirement: Decimal
    disclaimer: str = DISCLAIMER


def _nearest_rank(values: list[Decimal], percentile: Decimal) -> Decimal:
    ordered = sorted(values)
    index = int((percentile * len(ordered)).to_integral_value(rounding=ROUND_CEILING)) - 1
    return ordered[max(0, index)]


def simulate_pool_risk(
    replacement_costs: list[Decimal],
    ticket_price: int,
    *,
    fee_per_draw: Decimal = Decimal(0),
    volume: int = 1_000,
    simulations: int = 1_000,
    seed: str = "gwengift-risk-v1",
) -> RiskReport:
    if not replacement_costs or ticket_price <= 0 or volume <= 0 or simulations <= 0:
        raise ValueError("Pool, price, volume, and simulation count must be positive")
    if fee_per_draw < 0 or any(cost < 0 for cost in replacement_costs):
        raise ValueError("Costs and fees cannot be negative")

    final_margins: list[Decimal] = []
    reserve_requirements: list[Decimal] = []
    maximum_drawdown = Decimal(0)
    pool_size = len(replacement_costs)
    for simulation in range(simulations):
        rng = random.Random(f"{seed}:{simulation}")  # Risk simulation only, never gift draws.
        order = list(range(pool_size))
        cumulative = Decimal(0)
        peak = Decimal(0)
        largest_drawdown = Decimal(0)
        for draw in range(volume):
            if draw % pool_size == 0:
                rng.shuffle(order)
            replacement = replacement_costs[order[draw % pool_size]]
            cumulative += Decimal(ticket_price) - replacement - fee_per_draw
            peak = max(peak, cumulative)
            largest_drawdown = max(largest_drawdown, peak - cumulative)
        final_margins.append(cumulative)
        reserve_requirements.append(max(Decimal(0), largest_drawdown))
        maximum_drawdown = max(maximum_drawdown, largest_drawdown)

    expected_margin = (
        Decimal(ticket_price)
        - sum(replacement_costs, Decimal(0)) / Decimal(pool_size)
        - fee_per_draw
    )
    return RiskReport(
        seed=seed,
        volume=volume,
        simulations=simulations,
        pool_size=pool_size,
        ticket_price=ticket_price,
        fee_per_draw=fee_per_draw,
        expected_margin_per_draw=expected_margin,
        mean_final_margin=sum(final_margins, Decimal(0)) / Decimal(simulations),
        p05_final_margin=_nearest_rank(final_margins, Decimal("0.05")),
        worst_final_margin=min(final_margins),
        maximum_drawdown=maximum_drawdown,
        p95_reserve_requirement=_nearest_rank(reserve_requirements, Decimal("0.95")),
        maximum_reserve_requirement=max(reserve_requirements),
    )


def report_json(report: RiskReport) -> str:
    def convert(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        return value

    return json.dumps(convert(asdict(report)), ensure_ascii=False, sort_keys=True, indent=2)


def generate_collection_risk_report(
    session: Session,
    collection_id: str,
    *,
    seed: str,
    volume: int,
    simulations: int,
    fee_per_draw: Decimal,
) -> RiskReport:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise ValueError("Collection does not exist")
    round_ = session.scalar(
        select(Round).where(Round.collection_id == collection_id).order_by(Round.created_at.desc())
    )
    snapshot = session.scalar(
        select(MarketSnapshot)
        .where(MarketSnapshot.collection_id == collection_id)
        .order_by(MarketSnapshot.created_at.desc())
    )
    if round_ is None or snapshot is None:
        raise ValueError("Collection requires a seeded round and market snapshot")
    gifts = list(
        session.scalars(
            select(VirtualGift).where(
                VirtualGift.round_id == round_.id, VirtualGift.lifecycle == "AVAILABLE"
            )
        ).all()
    )
    settings = get_settings()
    valuations = calculate_gift_valuations(gifts, snapshot, settings)
    economics = calculate_pool_economics(valuations, snapshot, settings)
    return simulate_pool_risk(
        [valuation.replacement_cost for valuation in valuations],
        economics.price,
        fee_per_draw=fee_per_draw,
        volume=volume,
        simulations=simulations,
        seed=seed,
    )


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Simulate demo-pool drawdown and reserves")
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--seed", default="gwengift-risk-v1")
    parser.add_argument("--volume", type=int, default=1_000)
    parser.add_argument("--simulations", type=int, default=1_000)
    parser.add_argument("--fee-per-draw", type=Decimal, default=Decimal(0))
    args = parser.parse_args()
    with SessionLocal() as session:
        report = generate_collection_risk_report(
            session,
            args.collection_id,
            seed=args.seed,
            volume=args.volume,
            simulations=args.simulations,
            fee_per_draw=args.fee_per_draw,
        )
    print(report_json(report))


if __name__ == "__main__":
    main()
