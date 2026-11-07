import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, type DisclosurePackage, type RoundAudit } from '../api/client';
import type { components } from '../api/schema';
import { RoundAuditPage } from './RoundAuditPage';

vi.mock('../api/client', () => ({
  api: {
    getRoundAudit: vi.fn(),
    getDisclosure: vi.fn(),
  },
}));

const pool: components['schemas']['PublicPoolVersion'] = {
  id: 'pool-1',
  version: 1,
  commitment: 'ab'.repeat(32),
  price: 144,
  expected_value: '128.75',
  actual_rtp: '0.89409722',
  rounding_premium_stars: '0.94',
  operator_margin: '9.25',
  remaining_count: 4,
  value_distribution: {
    minimum: '90',
    median: '122.5',
    maximum: '180',
    below_ticket_count: 2,
    at_or_above_ticket_count: 2,
  },
  commitment_algorithm: 'SHA-256/gift-pool-v1',
  draw_algorithm: 'gift-draw-v1',
};

function audit(disclosure: RoundAudit['disclosure'] = null): RoundAudit {
  return {
    round: {
      id: 'round-1',
      status: disclosure ? 'DISCLOSED' : 'OPEN',
      opens_at: '2026-01-01T00:00:00',
      closes_at: '2026-01-08T00:00:00',
      disclosure_deadline: '2026-01-08T00:00:00',
    },
    collection: {
      id: 'plush-pepe',
      name: 'Plush Pepe',
      description: 'Virtual collection',
      status: disclosure ? 'PAUSED' : 'OPEN',
      available: !disclosure,
      pool,
      valuation: null,
      asset_mode: 'simulated',
    },
    disclosure,
    asset_mode: 'simulated',
  };
}

const disclosed = {
  schema_version: 1,
  asset_mode: 'simulated',
  round: {
    id: 'round-1',
    collection_id: 'plush-pepe',
    status: 'DISCLOSED',
    opens_at: '2026-01-01T00:00:00',
    closes_at: '2026-01-08T00:00:00',
    disclosure_deadline: '2026-01-08T00:00:00',
    disclosed_at: '2026-01-08T00:00:00',
  },
  algorithms: {
    pool_commitment: 'gift-pool-v1-sha256',
    selection: 'gift-draw-v1-sha256-rejection-v1',
    beacon: 'drand-quicknet-bls-unchained-g1-rfc9380',
    canonical_json: 'utf8-sorted-keys-compact',
  },
  pool_versions: [
    {
      ...pool,
      remaining_count: 1,
      manifest: {
        schema_version: 1,
        gifts: [
          {
            id: 'gift-secret-1',
            model: 'Hidden Plush Model',
            backdrop: 'Midnight',
            symbol: 'Star',
            rarity: 'Rare',
            number: 1,
            player_sale_estimate: 90,
            replacement_cost: 95,
          },
        ],
      },
      market_snapshot_id: 'snapshot-1',
      created_at: '2026-01-01T00:00:00',
    },
  ],
  market_snapshots: [
    {
      id: 'snapshot-1',
      collection_id: 'plush-pepe',
      primary_source: 'manual Stars-floor evidence',
      external_source: 'Data: TG Gifts',
      source_currency: 'STARS',
      conversion_rule: '{}',
      liquidity_discount: '0',
      source_payload: { manual: { evidence: 'published-after-deadline' } },
      provenance: {},
      cross_check_discrepancy: null,
      observed_at: '2026-01-01T00:00:00',
      expires_at: '2026-01-02T00:00:00',
      created_at: '2026-01-01T00:00:00',
    },
  ],
  bets: [
    {
      id: 'bet-12345678',
      user_epoch: 1,
      pool_version_id: 'pool-1',
      pool_version_hash: pool.commitment,
      idempotency_key: 'attempt-1',
      future_beacon_round: 12345,
      acceptance_cutoff: '2026-01-01T00:00:02',
      resolution_deadline: '2026-01-01T00:01:03',
      state: 'COMPLETED',
      price: 144,
      remaining_count: 1,
      selected_gift_id: 'gift-secret-1',
      cancellation_reason: null,
      created_at: '2026-01-01T00:00:00',
      resolved_at: '2026-01-01T00:00:03',
      ledger_entries: [
        {
          id: 'ledger-1',
          kind: 'DEBIT',
          amount: -144,
          balance_after: 9856,
          created_at: '2026-01-01T00:00:00',
        },
      ],
      beacon_proof: {
        network: 'quicknet',
        round: 12345,
        signature: 'ab'.repeat(48),
        randomness: 'cd'.repeat(32),
        verification_result: true,
        response: {},
        verified_at: '2026-01-01T00:00:03',
      },
    },
  ],
  gifts: [
    {
      id: 'gift-secret-1',
      model: 'Hidden Plush Model',
      backdrop: 'Midnight',
      symbol: 'Star',
      rarity: 'Rare',
      number: 1,
      player_sale_estimate: 90,
      replacement_cost: 95,
      lifecycle: 'AWARDED',
      owner_epoch: 1,
    },
  ],
} as DisclosurePackage;

function renderAudit() {
  render(
    <MemoryRouter
      initialEntries={['/rounds/round-1/audit']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <RoundAuditPage />
    </MemoryRouter>,
  );
}

describe('RoundAuditPage', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows the current commitment without leaking the hidden manifest', async () => {
    vi.mocked(api.getRoundAudit).mockResolvedValue(audit());
    renderAudit();

    expect(
      await screen.findByRole('heading', { name: 'Round audit' }),
    ).toBeVisible();
    expect(screen.getByText('ab'.repeat(32))).toBeVisible();
    expect(
      screen.getByText('The ordered manifest stays hidden until disclosure.'),
    ).toBeVisible();
    expect(screen.queryByText(/Hidden Plush Model/)).toBeNull();
    expect(
      screen.queryByRole('link', { name: 'Download disclosure JSON' }),
    ).toBeNull();
    expect(api.getDisclosure).not.toHaveBeenCalled();
  });

  it('shows disclosed manifests and proofs with download and local verification flow', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getRoundAudit).mockResolvedValue(
      audit({
        sha256: 'ef'.repeat(32),
        created_at: '2026-01-08T00:00:00',
        download_url: '/api/rounds/round-1/disclosure',
      }),
    );
    vi.mocked(api.getDisclosure).mockResolvedValue(disclosed);
    renderAudit();

    expect(
      await screen.findByRole('heading', { name: 'Complete disclosure' }),
    ).toBeVisible();
    expect(screen.getByText(`SHA-256: ${'ef'.repeat(32)}`)).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'Download disclosure JSON' }),
    ).toHaveAttribute('href', '/api/rounds/round-1/disclosure');
    expect(screen.getByText(/python -m app.verify_disclosure/)).toBeVisible();
    await user.click(screen.getByText(/Version 1 · 1 gifts/));
    expect(screen.getAllByText(/Hidden Plush Model/).length).toBeGreaterThan(0);
    expect(screen.getByText(/signature: abab/)).toBeInTheDocument();
    expect(screen.getByText(/published-after-deadline/)).toBeInTheDocument();
  });
});
