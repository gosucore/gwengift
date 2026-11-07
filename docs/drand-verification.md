# drand verification protocol

GwenGift uses the public **quicknet** drand network. Relay responses are untrusted until verified locally; an unavailable or invalid beacon must never be replaced with local randomness.

## Selected network

- Chain hash: `52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971`
- Beacon ID: `quicknet`
- Scheme: `bls-unchained-g1-rfc9380`
- Period: 3 seconds
- Genesis Unix time: `1692803367`
- Public key: the 96-byte BLS12-381 G2 value pinned in `backend/app/services/drand.py`
- Signature: a 48-byte BLS12-381 G1 value

The unchained signed message is `SHA-256(round_number)` where the round is encoded as an unsigned 64-bit big-endian integer. Hash-to-curve uses `BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_`. Verification checks the pairing equation `e(signature, G2_generator) == e(H(message), public_key)` through the maintained `blspy` binding. Derived randomness is `SHA-256(signature_bytes)`.

## Official vectors

The fixed vectors in `backend/tests/test_drand.py` are quicknet rounds 1 and 2 from the official League of Entropy API:

- <https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/1>
- <https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/2>

Network metadata was cross-checked against the official `/info` endpoint. The scheme and digest rules come from the official drand implementation:

- <https://docs.drand.love/developer/>
- <https://github.com/drand/drand/blob/master/crypto/schemes.go>
- <https://github.com/drand/drand/blob/master/crypto/schemes_test.go>

Run the offline verification tests:

```bash
cd backend
.venv/bin/python -m pytest tests/test_drand.py -q
```

The tests require no relay access. They accept both official vectors and reject changed rounds, signatures, public keys, derived randomness, malformed values, and out-of-range rounds.

## Relay adapter

`backend/app/services/drand_adapter.py` pins the complete network metadata and supports the official `api.drand.sh`, `api2.drand.sh`, `api3.drand.sh`, and Cloudflare relays. Round availability is `genesis_time + (round - 1) * period`; future-round selection publishes an acceptance cutoff before that availability time. The adapter makes no request for an unresolved round. It tries relays in order, but returns a beacon only after the round, BLS signature, and derived randomness all pass local verification. HTTP errors, malformed responses, wrong network metadata, and invalid proofs are never accepted as randomness.
