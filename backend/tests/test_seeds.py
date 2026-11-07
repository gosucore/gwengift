from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Collection, Round, VirtualGift
from app.seeds import (
    SeedCatalog,
    load_seed_catalog,
    seed_demo_catalog,
)

NOW = datetime.now(UTC).replace(tzinfo=None)


def test_seed_catalog_has_ten_complete_unique_collections() -> None:
    catalog = load_seed_catalog()

    assert catalog.schema_version == 1
    assert catalog.seed_version
    assert len(catalog.collections) == 10
    for collection in catalog.collections:
        assert collection.gifts
        assert len({gift.number for gift in collection.gifts}) == len(collection.gifts)
        for gift in collection.gifts:
            assert gift.model and gift.backdrop and gift.symbol and gift.rarity


def test_seeding_is_repeatable_and_gift_ids_are_unique(db_session: Session) -> None:
    catalog = load_seed_catalog()

    first = seed_demo_catalog(db_session, catalog, now=NOW)
    second = seed_demo_catalog(db_session, catalog, now=NOW)

    assert first.collections_created == 10
    assert first.rounds_created == 10
    assert first.gifts_created == sum(len(item.gifts) for item in catalog.collections)
    assert second.collections_created == 0
    assert second.rounds_created == 0
    assert second.gifts_created == 0

    gift_ids = list(db_session.scalars(select(VirtualGift.id)).all())
    assert len(gift_ids) == first.gifts_created
    assert len(set(gift_ids)) == len(gift_ids)
    assert db_session.scalar(select(func.count()).select_from(Collection)) == 10
    assert db_session.scalar(select(func.count()).select_from(Round)) == 10


def test_new_seed_version_creates_separate_round_and_gifts(db_session: Session) -> None:
    first_catalog = load_seed_catalog()
    second_catalog = first_catalog.model_copy(update={"seed_version": "test-v2"})
    seed_demo_catalog(db_session, first_catalog, now=NOW)

    result = seed_demo_catalog(db_session, second_catalog, now=NOW)

    assert result.collections_created == 0
    assert result.rounds_created == 10
    assert result.gifts_created == 40


def test_seed_validation_rejects_duplicate_gift_numbers() -> None:
    payload = load_seed_catalog().model_dump(mode="json")
    payload["collections"][0]["gifts"][1]["number"] = 1

    with pytest.raises(ValidationError, match="unique"):
        SeedCatalog.model_validate(payload)
