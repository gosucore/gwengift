import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Bet,
    Collection,
    Disclosure,
    DrandProof,
    LedgerEntry,
    MarketSnapshot,
    PoolVersion,
    Round,
    VirtualGift,
    utc_now,
)
from app.services.commitments import PoolManifest
from app.telemetry import operation_span, set_operation_attribute

DISCLOSURE_SCHEMA_VERSION: Literal[1] = 1


class DisclosureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DisclosedRound(DisclosureModel):
    id: str
    collection_id: str
    status: Literal["DISCLOSED"]
    opens_at: datetime
    closes_at: datetime
    disclosure_deadline: datetime
    disclosed_at: datetime


class DisclosedPoolVersion(DisclosureModel):
    id: str
    version: int
    commitment: str
    manifest: PoolManifest
    price: int
    expected_value: Decimal
    actual_rtp: Decimal
    operator_margin: Decimal
    remaining_count: int
    value_distribution: dict[str, Any]
    market_snapshot_id: str
    created_at: datetime


class DisclosedMarketSnapshot(DisclosureModel):
    id: str
    collection_id: str
    primary_source: str
    external_source: str
    source_currency: str
    conversion_rule: str
    liquidity_discount: Decimal
    source_payload: dict[str, Any]
    provenance: dict[str, Any]
    cross_check_discrepancy: Decimal | None
    observed_at: datetime
    expires_at: datetime
    created_at: datetime


class DisclosedLedgerEntry(DisclosureModel):
    id: str
    kind: Literal["DEBIT", "RESTORATION"]
    amount: int
    balance_after: int
    created_at: datetime


class DisclosedBeaconProof(DisclosureModel):
    network: str
    round: int
    signature: str
    randomness: str
    verification_result: Literal[True]
    response: dict[str, Any]
    verified_at: datetime


class DisclosedBet(DisclosureModel):
    id: str
    user_epoch: int
    pool_version_id: str
    pool_version_hash: str
    idempotency_key: str
    future_beacon_round: int
    acceptance_cutoff: datetime
    resolution_deadline: datetime
    state: Literal["COMPLETED", "CANCELLED"]
    price: int
    remaining_count: int
    selected_gift_id: str | None
    cancellation_reason: str | None
    created_at: datetime
    resolved_at: datetime
    ledger_entries: list[DisclosedLedgerEntry]
    beacon_proof: DisclosedBeaconProof | None


class DisclosedGift(DisclosureModel):
    id: str
    model: str
    backdrop: str
    symbol: str
    rarity: str
    number: int
    player_sale_estimate: int
    replacement_cost: int
    lifecycle: Literal["AVAILABLE", "AWARDED"]
    owner_epoch: int | None


class DisclosurePackage(DisclosureModel):
    schema_version: Literal[1] = DISCLOSURE_SCHEMA_VERSION
    asset_mode: Literal["simulated"] = "simulated"
    round: DisclosedRound
    algorithms: dict[str, str]
    pool_versions: list[DisclosedPoolVersion]
    market_snapshots: list[DisclosedMarketSnapshot]
    bets: list[DisclosedBet]
    gifts: list[DisclosedGift]


def canonical_disclosure_json(package: DisclosurePackage) -> str:
    return json.dumps(
        package.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def disclosure_package_hash(package_json: str) -> str:
    return hashlib.sha256(package_json.encode("utf-8")).hexdigest()


def _build_bet(session: Session, bet: Bet) -> DisclosedBet:
    ledger_entries = list(
        session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.bet_id == bet.id)
            .order_by(LedgerEntry.created_at, LedgerEntry.id)
        ).all()
    )
    proof = session.scalar(select(DrandProof).where(DrandProof.bet_id == bet.id))
    disclosed_proof = None
    if proof is not None:
        disclosed_proof = DisclosedBeaconProof(
            network=proof.network,
            round=proof.beacon_round,
            signature=proof.signature,
            randomness=proof.randomness,
            verification_result=True,
            response=json.loads(proof.response_json),
            verified_at=proof.verified_at,
        )
    if bet.resolved_at is None or bet.state not in {"COMPLETED", "CANCELLED"}:
        raise ValueError("Disclosure requires final bet outcomes")
    return DisclosedBet(
        id=bet.id,
        user_epoch=bet.user_epoch,
        pool_version_id=bet.pool_version_id,
        pool_version_hash=bet.pool_version_hash,
        idempotency_key=bet.idempotency_key,
        future_beacon_round=bet.future_beacon_round,
        acceptance_cutoff=bet.acceptance_cutoff,
        resolution_deadline=bet.resolution_deadline,
        state=bet.state,
        price=bet.price,
        remaining_count=bet.remaining_count,
        selected_gift_id=bet.selected_gift_id,
        cancellation_reason=bet.cancellation_reason,
        created_at=bet.created_at,
        resolved_at=bet.resolved_at,
        ledger_entries=[
            DisclosedLedgerEntry(
                id=entry.id,
                kind=entry.kind,
                amount=entry.amount,
                balance_after=entry.balance_after,
                created_at=entry.created_at,
            )
            for entry in ledger_entries
        ],
        beacon_proof=disclosed_proof,
    )


