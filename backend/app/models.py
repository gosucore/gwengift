import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return naive UTC consistently, including when SQLite omits tzinfo."""
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    active_epoch: Mapped[int] = mapped_column(Integer, default=1)
    demo_balance: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("active_epoch >= 1", name="ck_users_epoch_positive"),
        CheckConstraint("demo_balance >= 0", name="ck_users_balance_nonnegative"),
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="PAUSED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'PAUSED')", name="ck_collections_status"),
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    opens_at: Mapped[datetime] = mapped_column(DateTime)
    closes_at: Mapped[datetime] = mapped_column(DateTime)
    disclosure_deadline: Mapped[datetime] = mapped_column(DateTime)
    disclosed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'CLOSED', 'DISCLOSED')",
            name="ck_rounds_status",
        ),
    )


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    primary_source: Mapped[str] = mapped_column(String(100))
    external_source: Mapped[str] = mapped_column(String(100))
    source_currency: Mapped[str] = mapped_column(String(16))
    conversion_rule: Mapped[str] = mapped_column(Text)
    liquidity_discount: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    source_payload_json: Mapped[str] = mapped_column(Text)
    provenance_json: Mapped[str] = mapped_column(Text)
    cross_check_discrepancy: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "liquidity_discount >= 0 AND liquidity_discount <= 1",
            name="ck_market_snapshots_discount",
        ),
    )


class VirtualGift(Base):
    __tablename__ = "virtual_gifts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"), index=True)
    model: Mapped[str] = mapped_column(String(100))
    backdrop: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[str] = mapped_column(String(100))
    rarity: Mapped[str] = mapped_column(String(100))
    number: Mapped[int] = mapped_column(Integer)
    player_sale_estimate: Mapped[int] = mapped_column(Integer)
    replacement_cost: Mapped[int] = mapped_column(Integer)
    lifecycle: Mapped[str] = mapped_column(String(16), default="AVAILABLE")
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    owner_epoch: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "lifecycle IN ('AVAILABLE', 'RESERVED', 'AWARDED')",
            name="ck_virtual_gifts_lifecycle",
        ),
        CheckConstraint("number >= 0", name="ck_virtual_gifts_number_nonnegative"),
        CheckConstraint(
            "player_sale_estimate >= 0 AND replacement_cost >= 0",
            name="ck_virtual_gifts_values_nonnegative",
        ),
        Index("ix_virtual_gifts_owner_epoch", "owner_user_id", "owner_epoch"),
    )


class PoolVersion(Base):
    __tablename__ = "pool_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    manifest_json: Mapped[str] = mapped_column(Text)
    commitment: Mapped[str] = mapped_column(String(64), unique=True)
    price: Mapped[int] = mapped_column(Integer)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    actual_rtp: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    operator_margin: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    remaining_count: Mapped[int] = mapped_column(Integer)
    value_distribution_json: Mapped[str] = mapped_column(Text)
    market_snapshot_id: Mapped[str] = mapped_column(ForeignKey("market_snapshots.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("round_id", "version", name="uq_pool_versions_round_version"),
        CheckConstraint("version >= 1", name="ck_pool_versions_version_positive"),
        CheckConstraint("price > 0", name="ck_pool_versions_price_positive"),
        CheckConstraint("remaining_count >= 0", name="ck_pool_versions_remaining_nonnegative"),
    )


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_epoch: Mapped[int] = mapped_column(Integer)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"), index=True)
    pool_version_id: Mapped[str] = mapped_column(ForeignKey("pool_versions.id"))
    pool_version_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    future_beacon_round: Mapped[int] = mapped_column(BigInteger)
    acceptance_cutoff: Mapped[datetime] = mapped_column(DateTime)
    resolution_deadline: Mapped[datetime] = mapped_column(DateTime)
    state: Mapped[str] = mapped_column(String(24), default="PENDING_RANDOMNESS")
    price: Mapped[int] = mapped_column(Integer)
    remaining_count: Mapped[int] = mapped_column(Integer)
    selected_gift_id: Mapped[str | None] = mapped_column(
        ForeignKey("virtual_gifts.id"), unique=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_bets_user_idempotency"),
        CheckConstraint(
            "state IN ('PENDING_RANDOMNESS', 'RESOLVING', 'COMPLETED', 'CANCELLED')",
            name="ck_bets_state",
        ),
        CheckConstraint("price > 0", name="ck_bets_price_positive"),
        CheckConstraint("remaining_count > 0", name="ck_bets_remaining_positive"),
        Index("ix_bets_user_epoch_created", "user_id", "user_epoch", "created_at"),
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_epoch: Mapped[int] = mapped_column(Integer)
    bet_id: Mapped[str | None] = mapped_column(ForeignKey("bets.id"))
    kind: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("bet_id", "kind", name="uq_ledger_entries_bet_kind"),
        CheckConstraint(
            "kind IN ('DEBIT', 'RESTORATION', 'RESET')",
            name="ck_ledger_entries_kind",
        ),
        CheckConstraint("balance_after >= 0", name="ck_ledger_entries_balance_nonnegative"),
    )


class DrawLease(Base):
    __tablename__ = "draw_leases"

    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), primary_key=True)
    bet_id: Mapped[str] = mapped_column(ForeignKey("bets.id"), unique=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class DrandProof(Base):
    __tablename__ = "drand_proofs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    bet_id: Mapped[str] = mapped_column(ForeignKey("bets.id"), unique=True)
    network: Mapped[str] = mapped_column(String(100))
    beacon_round: Mapped[int] = mapped_column("round", BigInteger)
    signature: Mapped[str] = mapped_column(Text)
    randomness: Mapped[str] = mapped_column(String(64))
    verification_result: Mapped[bool] = mapped_column(Boolean)
    response_json: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Disclosure(Base):
    __tablename__ = "disclosures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"), unique=True)
    package_json: Mapped[str] = mapped_column(Text)
    package_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
