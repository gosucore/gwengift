import hashlib
from dataclasses import dataclass

from app.services.commitments import PoolManifest

DRAW_DOMAIN = b"gift-draw-v1"
UINT256_SPACE = 1 << 256


@dataclass(frozen=True)
class DrawSelection:
    gift_id: str
    index: int
    counter: int
    candidate_hex: str


def rejection_limit(remaining_count: int) -> int:
    if remaining_count < 1:
        raise ValueError("Remaining pool must not be empty")
    return (UINT256_SPACE // remaining_count) * remaining_count


def map_unbiased_candidate(candidate: int, remaining_count: int) -> int | None:
    """Return None for rejected candidates; otherwise map into the remaining pool."""
    limit = rejection_limit(remaining_count)
    if not 0 <= candidate < UINT256_SPACE:
        raise ValueError("Candidate must be an unsigned 256-bit integer")
    if candidate >= limit:
        return None
    return candidate % remaining_count


def draw_candidate_digest(
    drand_randomness: bytes,
    bet_id: str,
    pool_version_hash: str,
    counter: int,
) -> bytes:
    if len(drand_randomness) != 32:
        raise ValueError("Verified drand randomness must contain 32 bytes")
    if not bet_id:
        raise ValueError("Bet ID is required")
    try:
        hash_bytes = bytes.fromhex(pool_version_hash)
    except ValueError as exc:
        raise ValueError("Pool version hash must be hexadecimal") from exc
    if len(hash_bytes) != 32:
        raise ValueError("Pool version hash must contain 32 bytes")
    if not 0 <= counter <= 2**64 - 1:
        raise ValueError("Draw counter must fit in an unsigned 64-bit integer")
    preimage = (
        DRAW_DOMAIN
        + drand_randomness
        + bet_id.encode("utf-8")
        + pool_version_hash.encode("ascii")
        + counter.to_bytes(8, "big")
    )
    return hashlib.sha256(preimage).digest()


def select_gift(
    *,
    drand_randomness_hex: str,
    bet_id: str,
    pool_version_hash: str,
    remaining_manifest: PoolManifest,
) -> DrawSelection:
    try:
        randomness = bytes.fromhex(drand_randomness_hex)
    except ValueError as exc:
        raise ValueError("Drand randomness must be hexadecimal") from exc
    gift_ids = [gift.id for gift in remaining_manifest.gifts]
    if gift_ids != sorted(gift_ids):
        raise ValueError("Remaining manifest must use canonical gift-ID order")

    counter = 0
    while counter <= 2**64 - 1:
        digest = draw_candidate_digest(randomness, bet_id, pool_version_hash, counter)
        candidate = int.from_bytes(digest, "big")
        index = map_unbiased_candidate(candidate, len(remaining_manifest.gifts))
        if index is not None:
            return DrawSelection(
                gift_id=remaining_manifest.gifts[index].id,
                index=index,
                counter=counter,
                candidate_hex=digest.hex(),
            )
        counter += 1
    raise RuntimeError("Exhausted the deterministic draw counter space")
