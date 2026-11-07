import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type Account, type Bet } from '../api/client';
import { HistoryPage } from './HistoryPage';
import { InventoryPage } from './InventoryPage';

vi.mock('../api/client', () => ({
  api: {
    getInventory: vi.fn(),
    getAttempts: vi.fn(),
    resetAccount: vi.fn(),
  },
}));

vi.mock('../appContext', () => ({ useAppContext: () => context }));

const account: Account = {
  telegram_user_id: 1001,
  username: 'player',
  demo_balance: 10000,
  active_epoch: 1,
  asset_mode: 'simulated',
};

let context: { account: Account; refreshAccount: ReturnType<typeof vi.fn> };

const gift = {
  id: 'gift-1',
  bet_id: 'bet-1',
  collection_id: 'plush-pepe',
  round_id: 'round-1',
  model: 'Plush Pepe',
  backdrop: 'Midnight',
  symbol: 'Star',
  rarity: 'Rare',
  number: 2,
  player_sale_estimate: 110,
  ticket_price: 144,
  value_minus_ticket: -34,
  awarded_at: '2026-01-01T00:00:03',
};

function attempt(overrides: Partial<Bet>): Bet {
  return {
    id: 'bet-1',
    collection_id: 'plush-pepe',
    round_id: 'round-1',
    pool_version_id: 'pool-1',
    pool_version_hash: 'a'.repeat(64),
    state: 'COMPLETED',
    price: 144,
    remaining_count: 4,
    future_beacon_round: 12345,
    acceptance_cutoff: '2026-01-01T00:00:02',
    resolution_deadline: '2026-01-01T00:01:03',
    created_at: '2026-01-01T00:00:00',
    resolved_at: '2026-01-01T00:00:03',
    cancellation_reason: null,
    gift: null,
    beacon: null,
    asset_mode: 'simulated',
    ...overrides,
  };
}

function renderPage(page: 'inventory' | 'history') {
  render(
    <MemoryRouter
      initialEntries={[`/${page}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      {page === 'inventory' ? <InventoryPage /> : <HistoryPage />}
    </MemoryRouter>,
  );
}

describe('inventory and history', () => {
  beforeEach(() => {
    context = { account, refreshAccount: vi.fn().mockResolvedValue(account) };
    vi.mocked(api.getInventory).mockResolvedValue({
      gifts: [],
      asset_mode: 'simulated',
    });
    vi.mocked(api.getAttempts).mockResolvedValue({
      attempts: [],
      asset_mode: 'simulated',
    });
    vi.mocked(api.resetAccount).mockResolvedValue({
      ...account,
      active_epoch: 2,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows awarded attributes and links each gift to its draw and round', async () => {
    vi.mocked(api.getInventory).mockResolvedValue({
      gifts: [gift],
      asset_mode: 'simulated',
    });
    renderPage('inventory');

    expect(
      await screen.findByRole('heading', { name: 'Plush Pepe #2' }),
    ).toBeVisible();
    expect(screen.getByText('Midnight')).toBeVisible();
    expect(screen.getByText('Star')).toBeVisible();
    expect(screen.getByText('Rare')).toBeVisible();
    expect(screen.getByText('110 ★')).toBeVisible();
    expect(screen.getByText('-34 ★')).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'View associated draw' }),
    ).toHaveAttribute('href', '/bets/bet-1');
    expect(screen.getByRole('link', { name: 'View round' })).toHaveAttribute(
      'href',
      '/rounds/round-1/audit',
    );
  });

  it('renders useful empty states', async () => {
    renderPage('inventory');
    expect(
      await screen.findByRole('heading', { name: 'No virtual gifts yet' }),
    ).toBeVisible();
    cleanup();
    renderPage('history');
    expect(
      await screen.findByRole('heading', {
        name: 'No attempts in this demo epoch',
      }),
    ).toBeVisible();
  });

  it('lists completed and failed attempts with outcome and restoration details', async () => {
    vi.mocked(api.getAttempts).mockResolvedValue({
      attempts: [
        attempt({
          gift: {
            id: 'gift-1',
            model: 'Plush Pepe',
            backdrop: 'Midnight',
            symbol: 'Star',
            rarity: 'Rare',
            number: 2,
            player_sale_estimate: 110,
            ticket_price: 144,
            value_minus_ticket: -34,
          },
        }),
        attempt({
          id: 'bet-2',
          state: 'CANCELLED',
          cancellation_reason: 'verified_randomness_unavailable_by_deadline',
        }),
      ],
      asset_mode: 'simulated',
    });
    renderPage('history');

    expect(await screen.findByText('Completed')).toBeVisible();
    expect(screen.getByText('Network failure')).toBeVisible();
    expect(
      screen.getByText('Full demo debit restored; no gift awarded.'),
    ).toBeVisible();
    expect(
      screen.getAllByRole('link', { name: 'Inspect attempt' }),
    ).toHaveLength(2);
  });

  it('requires confirmation, refreshes account state, and clears active history after reset', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getAttempts)
      .mockResolvedValueOnce({
        attempts: [attempt({})],
        asset_mode: 'simulated',
      })
      .mockResolvedValueOnce({ attempts: [], asset_mode: 'simulated' });
    renderPage('history');
    await screen.findByRole('link', { name: 'Inspect attempt' });

    await user.click(
      screen.getByRole('button', { name: 'Reset demo progress' }),
    );
    expect(api.resetAccount).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Keep progress' }));
    expect(
      screen.queryByRole('group', { name: 'Confirm demo reset' }),
    ).toBeNull();

    await user.click(
      screen.getByRole('button', { name: 'Reset demo progress' }),
    );
    await user.click(screen.getByRole('button', { name: 'Yes, reset demo' }));
    expect(await screen.findByText(/Demo account reset/)).toBeVisible();
    expect(api.resetAccount).toHaveBeenCalledTimes(1);
    expect(context.refreshAccount).toHaveBeenCalledTimes(1);
    expect(api.getAttempts).toHaveBeenCalledTimes(2);
    expect(
      screen.getByRole('heading', { name: 'No attempts in this demo epoch' }),
    ).toBeVisible();
  });
});
