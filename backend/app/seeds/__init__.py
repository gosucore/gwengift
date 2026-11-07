import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.models import Collection, Round, VirtualGift, utc_now

DEFAULT_SEED_PATH = Path(__file__).with_name("demo_pools_v1.json")


class SeedGift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    model: str = Field(min_length=1, max_length=100)
    backdrop: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=100)
    rarity: str = Field(min_length=1, max_length=100)
    player_sale_estimate: int = Field(ge=0)
    replacement_cost: int = Field(ge=0)


class SeedCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9-]+$", max_length=64)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    gifts: list[SeedGift] = Field(min_length=1)

    @field_validator("gifts")
    @classmethod
    def gift_numbers_are_unique(cls, gifts: list[SeedGift]) -> list[SeedGift]:
        numbers = [gift.number for gift in gifts]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Gift numbers must be unique within a collection")
        return gifts


class SeedCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1, le=1)
    seed_version: str = Field(min_length=1)
    round_duration_hours: int = Field(gt=0)
    collections: list[SeedCollection] = Field(min_length=10, max_length=10)

    @field_validator("collections")
    @classmethod
    def collection_ids_are_unique(cls, collections: list[SeedCollection]) -> list[SeedCollection]:
        ids = [collection.id for collection in collections]
        if len(ids) != len(set(ids)):
            raise ValueError("Collection IDs must be unique")
        return collections


@dataclass(frozen=True)
class SeedResult:
    collections_created: int
    rounds_created: int
    gifts_created: int


def load_seed_catalog(path: Path = DEFAULT_SEED_PATH) -> SeedCatalog:
    return SeedCatalog.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _seed_id(seed_version: str, collection_id: str, kind: str, number: int | None = None) -> str:
    suffix = f"/{number}" if number is not None else ""
    name = f"https://gwengift.invalid/seed/{seed_version}/{collection_id}/{kind}{suffix}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def seed_demo_catalog(
    session: Session,
    catalog: SeedCatalog | None = None,
    *,
    now: datetime | None = None,
) -> SeedResult:
    seed = load_seed_catalog() if catalog is None else catalog
    created_at = utc_now() if now is None else now
    result = {"collections_created": 0, "rounds_created": 0, "gifts_created": 0}

    with session.begin():
        for item in seed.collections:
            collection = session.get(Collection, item.id)
            if collection is None:
                collection = Collection(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    status="PAUSED",
                )
                session.add(collection)
                session.flush()
                result["collections_created"] += 1

            round_id = _seed_id(seed.seed_version, item.id, "round")
            if session.get(Round, round_id) is None:
                session.add(
                    Round(
                        id=round_id,
                        collection_id=item.id,
                        status="DRAFT",
                        opens_at=created_at,
                        closes_at=created_at + timedelta(hours=seed.round_duration_hours),
                        disclosure_deadline=created_at + timedelta(hours=seed.round_duration_hours),
                    )
                )
                session.flush()
                result["rounds_created"] += 1

            for gift in item.gifts:
                gift_id = _seed_id(seed.seed_version, item.id, "gift", gift.number)
                if session.get(VirtualGift, gift_id) is not None:
                    continue
                session.add(
                    VirtualGift(
                        id=gift_id,
                        collection_id=item.id,
                        round_id=round_id,
                        model=gift.model,
                        backdrop=gift.backdrop,
                        symbol=gift.symbol,
                        rarity=gift.rarity,
                        number=gift.number,
                        player_sale_estimate=gift.player_sale_estimate,
                        replacement_cost=gift.replacement_cost,
                        lifecycle="AVAILABLE",
                    )
                )
                session.flush()
                result["gifts_created"] += 1

    return SeedResult(**result)


def main() -> None:
    from app.db import SessionLocal

    with SessionLocal() as session:
        result = seed_demo_catalog(session)
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
