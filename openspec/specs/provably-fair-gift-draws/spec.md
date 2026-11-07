# provably-fair-gift-draws Specification

## Purpose

Ensures that each virtual gift outcome is selected from the promised pool using publicly verifiable future randomness and can be independently audited after the hidden manifest is disclosed.

## Requirements

### Requirement: Hidden pool commitment
The system SHALL publish a cryptographic commitment to the complete ordered pool manifest before accepting attempts and MUST NOT change that manifest except through disclosed pool-version updates.

#### Scenario: Start a round
- **WHEN** a pool round opens
- **THEN** its commitment, aggregate statistics, draw algorithm, and disclosure deadline are available before the first attempt

#### Scenario: Manifest differs from commitment
- **WHEN** the disclosed manifest does not reproduce the published commitment
- **THEN** verification fails and identifies the round as invalid

### Requirement: Future beacon binding
Each attempt SHALL be bound before randomness is known to a unique bet identifier, pool version, remaining quantity, price, and future drand round with an acceptance cutoff.

#### Scenario: Accept an attempt before cutoff
- **WHEN** an attempt is confirmed before the published cutoff
- **THEN** its binding record is immutable and the selected beacon round has not yet resolved

#### Scenario: Attempt arrives too late
- **WHEN** confirmation cannot be completed before the cutoff
- **THEN** the system does not start the draw and leaves the demo balance unchanged or restores any reserved debit

### Requirement: Beacon authenticity verification
The system SHALL verify the drand signature and derived randomness against the configured network's public key and MUST NOT trust an unverified relay response.

#### Scenario: Valid beacon response
- **WHEN** a relay returns a correctly signed value for the committed round
- **THEN** the system accepts it as input to the published selection algorithm

#### Scenario: Invalid beacon response
- **WHEN** the signature, round, network identity, or derived randomness fails verification
- **THEN** the system rejects the response and does not select a gift

### Requirement: Deterministic unbiased selection
The system SHALL derive an outcome using the published deterministic algorithm over verified randomness, the bet identifier, and the remaining ordered pool without modulo bias or operator-selected substitution.

#### Scenario: Replay a selection
- **WHEN** an auditor supplies the disclosed bet binding, beacon proof, and remaining manifest to the published algorithm
- **THEN** the algorithm returns the same virtual gift that was awarded

### Requirement: Atomic gift reservation
The system SHALL reserve a selected gift and record the corresponding demo debit atomically enough to prevent duplicate awards, duplicate charges, or reuse of a consumed gift.

#### Scenario: Concurrent attempts target one pool
- **WHEN** multiple attempts resolve against the same pool
- **THEN** each gift is awarded at most once and every successful attempt has exactly one corresponding balance mutation

#### Scenario: Retry a resolved attempt
- **WHEN** the same attempt is submitted or resolved again through an idempotent retry
- **THEN** the original result is returned without another debit or gift award

### Requirement: Randomness failure behavior
The system SHALL wait or cancel and restore the demo debit according to the published rule when committed randomness is unavailable and MUST NOT substitute local or operator-chosen randomness.

#### Scenario: Beacon remains unavailable
- **WHEN** valid committed randomness cannot be obtained by the resolution deadline
- **THEN** the attempt enters the published wait or cancellation path and no gift is invented or selected through another RNG

### Requirement: Result and audit record
Every resolved attempt SHALL produce an immutable audit record linking its debit, pool version, beacon proof, selected gift, and inventory outcome.

#### Scenario: Inspect a completed attempt
- **WHEN** a user opens a completed attempt
- **THEN** the user can retrieve its result and the evidence associated with that specific selection

### Requirement: Mandatory round disclosure
By its published deadline, including early termination, the system SHALL disclose the original manifest, pool-version history, valuation evidence, bet bindings, beacon proofs, and outcomes.

#### Scenario: Round sells out
- **WHEN** the final available gift is awarded
- **THEN** the system closes the round and publishes the complete disclosure package

#### Scenario: Round ends with unsold gifts
- **WHEN** the round reaches its disclosure deadline before selling out
- **THEN** the system discloses both awarded and remaining gifts and preserves verification of all completed attempts

### Requirement: Independent economic verification
The disclosed round data SHALL allow an auditor to recompute the historical aggregate statistics, calculated RTP, selection outcomes, and gift uniqueness.

#### Scenario: Audit a completed round
- **WHEN** an auditor processes the complete disclosure package
- **THEN** the auditor can determine whether the published economics and every awarded outcome were consistent with the committed data
