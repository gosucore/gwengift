# Spec Delta

## Purpose

Defines how virtual gift pools are valued and priced so every demo attempt has explicit, reproducible economics instead of an arbitrary ticket price or an inflated rarity claim.

## ADDED Requirements

### Requirement: Collection pool composition
Each playable collection SHALL contain a finite set of uniquely identified virtual gifts with collection, model, backdrop, symbol, rarity, and number attributes.

#### Scenario: Initialize a collection
- **WHEN** a collection round is initialized
- **THEN** every virtual gift has a unique identity and a complete attribute record suitable for later disclosure

### Requirement: Conservative player valuation
Each gift SHALL have a conservative player-sale estimate denominated in demo Stars, based on Stars-floor evidence and excluding unsupported premiums for numbers or attributes.

#### Scenario: Value a gift without attribute sales evidence
- **WHEN** a gift has no reliable comparable sales for its number, backdrop, or symbol
- **THEN** those attributes contribute no premium to its player-sale estimate

#### Scenario: External price disagrees with Stars floor
- **WHEN** external TG Gifts data materially disagrees with the primary Stars-floor estimate
- **THEN** the system records the discrepancy and applies the configured conservative valuation or pause rule

### Requirement: Replacement valuation
Each gift SHALL have a separate replacement-cost estimate that includes acquisition, expected fees, and the cost of restoring equivalent pool inventory.

#### Scenario: Calculate operator economics
- **WHEN** the system evaluates a pool
- **THEN** it uses replacement cost rather than the player-sale estimate to determine whether the pool is economically sustainable

### Requirement: Valuation provenance
Every valuation snapshot SHALL include its primary source, external cross-check, source currency, conversion rule when applicable, liquidity discount, and observation timestamp.

#### Scenario: Inspect a valuation snapshot
- **WHEN** a user or auditor requests the evidence for a displayed price
- **THEN** the system returns the provenance needed to reproduce the conservative estimate

### Requirement: Target calculated RTP
The system SHALL target 90% calculated RTP by deriving the ticket price from the pool's mean conservative player-sale estimate and SHALL disclose any rounding effect.

#### Scenario: Price a pool
- **WHEN** a valid pool valuation snapshot is available
- **THEN** the displayed ticket price and actual calculated RTP are reproducible from the published formula and current gift estimates

### Requirement: Economic eligibility
The system SHALL make a pool playable only when it satisfies configured minimum RTP, operator-margin, worst-outcome value, and liquidity requirements.

#### Scenario: Pool has attractive displayed RTP but negative operator margin
- **WHEN** expected replacement costs and fees exceed sustainable levels
- **THEN** the system rejects or pauses the pool despite its calculated player RTP

#### Scenario: Pool contains inadequate worst outcomes
- **WHEN** the lowest estimated prize violates the configured minimum ratio to ticket price
- **THEN** the system does not offer the pool for new attempts

### Requirement: Public aggregate statistics
Before a round is disclosed, the system SHALL publish only aggregate pool statistics, including remaining quantity, price, expected value, RTP, value distribution, and valuation age, while withholding the full gift list.

#### Scenario: View an active pool
- **WHEN** a user inspects an undisclosed pool
- **THEN** the user can evaluate its published economics without retrieving the identities of individual gifts

### Requirement: Dynamic pool snapshots
The system SHALL create a new versioned economic snapshot whenever pool composition or a valuation input changes and bind each attempt to exactly one snapshot.

#### Scenario: A gift leaves the pool
- **WHEN** a draw awards a gift whose valuation affects aggregate statistics
- **THEN** subsequent attempts receive updated statistics and a new pool-version commitment

#### Scenario: Market inputs change
- **WHEN** a fresh valuation changes the pool's expected value or operator margin
- **THEN** subsequent attempts use the revised price and availability rather than the stale quote

### Requirement: Stale data protection
The system SHALL stop accepting attempts when valuation data exceeds its configured freshness limit or required provenance is unavailable.

#### Scenario: Valuation expires
- **WHEN** the current valuation snapshot becomes stale
- **THEN** the collection becomes unavailable until a valid replacement snapshot is recorded

### Requirement: Risk evaluation
The system SHALL support reproducible simulations of drawdown and reserve requirements using the pool's replacement-cost distribution, ticket price, fees, and configured volume.

#### Scenario: Evaluate a proposed pool
- **WHEN** an operator runs the economic risk evaluation
- **THEN** the system reports expected margin and simulated adverse outcomes without presenting expected value as a short-term profit guarantee
