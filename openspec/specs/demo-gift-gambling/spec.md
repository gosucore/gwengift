# demo-gift-gambling Specification

## Purpose

Provides an accessible Telegram Mini App gambling loop with demo Stars and virtual gifts, allowing users to play, inspect results, and review rounds without purchasing or owning real assets.

## Requirements

### Requirement: Unambiguous simulation mode
The system SHALL label balances, gifts, valuations, and winnings as simulated throughout the user flow and MUST NOT offer real payments, wallet connections, or real NFT transfers.

#### Scenario: User opens the Mini App
- **WHEN** a user opens any gameplay or inventory screen
- **THEN** the screen visibly identifies the assets as demo assets and provides no real-money purchase or withdrawal action

### Requirement: Telegram-associated demo account
The system SHALL associate each demo balance, inventory, and draw history with an authenticated Telegram Mini App user and reject invalid launch credentials.

#### Scenario: Valid Telegram launch
- **WHEN** a user opens the Mini App with valid Telegram launch data
- **THEN** the system loads or creates that user's demo account

#### Scenario: Invalid Telegram launch
- **WHEN** launch data is missing or fails authentication outside an explicit development mode
- **THEN** the system denies access to account mutations and explains that the app must be opened through Telegram

### Requirement: Demo balance and reset
The system SHALL provide a starting demo Stars balance and a confirmed reset action that restores the account to its initial demo state.

#### Scenario: Reset demo progress
- **WHEN** a user confirms the demo reset action
- **THEN** the system restores the starting balance and clears that user's virtual inventory and draw history

#### Scenario: Insufficient balance
- **WHEN** a user attempts a draw costing more than the available demo balance
- **THEN** the system rejects the attempt without debiting Stars or starting a draw

### Requirement: Collection catalog
The system SHALL present ten playable gift collections with their current ticket price, calculated RTP, expected value, remaining quantity, and availability status.

#### Scenario: Browse collections
- **WHEN** a user opens the collection catalog
- **THEN** the user can compare all ten collections and open any available collection detail view

#### Scenario: Collection unavailable
- **WHEN** a collection is paused or fails an economic or data-freshness check
- **THEN** the system explains the unavailability and prevents new attempts in that collection

### Requirement: Draw confirmation and pending state
The system SHALL require confirmation of the exact demo price before a draw and display a pending state until the committed randomness resolves.

#### Scenario: Confirm a draw
- **WHEN** a user confirms an available collection and price
- **THEN** the system debits at most once, displays the pending draw, and prevents duplicate submission of the same attempt

#### Scenario: Resolve a draw
- **WHEN** the committed randomness resolves successfully
- **THEN** the system replaces the pending state with the awarded virtual gift and its reveal presentation

#### Scenario: Randomness resolution deadline expires
- **WHEN** verified committed drand randomness is not obtained by the published resolution deadline
- **THEN** the system cancels the draw, marks the attempt as "Network failure" in history, restores the full demo Stars debit, and awards no gift

### Requirement: Gift reveal
The system SHALL reveal the awarded gift's collection, model, backdrop, symbol, rarity, number, estimated value, and comparison with the ticket price.

#### Scenario: View a winning result
- **WHEN** a draw completes
- **THEN** the user sees the awarded attributes and whether its estimated value is below, equal to, or above the paid demo price

### Requirement: Virtual inventory and history
The system SHALL store every awarded gift in the user's virtual inventory and retain a chronological history of the user's completed and failed attempts.

#### Scenario: Inspect inventory
- **WHEN** a user opens the inventory after winning a gift
- **THEN** the user can inspect that gift and navigate to its associated draw and round

### Requirement: Access to fairness information
The system SHALL provide access to current aggregate statistics, valuation provenance, round commitments, completed-round disclosures, and draw verification information.

#### Scenario: Inspect a completed round
- **WHEN** a user opens a completed round
- **THEN** the user can view its disclosed manifest and the evidence needed to verify its published statistics and draws

### Requirement: Telegram-native mobile experience
The user interface SHALL adapt to Telegram's light or dark theme and remain usable on a mobile viewport without requiring desktop-only navigation.

#### Scenario: Open on a mobile Telegram client
- **WHEN** a user opens the Mini App on a supported mobile client
- **THEN** the catalog, confirmation, reveal, inventory, and audit flows remain readable and operable
