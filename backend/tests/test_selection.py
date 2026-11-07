from collections import Counter

import pytest

from app.services.commitments import ManifestGift, PoolManifest, commit_pool_manifest
from app.services.selection import (
    UINT256_SPACE,
    draw_candidate_digest,
    map_unbiased_candidate,
    rejection_limit,
    select_gift,
)

RANDOMNESS_1 = "1466a6cd24e327188770752f6134001c64d6efcc590ccc26b721611ad96f165a"
RANDOMNESS_2 = "5782d6987841c654515a0e72b2d1ebb4e741234042c37cb19608ae50d93fb60c"
POOL_HASH_1 = "8222cad41ff6051f1fe6db6ce1f1974220607b7e57068796e4f7f8bacd27c430"
POOL_HASH_2 = "b45208f06f88c2e723aa6ebc07c611ee4a51442a762fc7384ff94c0afa5ed071"


def gift(letter: str) -> ManifestGift:
    upper = letter.upper()
    values = {"a": (90, 100), "b": (180, 200), "c": (270, 300)}
    sale, replacement = values[letter]
    return ManifestGift(
        id=f"gift-{letter}",
        model=f"Model {upper}",
        backdrop={"a": "Blue", "b": "Gold", "c": "Red"}[letter],
        symbol={"a": "Star", "b": "Moon", "c": "Sun"}[letter],
        rarity={"a": "Common", "b": "Rare", "c": "Epic"}[letter],
        number=ord(letter) - ord("a") + 1,
        player_sale_estimate=sale,
        replacement_cost=replacement,
    )


def manifest(count: int) -> PoolManifest:
    return PoolManifest(gifts=[gift(chr(ord("a") + index)) for index in range(count)])


def test_published_two_gift_audit_vector() -> None:
    pool = manifest(2)
    assert commit_pool_manifest("round-1", 1, pool) == POOL_HASH_1

    digest = draw_candidate_digest(bytes.fromhex(RANDOMNESS_1), "bet-0001", POOL_HASH_1, 0)
    selection = select_gift(
        drand_randomness_hex=RANDOMNESS_1,
        bet_id="bet-0001",
        pool_version_hash=POOL_HASH_1,
        remaining_manifest=pool,
    )

    assert digest.hex() == "25679154e32fe69bdf6cfb5ec42541c3b710561a8251ecbfabb0e650b5a2dd46"
    assert selection.gift_id == "gift-a"
    assert selection.index == 0
    assert selection.counter == 0
    assert selection.candidate_hex == digest.hex()


def test_published_three_gift_audit_vector() -> None:
    pool = manifest(3)
    assert commit_pool_manifest("round-1", 2, pool) == POOL_HASH_2

    digest = draw_candidate_digest(bytes.fromhex(RANDOMNESS_2), "bet-0003", POOL_HASH_2, 0)
    selection = select_gift(
        drand_randomness_hex=RANDOMNESS_2,
        bet_id="bet-0003",
        pool_version_hash=POOL_HASH_2,
        remaining_manifest=pool,
    )

    assert digest.hex() == "011a46d3e1002f972312658cb1751c86aaf4ebfc03451c117e3d8cb5a976530b"
    assert selection.gift_id == "gift-b"
    assert selection.index == 1
    assert selection.counter == 0


def test_replay_returns_identical_gift_and_trace() -> None:
    first = select_gift(
        drand_randomness_hex=RANDOMNESS_1,
        bet_id="bet-replay",
        pool_version_hash=POOL_HASH_1,
        remaining_manifest=manifest(2),
    )
    second = select_gift(
        drand_randomness_hex=RANDOMNESS_1,
        bet_id="bet-replay",
        pool_version_hash=POOL_HASH_1,
        remaining_manifest=manifest(2),
    )

    assert first == second


def test_bet_binding_changes_candidate_digest() -> None:
    randomness = bytes.fromhex(RANDOMNESS_1)

    first = draw_candidate_digest(randomness, "bet-a", POOL_HASH_1, 0)
    second = draw_candidate_digest(randomness, "bet-b", POOL_HASH_1, 0)

    assert first != second


def test_rejection_sampling_boundaries() -> None:
    assert rejection_limit(1) == UINT256_SPACE
    assert rejection_limit(2) == UINT256_SPACE
    assert rejection_limit(3) == UINT256_SPACE - 1
    assert map_unbiased_candidate(0, 3) == 0
    assert map_unbiased_candidate(UINT256_SPACE - 2, 3) is not None
    assert map_unbiased_candidate(UINT256_SPACE - 1, 3) is None
    assert map_unbiased_candidate(UINT256_SPACE - 1, 2) == 1


def test_rejected_candidate_increments_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import selection

    real_digest = selection.draw_candidate_digest
    calls: list[int] = []

    def first_rejected(randomness: bytes, bet_id: str, pool_hash: str, counter: int) -> bytes:
        calls.append(counter)
        return b"\xff" * 32 if counter == 0 else real_digest(randomness, bet_id, pool_hash, counter)

    monkeypatch.setattr(selection, "draw_candidate_digest", first_rejected)

    result = selection.select_gift(
        drand_randomness_hex=RANDOMNESS_1,
        bet_id="bet-rejection",
        pool_version_hash=POOL_HASH_2,
        remaining_manifest=manifest(3),
    )

    assert calls == [0, 1]
    assert result.counter == 1


def test_deterministic_mapping_covers_pool_without_large_count_skew() -> None:
    counts: Counter[int] = Counter()
    for number in range(2_000):
        digest = draw_candidate_digest(
            bytes.fromhex(RANDOMNESS_1), f"bet-statistical-{number}", POOL_HASH_1, 0
        )
        index = map_unbiased_candidate(int.from_bytes(digest, "big"), 4)
        assert index is not None
        counts[index] += 1

    assert set(counts) == {0, 1, 2, 3}
    assert all(400 <= count <= 600 for count in counts.values())


def test_invalid_or_unordered_pools_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive|not be empty"):
        rejection_limit(0)
    with pytest.raises(ValueError, match="canonical gift-ID order"):
        select_gift(
            drand_randomness_hex=RANDOMNESS_1,
            bet_id="bet-order",
            pool_version_hash=POOL_HASH_1,
            remaining_manifest=PoolManifest(gifts=[gift("b"), gift("a")]),
        )
    with pytest.raises(ValueError, match="32 bytes"):
        select_gift(
            drand_randomness_hex="00",
            bet_id="bet-short",
            pool_version_hash=POOL_HASH_1,
            remaining_manifest=manifest(2),
        )
