# Design

## Context

See `proposal.md` for motivation and the three capability specs for observable requirements. The repository is greenfield, so there are no compatibility constraints or existing application components to preserve.

The system is a demo, but its hidden pools, deterministic outcomes, and balance mutations still require server-side authority and auditable persistence. Real market data is read-only reference data; no real asset is held or transferred.

## Goals / Non-Goals

**Goals:**

- A single deployable application with a React Telegram Mini App and a FastAPI API.
- Reproducible pool pricing, draw selection, and post-round disclosure.
- Atomic demo-balance and gift-state transitions, including retries and backend recovery.
- Verified drand randomness with no trusted-relay shortcut.
- Local development and single-container demo deployment without paid infrastructure.

**Non-Goals:**

- High availability, horizontal scaling, or multi-writer database support.
- A public operator/admin interface; seeding and market imports are internal jobs.
- Real payment, wallet, custodial, blockchain, crafting, or LLM integrations.
- Real-time market pricing or a guarantee that an estimated floor is executable.

## Decisions

### 1. Use a small full-stack monolith

Use `frontend/` for React + TypeScript + Vite and `backend/` for FastAPI + SQLAlchemy + Alembic. In production, FastAPI serves the compiled frontend and API from one origin; Vite proxies API requests during development.

This avoids CORS and multi-service deployment complexity. A separate microservice architecture is unnecessary at demo scale. Generate the frontend API client from FastAPI's OpenAPI schema instead of maintaining duplicate request/response types in Python and TypeScript.

### 2. Treat Telegram launch data as credentials

The frontend sends Telegram `initData` to the backend. The backend validates its HMAC and freshness using the bot token and derives the user identity from validated data; client-supplied user IDs are never trusted.

An explicit development-only identity adapter supports local browser and Playwright testing. It is disabled in production configuration.

### 3. Use append-only domain records plus a per-user demo epoch

The principal tables are:

- `users`: Telegram identity, active demo epoch, current balance.
- `collections`: ten configured gift collections.
- `rounds`: collection, status, opening/disclosure deadlines, disclosure state.
- `virtual_gifts`: unique gift identity, complete attributes, round, lifecycle state.
- `pool_versions`: ordered hidden manifest, commitment, price, aggregate statistics, valuation snapshot.
- `market_snapshots`: source payload, provenance, observation time, currency, conversion and discount rules.
- `bets`: user, pool version, idempotency key, future beacon round, cutoff, state, selected gift.
- `ledger_entries`: immutable debit, cancellation/restoration, and reset entries.
- `drand_proofs`: network, round, signature, randomness, verification result.
- `disclosures`: complete disclosed package and package hash.

A demo reset increments the user's epoch and creates a fresh starting-balance ledger entry. Old inventory and history disappear from the user's active view, while global round disclosures and audit evidence remain intact.

### 4. Serialize draws per collection for the MVP

At attempt creation, acquire a per-collection draw lease and hold it until the bet resolves or cancels. Only one pending bet per collection can bind to the current pool version; requests that arrive during another draw receive a retryable pending state.

This prevents two bets from binding to the same remaining manifest and selecting the same gift. Batch permutation draws would support more concurrency but add substantial protocol and audit complexity. Per-collection serialization is acceptable for a portfolio demo and does not prevent concurrent play in different collections.

The lease is persisted and recoverable. A backend restart resumes the stored bet from its immutable binding rather than creating a new draw.

### 5. Use explicit bet and round state machines

Bet states:

```text
PENDING_RANDOMNESS --> RESOLVING --> COMPLETED
        |                  |
        +------------------+--> CANCELLED (demo debit restored)
```

Round states:

```text
DRAFT --> OPEN --> CLOSED --> DISCLOSED
```

Every transition is idempotent and constrained by current state. Unique constraints enforce one successful debit per bet, one award per gift, and one selected gift per bet. Ledger and gift changes use `BEGIN IMMEDIATE` SQLite transactions; the initial deployment runs one API/worker writer.

### 6. Bind the bet before the future beacon resolves

On attempt creation:

1. Validate balance, collection availability, valuation freshness, and pool version.
2. Select a drand round beyond a safety cutoff derived from the network's published genesis and period.
3. Persist the bet UUID, pool-version hash, remaining count, exact price, target round, cutoff, and debit in one transaction.
4. Return the pending bet to the user.

A late attempt is rejected before debit or cancelled and restored without operator discretion. The target beacon round and acceptance rule are fixed before its randomness exists.

### 7. Verify drand through an isolated adapter

The randomness adapter handles network metadata, relay retrieval, signature verification, and derivation `randomness = SHA-256(signature)`. Multiple public relays may supply responses, but every response must match the configured network and pass local verification.

