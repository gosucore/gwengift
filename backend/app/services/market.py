import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Collection, MarketSnapshot, VirtualGift, utc_now

TG_GIFTS_ATTRIBUTION = "Data: TG Gifts (https://tggifts.com)"
TG_GIFTS_LICENSE = "https://creativecommons.org/licenses/by/4.0/"


class MarketDataError(ValueError):
    pass


class ManualGiftFloor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    floor_stars: int = Field(gt=0)
    evidence_url: AnyHttpUrl


class ManualStarsFloor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1, le=1)
    collection_id: str
    observed_at: datetime
    liquidity_discount: Decimal = Field(ge=0, le=1)
    gifts: list[ManualGiftFloor] = Field(min_length=1)

    @field_validator("gifts")
    @classmethod
    def unique_gift_numbers(cls, gifts: list[ManualGiftFloor]) -> list[ManualGiftFloor]:
        numbers = [gift.number for gift in gifts]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Manual floor entries must have unique gift numbers")
        return gifts


class TGDay(BaseModel):
    day: date
    floor_gram: Decimal = Field(gt=0)
    recent_sales: int = Field(ge=0)
    price_kind: Literal["b", "t"] = "b"

    @model_validator(mode="before")
    @classmethod
    def parse_daily_array(cls, value: object) -> object:
        if isinstance(value, list) and 2 <= len(value) <= 4:
            keys = ("day", "floor_gram", "recent_sales", "price_kind")
            return dict(zip(keys, value, strict=False))
        return value


class TGCollection(BaseModel):
    name: str = Field(min_length=1)
    days: list[TGDay] = Field(min_length=1)


class DailyDocument(BaseModel):
    source: str
    license: str
    generated: datetime
    collections: dict[str, TGCollection]


class CacheEnvelope(BaseModel):
    fetched_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class CachedDailyData:
    payload: dict[str, Any]
    fetched_at: datetime
    from_cache: bool


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pause_collection(session: Session, collection_id: str) -> None:
    with session.begin():
        collection = session.get(Collection, collection_id)
        if collection is not None:
            collection.status = "PAUSED"