def _build_package(session: Session, round_: Round, disclosed_at: datetime) -> DisclosurePackage:
    pool_versions = list(
        session.scalars(
            select(PoolVersion)
            .where(PoolVersion.round_id == round_.id)
            .order_by(PoolVersion.version)
        ).all()
    )
    snapshot_ids = sorted({pool.market_snapshot_id for pool in pool_versions})
    snapshots = [
        snapshot
        for snapshot_id in snapshot_ids
        if (snapshot := session.get(MarketSnapshot, snapshot_id)) is not None
    ]
    if len(snapshots) != len(snapshot_ids):
        raise ValueError("A referenced market snapshot is missing")
    bets = list(
        session.scalars(
            select(Bet).where(Bet.round_id == round_.id).order_by(Bet.created_at, Bet.id)
        )
    )
    gifts = list(
        session.scalars(
            select(VirtualGift).where(VirtualGift.round_id == round_.id).order_by(VirtualGift.id)
        ).all()
    )
    return DisclosurePackage(
        round=DisclosedRound(
            id=round_.id,
            collection_id=round_.collection_id,
            status="DISCLOSED",
            opens_at=round_.opens_at,
            closes_at=round_.closes_at,
            disclosure_deadline=round_.disclosure_deadline,
            disclosed_at=disclosed_at,
        ),
        algorithms={
            "pool_commitment": "gift-pool-v1-sha256",
            "selection": "gift-draw-v1-sha256-rejection-v1",
            "beacon": "drand-quicknet-bls-unchained-g1-rfc9380",
            "canonical_json": "utf8-sorted-keys-compact",
        },
        pool_versions=[
            DisclosedPoolVersion(
                id=pool.id,
                version=pool.version,
                commitment=pool.commitment,
                manifest=PoolManifest.model_validate_json(pool.manifest_json),
                price=pool.price,
                expected_value=pool.expected_value,
                actual_rtp=pool.actual_rtp,
                operator_margin=pool.operator_margin,
                remaining_count=pool.remaining_count,
                value_distribution=json.loads(pool.value_distribution_json),
                market_snapshot_id=pool.market_snapshot_id,
                created_at=pool.created_at,
            )
            for pool in pool_versions
        ],
        market_snapshots=[
            DisclosedMarketSnapshot(
                id=snapshot.id,
                collection_id=snapshot.collection_id,
                primary_source=snapshot.primary_source,
                external_source=snapshot.external_source,
                source_currency=snapshot.source_currency,
                conversion_rule=snapshot.conversion_rule,
                liquidity_discount=snapshot.liquidity_discount,
                source_payload=json.loads(snapshot.source_payload_json),
                provenance=json.loads(snapshot.provenance_json),
                cross_check_discrepancy=snapshot.cross_check_discrepancy,
                observed_at=snapshot.observed_at,
                expires_at=snapshot.expires_at,
                created_at=snapshot.created_at,
            )
            for snapshot in snapshots
        ],
        bets=[_build_bet(session, bet) for bet in bets],
        gifts=[
            DisclosedGift(
                id=gift.id,
                model=gift.model,
                backdrop=gift.backdrop,
                symbol=gift.symbol,
                rarity=gift.rarity,
                number=gift.number,
                player_sale_estimate=gift.player_sale_estimate,
                replacement_cost=gift.replacement_cost,
                lifecycle=gift.lifecycle,
                owner_epoch=gift.owner_epoch,
            )
            for gift in gifts
        ],
    )


def disclose_round_in_transaction(
    session: Session, round_id: str, *, now: datetime | None = None
) -> Disclosure:
    with operation_span("round.disclose", attributes={"gwengift.round_id": round_id}) as span:
        disclosure = _disclose_round_in_transaction(session, round_id, now=now)
        if span is not None:
            set_operation_attribute(span, "gwengift.outcome", "DISCLOSED")
        return disclosure


def _disclose_round_in_transaction(
    session: Session, round_id: str, *, now: datetime | None = None
) -> Disclosure:
    existing = session.scalar(select(Disclosure).where(Disclosure.round_id == round_id))
    if existing is not None:
        return existing
    round_ = session.get(Round, round_id)
    if round_ is None:
        raise ValueError("Round does not exist")
    current_time = utc_now() if now is None else now
    active_bet = session.scalar(
        select(Bet.id).where(
            Bet.round_id == round_id, Bet.state.in_(["PENDING_RANDOMNESS", "RESOLVING"])
        )
    )
    if active_bet is not None:
        raise ValueError("Pending attempts must reach a final outcome before disclosure")
    remaining_count = len(
        list(
            session.scalars(
                select(VirtualGift.id).where(
                    VirtualGift.round_id == round_id, VirtualGift.lifecycle == "AVAILABLE"
                )
            ).all()
        )
    )
    if remaining_count > 0 and current_time < round_.disclosure_deadline:
        raise ValueError("An unsold round cannot be disclosed before its deadline")

    collection = session.get(Collection, round_.collection_id)
    if collection is None:
        raise ValueError("Round collection does not exist")
    round_.status = "DISCLOSED"
    round_.disclosed_at = current_time
    collection.status = "PAUSED"
    package = _build_package(session, round_, current_time)
    package_json = canonical_disclosure_json(package)
    disclosure = Disclosure(
        round_id=round_id,
        package_json=package_json,
        package_hash=disclosure_package_hash(package_json),
        created_at=current_time,
    )
    session.add(disclosure)
    session.flush()
    return disclosure


def disclose_round(session: Session, round_id: str, *, now: datetime | None = None) -> Disclosure:
    with session.begin():
        return disclose_round_in_transaction(session, round_id, now=now)
