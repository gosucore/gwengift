import json

import pytest
from pydantic import ValidationError

from app.services.commitments import (
    ManifestGift,
    PoolManifest,
    canonical_manifest_json,
    commit_pool_manifest,
    create_pool_commitment,
    verify_pool_commitment,
)

ROUND_ID = "round-1"
EXPECTED_COMMITMENT = "8222cad41ff6051f1fe6db6ce1f1974220607b7e57068796e4f7f8bacd27c430"
EXPECTED_MANIFEST_JSON = (
    '{"gifts":[{"backdrop":"Blue","id":"gift-a","model":"Model A","number":1,'
    '"player_sale_estimate":90,"rarity":"Common","replacement_cost":100,'
    '"symbol":"Star"},{"backdrop":"Gold","id":"gift-b","model":"Model B",'
    '"number":2,"player_sale_estimate":180,"rarity":"Rare","replacement_cost":200,'
    '"symbol":"Moon"}],"schema_version":1}'
)


def vector_gifts() -> list[ManifestGift]:
    return [
        ManifestGift(
            id="gift-a",
            model="Model A",
            backdrop="Blue",
            symbol="Star",
            rarity="Common",
            number=1,
            player_sale_estimate=90,
            replacement_cost=100,
        ),
        ManifestGift(
            id="gift-b",
            model="Model B",
            backdrop="Gold",
            symbol="Moon",
            rarity="Rare",
            number=2,
            player_sale_estimate=180,
            replacement_cost=200,
        ),
    ]


def test_known_canonical_manifest_and_commitment_vector() -> None:
    manifest = PoolManifest(gifts=vector_gifts())

    assert canonical_manifest_json(manifest) == EXPECTED_MANIFEST_JSON
    assert commit_pool_manifest(ROUND_ID, 1, manifest) == EXPECTED_COMMITMENT
    assert verify_pool_commitment(ROUND_ID, 1, EXPECTED_MANIFEST_JSON, EXPECTED_COMMITMENT)


def test_creation_sorts_by_stable_gift_id() -> None:
    manifest, manifest_json, commitment = create_pool_commitment(
        ROUND_ID, 1, reversed(vector_gifts())
    )

    assert [gift.id for gift in manifest.gifts] == ["gift-a", "gift-b"]
    assert manifest_json == EXPECTED_MANIFEST_JSON
    assert commitment == EXPECTED_COMMITMENT


def test_changed_gift_or_valuation_fails_verification() -> None:
    data = json.loads(EXPECTED_MANIFEST_JSON)
    data["gifts"][0]["model"] = "Substituted model"
    tampered_json = json.dumps(data, sort_keys=True, separators=(",", ":"))

    assert not verify_pool_commitment(ROUND_ID, 1, tampered_json, EXPECTED_COMMITMENT)

    data = json.loads(EXPECTED_MANIFEST_JSON)
    data["gifts"][0]["player_sale_estimate"] = 9000
    tampered_json = json.dumps(data, sort_keys=True, separators=(",", ":"))

    assert not verify_pool_commitment(ROUND_ID, 1, tampered_json, EXPECTED_COMMITMENT)


def test_changed_gift_order_fails_even_when_json_content_is_equivalent() -> None:
    reordered = PoolManifest(gifts=list(reversed(vector_gifts())))

    assert commit_pool_manifest(ROUND_ID, 1, reordered) != EXPECTED_COMMITMENT
    assert not verify_pool_commitment(
        ROUND_ID, 1, canonical_manifest_json(reordered), EXPECTED_COMMITMENT
    )


@pytest.mark.parametrize(
    ("round_id", "version"),
    [("round-2", 1), (ROUND_ID, 2)],
)
def test_changed_round_id_or_version_fails_verification(round_id: str, version: int) -> None:
    assert not verify_pool_commitment(
        round_id, version, EXPECTED_MANIFEST_JSON, EXPECTED_COMMITMENT
    )


def test_noncanonical_or_duplicate_manifest_is_rejected() -> None:
    pretty_json = json.dumps(json.loads(EXPECTED_MANIFEST_JSON), indent=2)
    assert not verify_pool_commitment(ROUND_ID, 1, pretty_json, EXPECTED_COMMITMENT)

    duplicate_data = json.loads(EXPECTED_MANIFEST_JSON)
    duplicate_data["gifts"].append(duplicate_data["gifts"][0])
    duplicate_json = json.dumps(duplicate_data, sort_keys=True, separators=(",", ":"))
    assert not verify_pool_commitment(ROUND_ID, 1, duplicate_json, EXPECTED_COMMITMENT)


def test_duplicate_gift_ids_cannot_create_a_manifest() -> None:
    with pytest.raises(ValidationError, match="gift IDs must be unique"):
        PoolManifest(gifts=[vector_gifts()[0], vector_gifts()[0]])
