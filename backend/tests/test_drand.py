from typing import TypedDict

import pytest

from app.services.drand import (
    QUICKNET,
    beacon_message,
    derive_randomness,
    verify_quicknet_beacon,
)


class Vector(TypedDict):
    round: int
    signature: str
    randomness: str


VECTORS: list[Vector] = [
    {
        "round": 1,
        "signature": (
            "b55e7cb2d5c613ee0b2e28d6750aabbb78c39dcc96bd9d38c2c2e12198df95571d"
            "e8e8e402a0cc48871c7089a2b3af4b"
        ),
        "randomness": "1466a6cd24e327188770752f6134001c64d6efcc590ccc26b721611ad96f165a",
    },
    {
        "round": 2,
        "signature": (
            "b6b6a585449b66eb12e875b64fcbab3799861a00e4dbf092d99e969a5eac57dd3f"
            "798acf61e705fe4f093db926626807"
        ),
        "randomness": "5782d6987841c654515a0e72b2d1ebb4e741234042c37cb19608ae50d93fb60c",
    },
]


@pytest.mark.parametrize("vector", VECTORS)
def test_official_quicknet_vectors_pass(vector: Vector) -> None:
    assert verify_quicknet_beacon(vector["round"], vector["signature"], vector["randomness"])
    assert derive_randomness(bytes.fromhex(vector["signature"])).hex() == vector["randomness"]


def test_quicknet_metadata_matches_selected_official_network() -> None:
    assert QUICKNET.beacon_id == "quicknet"
    assert QUICKNET.chain_hash == (
        "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
    )
    assert QUICKNET.scheme == "bls-unchained-g1-rfc9380"
    assert QUICKNET.period_seconds == 3
    assert QUICKNET.genesis_time == 1692803367
    assert len(bytes.fromhex(QUICKNET.public_key)) == 96


def test_altered_round_fails() -> None:
    vector = VECTORS[0]

    assert not verify_quicknet_beacon(2, vector["signature"], vector["randomness"])


def test_altered_signature_fails_even_with_internally_consistent_randomness() -> None:
    original = VECTORS[0]
    altered = VECTORS[1]

    assert not verify_quicknet_beacon(
        original["round"], altered["signature"], altered["randomness"]
    )


def test_altered_public_key_fails() -> None:
    vector = VECTORS[0]
    altered_key = ("0" if QUICKNET.public_key[0] != "0" else "1") + QUICKNET.public_key[1:]

    assert not verify_quicknet_beacon(
        vector["round"],
        vector["signature"],
        vector["randomness"],
        public_key_hex=altered_key,
    )


def test_altered_derived_randomness_fails() -> None:
    vector = VECTORS[0]
    altered_randomness = ("0" if vector["randomness"][0] != "0" else "1") + str(
        vector["randomness"]
    )[1:]

    assert not verify_quicknet_beacon(vector["round"], vector["signature"], altered_randomness)


@pytest.mark.parametrize(
    ("round_number", "signature", "randomness"),
    [
        (-1, VECTORS[0]["signature"], VECTORS[0]["randomness"]),
        (2**64, VECTORS[0]["signature"], VECTORS[0]["randomness"]),
        (1, "not-hex", VECTORS[0]["randomness"]),
        (1, "00", VECTORS[0]["randomness"]),
        (1, VECTORS[0]["signature"], "00"),
    ],
)
def test_malformed_or_out_of_range_inputs_fail(
    round_number: int, signature: str, randomness: str
) -> None:
    assert not verify_quicknet_beacon(round_number, signature, randomness)


def test_signed_message_is_sha256_of_big_endian_uint64_round() -> None:
    assert beacon_message(1).hex() == (
        "cd2662154e6d76b2b2b92e70c0cac3ccf534f9b74eb5b89819ec509083d00a50"
    )