The first implementation task is a verification spike against official vectors for the selected low-latency network, including its chained/unchained and G1/G2 scheme details. Use a maintained Python BLS binding; do not implement pairing cryptography in project code. If no suitable binding supports the required scheme, isolate the official JS `drand-client` behind the same adapter boundary rather than skipping verification.

Relay failures trigger retries until the published resolution deadline, then cancellation/restoration. Local `random()` or server secrets are never a fallback.

### 8. Use canonical manifests and domain-separated unbiased selection

Serialize manifests as canonical JSON with gifts ordered by stable virtual gift ID. Commit to:

```text
SHA-256("gift-pool-v1" || round_id || version || canonical_manifest)
```

A full-manifest hash is sufficient because the entire manifest and all versions are disclosed later; a Merkle tree adds no required user capability.

For a remaining count `N`, derive candidate integers using:

```text
SHA-256(
  "gift-draw-v1" || drand_randomness || bet_id || pool_version_hash || counter
)
```

Use 256-bit rejection sampling: reject candidates outside the largest multiple of `N` below `2^256`, then map the accepted candidate modulo `N`. This avoids modulo bias and is exactly reproducible by auditors.

### 9. Recompute economic snapshots, never mutate old quotes

For each new pool version or market snapshot:

```text
player_EV = sum(conservative_player_sale_estimates) / N
price = ceil_to_demo_star(player_EV / 0.90)
actual_RTP = player_EV / price
operator_margin = price - mean(replacement_costs) - fees
```

Eligibility also applies configured worst-outcome and liquidity thresholds. Bets retain the exact snapshot accepted by the user, while subsequent bets use the updated quote. Stale or incomplete inputs pause the collection.

Manual Stars-floor snapshots are versioned JSON records with evidence links and timestamps. TG Gifts daily data is cached and used as an external cross-check with the required CC BY 4.0 attribution. No Telegram marketplace scraping is introduced.

### 10. Disclose complete version history

Closing or expiring a round produces a canonical disclosure package containing:

- Original and subsequent manifests with their commitments.
- Awarded and remaining gifts.
- Valuation and market snapshots.
- Public aggregate statistics for every version.
- Bet bindings, debits/restorations, beacon proofs, and outcomes.
- The canonicalization and selection algorithm versions.

The frontend provides a readable audit view and a downloadable JSON package. Hidden manifests and valuation internals are excluded from public API serializers until the round is disclosed.

### 11. Keep background work in the same single-writer deployment

A backend worker handles pending drand rounds, round disclosure deadlines, and market-data refresh. Database state, not in-memory timers, is authoritative, so restarts are safe.

Docker Compose runs the application locally with a persistent SQLite volume. A single-container build serves the compiled Mini App behind HTTPS for hosted demos. Horizontal scaling would require moving to PostgreSQL and distributed job/lease coordination and is deliberately deferred.

### 12. Verify at four levels

- **Unit/property tests:** pricing, rounding, valuation provenance, canonical commitments, rejection sampling, and economic eligibility.
- **Protocol tests:** official drand vectors, invalid signatures, cutoffs, replayed selection, disclosure recomputation, and deterministic risk simulations.
- **Database tests:** concurrent attempts, duplicate idempotency keys, crash recovery, gift uniqueness, balance conservation, and reset during pending states.
- **Playwright:** Telegram-associated demo login, collection browsing, confirmation, pending/reveal, inventory, reset, and completed-round audit on a mobile viewport.

## Risks / Trade-offs

- **Python drand scheme support is unproven** → Make verification the first spike, use official vectors, and keep a client-adapter fallback without weakening verification.
- **Public relay or beacon downtime** → Use multiple relays, persistent pending state, explicit deadlines, and automatic demo-debit restoration; never substitute RNG.
- **Per-collection serialization limits throughput** → Keep reveal latency low and document the constraint; introduce batch draws only as a separately specified change.
- **SQLite writer contention** → Use one writer, immediate transactions, short critical sections, and unique constraints; migrate before horizontal scaling.
- **Manual Stars-floor estimates can be wrong or stale** → Publish provenance, cross-check external data, apply conservative discounts, and pause expired pools.
- **A hidden pool requires trust until disclosure** → Enforce disclosure deadlines and retain immutable evidence so false statistics become detectable after the round.
- **Hidden data can leak through API responses or logs** → Use separate public/internal serializers and exclude secret manifests from application logs.
- **Demo assets may be mistaken for real value** → Keep persistent demo labels and provide no purchase, withdrawal, wallet, or transfer affordances.

## Migration Plan

1. Create the initial Alembic schema and seed ten demo collections with versioned market snapshots.
2. Run protocol and concurrency tests before enabling draw endpoints.
3. Deploy the single-container demo with an empty persistent volume and validate one live drand-backed round.
4. Roll back by disabling new attempts, resolving or cancelling pending bets, and restoring the previous container/image. Since the project is greenfield and demo-only, no production asset migration is required.
