import hashlib
import hmac
from dataclasses import dataclass

from blspy import G1Element, G2Element

QUICKNET_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
QUICKNET_PUBLIC_KEY = (
    "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c8c4b450b6a0a6c3"
    "ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5a6"
    "e9c76a4bc09e76eae8991ef5ece45a"
)
QUICKNET_SCHEME = "bls-unchained-g1-rfc9380"
G1_BASIC_DST = b"BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"


@dataclass(frozen=True)
class DrandNetwork:
    beacon_id: str
    chain_hash: str
    public_key: str
    scheme: str
    period_seconds: int
    genesis_time: int


QUICKNET = DrandNetwork(
    beacon_id="quicknet",
    chain_hash=QUICKNET_CHAIN_HASH,
    public_key=QUICKNET_PUBLIC_KEY,
    scheme=QUICKNET_SCHEME,
    period_seconds=3,
    genesis_time=1692803367,
)


def beacon_message(round_number: int) -> bytes:
    if not 0 <= round_number <= 2**64 - 1:
        raise ValueError("Drand round must fit in an unsigned 64-bit integer")
    return hashlib.sha256(round_number.to_bytes(8, "big")).digest()


def derive_randomness(signature: bytes) -> bytes:
    return hashlib.sha256(signature).digest()


def verify_quicknet_beacon(
    round_number: int,
    signature_hex: str,
    randomness_hex: str,
    *,
    public_key_hex: str = QUICKNET_PUBLIC_KEY,
) -> bool:
    """Verify quicknet's unchained G1 signature and SHA-256 randomness locally."""
    try:
        message = beacon_message(round_number)
        signature_bytes = bytes.fromhex(signature_hex)
        randomness = bytes.fromhex(randomness_hex)
        public_key_bytes = bytes.fromhex(public_key_hex)
        if (
            len(signature_bytes) != 48
            or len(randomness) != 32
            or len(public_key_bytes) != 96
            or not hmac.compare_digest(derive_randomness(signature_bytes), randomness)
        ):
            return False
        signature = G1Element.from_bytes(signature_bytes)
        public_key = G2Element.from_bytes(public_key_bytes)
        hashed_message = G1Element.from_message(message, G1_BASIC_DST)
        # e(signature, G2 generator) == e(H(round), network public key)
        return bool(signature.pair(G2Element.generator()) == hashed_message.pair(public_key))
    except (ValueError, TypeError, RuntimeError, OverflowError):
        return False
