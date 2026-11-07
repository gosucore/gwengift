# Disclosure and independent verification

A disclosed round is one immutable JSON document. It contains simulated-asset evidence only: no Telegram user ID, username, real payment, wallet, or withdrawal data.

## Obtain a package

The API publishes the package only after the round sells out or reaches its disclosure deadline with no active attempts:

```bash
curl --fail http://localhost:8000/api/rounds/ROUND_ID/disclosure \
  --output disclosure.json
```

The response is canonical JSON. Its `X-Disclosure-SHA256` header is the SHA-256 of the exact response bytes. The hash identifies the download but is not a substitute for checking its contents.

## Schema version 1

Top-level fields:

| Field | Contents |
| --- | --- |
| `schema_version` | Integer `1`; unknown versions are rejected. |
| `asset_mode` | Always `simulated`. |
| `round` | Round and collection IDs, open/close times, disclosure deadline, and disclosure time. |
| `algorithms` | Exact commitment, selection, beacon, and canonical-JSON algorithm IDs. |
| `pool_versions` | Every version in ascending order: ID, version number, commitment, complete ordered manifest, ticket price, expected value, actual RTP, operator margin, remaining count, value distribution, market snapshot reference, and creation time. |
| `market_snapshots` | Complete valuation evidence for every referenced snapshot: source names, currencies, conversion/discount rules, source payload, provenance, discrepancy, observation/expiry times, and creation time. |
| `bets` | Every final attempt binding: bet ID, demo epoch, pool reference/hash, idempotency key, future beacon round, cutoffs/deadline, state, price, remaining count, selected gift or cancellation reason, timestamps, bet-linked debit/restoration entries, and beacon proof. |
| `gifts` | Every original gift's complete attributes, latest stored estimates, final `AWARDED`/`AVAILABLE` state, and demo owner epoch when awarded. |

Each manifest gift contains `id`, `model`, `backdrop`, `symbol`, `rarity`, `number`, `player_sale_estimate`, and `replacement_cost`. Decimal values are JSON strings; timestamps are ISO 8601 UTC values without a timezone suffix, matching the backend's naive-UTC storage convention.

## Canonicalization and commitments

Both manifests and disclosure packages use UTF-8 JSON with lexicographically sorted object keys, no insignificant whitespace, and no non-finite numbers. Disclosure verification requires byte-for-byte canonical JSON, so trailing newlines and reordered keys are rejected. Manifest gifts must additionally remain ordered by stable gift ID.

For pool version `v`:

```text
commitment = SHA-256(
  "gift-pool-v1" || round_id_utf8 || decimal_version_ascii || canonical_manifest_utf8
)
```

Pool versions must be consecutive from 1. A later manifest may be unchanged after a valuation refresh or may remove exactly the gift awarded by the completed bet bound to the preceding version. It cannot add or reintroduce a gift.

The verifier recomputes, from each disclosed manifest:

```text
expected_value = mean(player_sale_estimate)
price = ceil(expected_value / 0.90)
actual_RTP = expected_value / price
operator_margin = price - mean(replacement_cost)
```

It also recomputes minimum/median/maximum estimates and counts below versus at/above the ticket price. Stored decimal aggregates are compared at their database precision (eight decimal places).

## Beacon and outcome replay

For each completed bet, the verifier locally checks the pinned drand quicknet BLS signature and `randomness = SHA-256(signature)`. It requires the proof round to equal the bet's committed future round. See [drand verification](drand-verification.md) for network constants and official vectors.

It then replays `gift-draw-v1` using the proof randomness, bet ID, pool commitment, and that pool's remaining manifest. The published encoding and 256-bit rejection-sampling algorithm are specified in [deterministic gift selection](draw-selection.md). The replayed gift must equal the disclosed outcome.

Finally, verification checks unique bet/gift/ledger IDs, one matching debit per bet, restoration only for cancelled bets, unique awards, unchanged gift attributes, final ownership epochs, and complete market-snapshot references. An unsold round cannot have a disclosure time before its deadline.

## Local verification command

Install the backend dependencies as described in the README, then run:

```bash
cd backend
.venv/bin/python -m app.verify_disclosure ./disclosure.json
```

A valid package exits 0 and prints one JSON line:

```json
{"completed_bets":4,"remaining_gifts":0,"round_id":"...","sha256":"...","valid":true}
```

An invalid schema, noncanonical document, changed statistic or manifest, invalid beacon, duplicate award, or non-replaying outcome exits 1 and prints the reason to stderr. Verification is offline and does not query a relay or read the application database. The quicknet public key and algorithm implementations are pinned in this source tree, so auditors should obtain and review that source independently rather than trusting a downloaded package to supply its own verification rules.
