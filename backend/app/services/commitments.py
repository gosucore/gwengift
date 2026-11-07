import hashlib
import hmac
import json
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models import VirtualGift

POOL_COMMITMENT_DOMAIN = b"gift-pool-v1"
POOL_MANIFEST_SCHEMA_VERSION: Literal[1] = 1


class ManifestGift(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, strict=True)

    id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    backdrop: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    rarity: str = Field(min_length=1)
    number: int = Field(ge=0)
    player_sale_estimate: int = Field(ge=0)
    replacement_cost: int = Field(ge=0)


class PoolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = POOL_MANIFEST_SCHEMA_VERSION
    gifts: list[ManifestGift] = Field(min_length=1)

    @model_validator(mode="after")
    def gift_ids_are_unique(self) -> "PoolManifest":
        ids = [gift.id for gift in self.gifts]
        if len(ids) != len(set(ids)):
            raise ValueError("Manifest gift IDs must be unique")
        return self


def build_pool_manifest(round_id: str, gifts: Iterable[VirtualGift | ManifestGift]) -> PoolManifest:
    entries: list[ManifestGift] = []
    for gift in gifts:
        if isinstance(gift, VirtualGift) and gift.round_id != round_id:
            raise ValueError("Every manifest gift must belong to the committed round")
        entries.append(
            gift if isinstance(gift, ManifestGift) else ManifestGift.model_validate(gift)
        )
    entries.sort(key=lambda gift: gift.id)
    return PoolManifest(gifts=entries)


def canonical_manifest_json(manifest: PoolManifest) -> str:
    """Serialize without insignificant whitespace; preserve the committed gift order."""
    return json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def commit_pool_manifest(round_id: str, version: int, manifest: PoolManifest) -> str:
    if not round_id or version < 1:
        raise ValueError("A round ID and positive pool version are required")
    payload = canonical_manifest_json(manifest).encode("utf-8")
    preimage = (
        POOL_COMMITMENT_DOMAIN + round_id.encode("utf-8") + str(version).encode("ascii") + payload
    )
    return hashlib.sha256(preimage).hexdigest()


def create_pool_commitment(
    round_id: str, version: int, gifts: Iterable[VirtualGift | ManifestGift]
) -> tuple[PoolManifest, str, str]:
    manifest = build_pool_manifest(round_id, gifts)
    manifest_json = canonical_manifest_json(manifest)
    return manifest, manifest_json, commit_pool_manifest(round_id, version, manifest)


def verify_pool_commitment(
    round_id: str, version: int, manifest_json: str, expected_commitment: str
) -> bool:
    """Require canonical encoding and ID order, not merely equivalent JSON content."""
    try:
        manifest = PoolManifest.model_validate_json(manifest_json)
    except (ValidationError, ValueError):
        return False
    if [gift.id for gift in manifest.gifts] != sorted(gift.id for gift in manifest.gifts):
        return False
    if canonical_manifest_json(manifest) != manifest_json:
        return False
    actual = commit_pool_manifest(round_id, version, manifest)
    return hmac.compare_digest(actual, expected_commitment)
