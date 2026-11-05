# Proposal

## Why

The project needs a portfolio-quality Telegram iGaming demo that demonstrates a complete product loop without requiring real-money payments, NFT inventory, or Web3 infrastructure. A simulator with virtual assets, real market-price references, and verifiable randomness makes the economics and fairness mechanics testable while keeping the demo accessible to every reviewer.

## What Changes

- Add a Telegram Mini App with ten gift collections, demo Stars, virtual pre-minted gift NFTs, reveal animations, inventory, and round history.
- Add collection-specific pools with hidden full manifests and public aggregate statistics, including price, expected value, calculated RTP, remaining supply, valuation provenance, and data age.
- Add conservative Stars-floor pricing with external TG Gifts data as a cross-check, targeting 90% calculated RTP and rejecting economically unsuitable pools.
- Add publicly verifiable drand draws bound to a specific bet and future beacon round; never substitute local randomness when the beacon is unavailable.
- Add cryptographic pool commitments and post-round disclosure of manifests, valuations, draw parameters, and outcomes for independent auditing.
- Clearly label all balances, gifts, and winnings as simulated. Real payments, custodial Telegram Business inventory, real NFT transfers, smart contracts, external liquidity providers, crafting, and LLM features are out of scope.

## Capabilities

### New Capabilities

- `demo-gift-gambling`: Telegram Mini App gameplay, demo balances, virtual gift inventory, simulation disclosures, and the core collection-to-reveal user flow.
- `gift-pool-economics`: Virtual pool composition, conservative valuation snapshots, dynamic ticket pricing, calculated RTP, pool eligibility rules, and aggregate public statistics.
- `provably-fair-gift-draws`: Bet-to-beacon binding, unbiased gift selection, hidden pool commitments, draw failure behavior, and post-round verification.

### Modified Capabilities

None; this is a greenfield project with no existing specifications.

## Impact

- Creates a new React frontend, FastAPI backend, and SQLite persistence layer.
- Introduces integrations with Telegram Mini App launch data, public drand relays, and TG Gifts open data, plus manually curated Stars-floor snapshots.
- Requires Python-compatible drand signature verification, deterministic draw algorithms, transactional demo-balance updates, and automated economic and end-to-end tests.
- Does not integrate real payments, TON wallets, Telegram Business gift transfers, or production blockchain services.