def import_market_snapshot(
    session: Session,
    collection_id: str,
    manual_payload: dict[str, Any],
    external_payload: dict[str, Any],
    *,
    stars_per_gram: Decimal,
    settings: Settings,
    now: datetime | None = None,
    external_cache_used: bool = False,
) -> MarketSnapshot:
    current_time = _naive_utc(now or utc_now())
    try:
        manual = ManualStarsFloor.model_validate(manual_payload)
        external = DailyDocument.model_validate(external_payload)
        if manual.collection_id != collection_id:
            raise MarketDataError("Manual snapshot collection does not match")
        if stars_per_gram <= 0:
            raise MarketDataError("GRAM-to-Stars conversion must be positive")
        if "CC BY 4.0" not in external.license or "TG Gifts" not in external.source:
            raise MarketDataError("TG Gifts attribution or license is missing")
        if collection_id not in external.collections:
            raise MarketDataError("External collection data is missing")

        observed_at = _naive_utc(manual.observed_at)
        generated_at = _naive_utc(external.generated)
        latest = max(external.collections[collection_id].days, key=lambda point: point.day)
        external_observed_at = datetime.combine(latest.day, time.min)
        manual_expiry = observed_at + timedelta(hours=settings.manual_data_max_age_hours)
        external_expiry = external_observed_at + timedelta(
            hours=settings.external_data_max_age_hours
        )
        if current_time >= manual_expiry or current_time >= external_expiry:
            raise MarketDataError("Market data is stale")
        if (
            observed_at > current_time + timedelta(minutes=5)
            or generated_at > current_time + timedelta(minutes=5)
            or external_observed_at > current_time + timedelta(minutes=5)
        ):
            raise MarketDataError("Market data timestamps are from the future")
        if current_time >= generated_at + timedelta(hours=settings.external_data_max_age_hours):
            raise MarketDataError("External dataset generation time is stale")

        primary_floor = min(gift.floor_stars for gift in manual.gifts)
        external_stars = latest.floor_gram * stars_per_gram
        discrepancy = abs(Decimal(primary_floor) - external_stars) / max(
            Decimal(primary_floor), external_stars
        )
        discrepancy_found = discrepancy > settings.market_discrepancy_threshold
        pause_for_discrepancy = discrepancy_found and settings.market_discrepancy_action == "pause"
        liquidity_discount = manual.liquidity_discount
        if discrepancy_found and settings.market_discrepancy_action == "discount":
            liquidity_discount = min(
                Decimal("1"), liquidity_discount + settings.discrepancy_liquidity_discount
            )

        external_evidence = {
            "source": external.source,
            "license": external.license,
            "license_url": TG_GIFTS_LICENSE,
            "dataset_url": settings.tg_gifts_daily_url,
            "generated_at": generated_at.isoformat(),
            "day": latest.day.isoformat(),
            "floor_gram": str(latest.floor_gram),
            "recent_sales": latest.recent_sales,
            "price_kind": latest.price_kind,
            "cache_used": external_cache_used,
        }
        provenance = {
            "manual": manual.model_dump(mode="json"),
            "external": external_evidence,
            "discrepancy": str(discrepancy),
            "discrepancy_threshold": str(settings.market_discrepancy_threshold),
            "discrepancy_action": settings.market_discrepancy_action,
            "availability": "paused" if pause_for_discrepancy else "open",
        }

        with session.begin():
            expected_numbers = set(
                session.scalars(
                    select(VirtualGift.number).where(VirtualGift.collection_id == collection_id)
                ).all()
            )
            if {gift.number for gift in manual.gifts} != expected_numbers:
                raise MarketDataError("Manual snapshot does not cover the complete pool")
            collection = session.get(Collection, collection_id)
            if collection is None:
                raise MarketDataError("Collection does not exist")

            snapshot = MarketSnapshot(
                collection_id=collection_id,
                primary_source="manual Stars-floor evidence",
                external_source=TG_GIFTS_ATTRIBUTION,
                source_currency="STARS; external cross-check GRAM",
                conversion_rule=_canonical_json(
                    {
                        "formula": "external_stars = floor_gram * stars_per_gram",
                        "stars_per_gram": str(stars_per_gram),
                    }
                ),
                liquidity_discount=liquidity_discount,
                source_payload_json=_canonical_json(
                    {"manual": manual.model_dump(mode="json"), "external": external_evidence}
                ),
                provenance_json=_canonical_json(provenance),
                cross_check_discrepancy=discrepancy,
                observed_at=observed_at,
                expires_at=min(manual_expiry, external_expiry),
            )
            session.add(snapshot)
            collection.status = "PAUSED" if pause_for_discrepancy else "OPEN"
            session.flush()
            return snapshot
    except (MarketDataError, ValidationError) as exc:
        _pause_collection(session, collection_id)
        raise MarketDataError(str(exc)) from exc


def fetch_tg_gifts_daily(
    *,
    url: str,
    cache_path: Path,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
    max_cache_age: timedelta = timedelta(hours=6),
) -> CachedDailyData:
    current_time = _naive_utc(now or utc_now())
    try:
        with httpx.Client(transport=transport, timeout=10) as client:
            response = client.get(url)
            response.raise_for_status()
            payload: Any = response.json()
        if not isinstance(payload, dict):
            raise MarketDataError("TG Gifts response must be a JSON object")
        DailyDocument.model_validate(payload)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        envelope = CacheEnvelope(fetched_at=current_time, payload=payload)
        temporary_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary_path.write_text(envelope.model_dump_json(), encoding="utf-8")
        temporary_path.replace(cache_path)
        return CachedDailyData(payload, current_time, from_cache=False)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        try:
            envelope = CacheEnvelope.model_validate_json(cache_path.read_text(encoding="utf-8"))
            DailyDocument.model_validate(envelope.payload)
            fetched_at = _naive_utc(envelope.fetched_at)
            age = current_time - fetched_at
            if timedelta(0) <= age <= max_cache_age:
                return CachedDailyData(envelope.payload, fetched_at, from_cache=True)
        except (OSError, ValueError):
            pass
        raise MarketDataError("TG Gifts download failed and no fresh cache is available") from exc
