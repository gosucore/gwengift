# Tasks

## 1. Project foundation

- [x] 1.1 Scaffold `frontend/` with React, TypeScript, and Vite and `backend/` with FastAPI, SQLAlchemy, and Alembic; verify the frontend renders and `GET /health` returns success.
- [x] 1.2 Add environment validation, development configuration, Docker Compose, and setup documentation; verify a clean checkout starts with the documented commands and no production secrets are committed.
- [x] 1.3 Configure Python and TypeScript linting, formatting, type checking, and test runners; verify all baseline quality commands pass locally.

## 2. Persistence and demo identity

- [x] 2.1 Implement the initial schema for users, collections, rounds, gifts, pool versions, market snapshots, bets, ledger entries, drand proofs, and disclosures; verify upgrade and downgrade migrations on an empty SQLite database.
- [x] 2.2 Implement Telegram `initData` HMAC/freshness validation and the explicit development-only identity adapter; verify valid, invalid, expired, and spoofed launch-data tests.
- [x] 2.3 Implement demo accounts, starting balances, ledger entries, and epoch-based reset; verify insufficient balances are rejected and reset hides old user history while preserving global audit records.
- [x] 2.4 Add authenticated account and reset API tests plus endpoint documentation; verify users cannot read or mutate another user's demo state.

## 3. Collections and market economics

- [x] 3.1 Add versioned seed data for ten collections and finite virtual-gift pools with complete attributes and unique IDs; verify seeds are repeatable and every collection satisfies the attribute and uniqueness checks.
- [x] 3.2 Implement manual Stars-floor snapshot imports and cached TG Gifts daily imports with timestamps, provenance, conversion rules, and CC BY attribution; verify malformed, missing, stale, and disagreeing inputs follow the configured pause/discount rules.
- [x] 3.3 Implement conservative player-sale and replacement valuations, 90% target RTP pricing, rounding disclosure, operator margin, and eligibility thresholds; verify formula examples and boundary tests for negative margin, weak worst outcomes, and stale data.
- [x] 3.4 Implement deterministic pool-risk simulations and a documented report command; verify identical seeds reproduce drawdown/reserve reports and the report distinguishes expected margin from short-term guarantees.

## 4. Pool commitments and public catalog API

- [x] 4.1 Implement canonical ordered manifests and domain-separated commitments; verify known vectors and tamper tests detect changed gifts, ordering, versions, or round IDs.
- [x] 4.2 Implement append-only pool-version creation after gift or valuation changes; verify old bet quotes remain unchanged while new attempts receive updated statistics.
- [x] 4.3 Implement catalog and collection-detail endpoints exposing only aggregate statistics and provenance before disclosure; verify ten collections are returned and hidden gift identities never leak in responses or logs.

## 5. Verified randomness and draw lifecycle

- [x] 5.1 Complete the drand verification spike for the selected network and document its signature scheme and official test vectors; verify valid vectors pass and altered rounds, signatures, keys, or derived randomness fail.
- [x] 5.2 Implement the drand adapter with network metadata, future-round calculation, acceptance cutoffs, multiple relays, and local verification; verify mocked clock/relay tests never accept an already-resolved or unverified round.
- [x] 5.3 Implement deterministic domain-separated selection with 256-bit rejection sampling and published audit vectors; verify replay returns identical gifts and statistical/boundary tests cover the selection mapping.
- [x] 5.4 Implement bet creation with per-collection leases, immutable bindings, idempotency keys, and atomic demo debits; verify concurrent, duplicate, late, stale-pool, and insufficient-balance requests preserve balance and gift invariants.
- [x] 5.5 Implement worker resolution, cancellation/restoration, gift award, lease release, and restart recovery; verify unavailable/invalid randomness never invokes another RNG and every completed bet has exactly one debit and gift.
- [x] 5.6 Add lifecycle API tests for pending, completed, and cancelled bets; verify clients can safely poll and retry without changing the outcome.

## 6. Inventory, disclosure, and independent audit

- [x] 6.1 Implement virtual inventory and attempt-history endpoints; verify awarded attributes, estimated values, ticket comparisons, user isolation, and epoch filtering.
- [x] 6.2 Implement canonical disclosure generation on sell-out and deadline expiry; verify packages include all pool versions, valuations, bets, proofs, outcomes, and remaining gifts.
- [x] 6.3 Implement disclosure download and verification utilities; verify an independent replay accepts a valid round and rejects manipulated statistics, manifests, beacon proofs, duplicate awards, or outcomes.
- [x] 6.4 Document the disclosure schema, canonicalization, selection algorithm, and local verification command; verify the documented example completes against a generated disclosure package.

## 7. Telegram Mini App core experience

- [x] 7.1 Build the Telegram-aware app shell, generated API client, routing, persistent demo labels, and light/dark mobile theme; verify component tests and mobile screenshots contain no real payment, wallet, or withdrawal actions.
- [x] 7.2 Build the ten-collection catalog and collection-detail statistics/provenance views; verify loading, empty, paused, stale, and discrepancy states through component and API-mock tests.
- [x] 7.3 Build draw confirmation, pending polling, error/cancellation handling, and result reveal with attributes and price comparison; verify duplicate clicks, retries, insufficient balance, and failed randomness behave correctly.
- [x] 7.4 Build inventory, attempt history, and confirmed reset flows; verify gift-to-draw navigation, empty states, and reset behavior with frontend tests.
- [x] 7.5 Build current-round commitment and completed-round audit views with disclosure download; verify users can inspect evidence and reach the documented verification flow.

## 8. Late visual polish

- [x] 8.1 Apply the Native + casino visual treatment and reveal motion after core flows stabilize; verify light/dark mobile screenshot review for every primary screen.
- [x] 8.2 Polish responsive layout, focus states, loading transitions, and reduced-motion behavior; verify keyboard navigation and automated accessibility checks have no serious violations.

## 9. End-to-end integration and deployment

- [x] 9.1 Add Playwright coverage for Telegram-associated login, catalog, confirmation, pending/reveal, inventory, reset, and completed-round audit using deterministic randomness fixtures; verify the complete mobile flow passes.
- [x] 9.2 Build the single-container production image with compiled frontend, migrations, worker, and persistent SQLite volume; verify the documented restart/recovery smoke test retains bets and audit data.
- [x] 9.3 Run a live drand smoke test and an HTTPS Telegram Mini App checklist; verify one real beacon-backed demo round resolves and invalid launch data cannot mutate state.
- [x] 9.4 Run the complete lint, type-check, unit, protocol, concurrency, integration, and production-build commands; verify all pass and the README explains demo scope, setup, deployment, limitations, and verification.
