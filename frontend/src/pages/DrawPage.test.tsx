import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, type Bet } from '../api/client';
import { DrawPage } from './DrawPage';

vi.mock('../api/client', () => ({ api: { getBet: vi.fn() } }));

function bet(overrides: Partial<Bet> = {}): Bet {
  return {
    id: 'bet-12345678',
    collection_id: 'plush-pepe',
    round_id: 'round-1',
    pool_version_id: 'pool-1',
    pool_version_hash: 'a'.repeat(64),
    state: 'PENDING_RANDOMNESS',
    price: 144,
    remaining_count: 4,
    future_beacon_round: 12345,
    acceptance_cutoff: '2026-01-01T00:00:02',
    resolution_deadline: '2026-01-01T00:01:03',
    created_at: '2026-01-01T00:00:00',
    resolved_at: null,
    cancellation_reason: null,
    gift: null,
    beacon: null,
    asset_mode: 'simulated',
    ...overrides,
  };
}

function renderDraw() {
  return render(
    <MemoryRouter
      initialEntries={['/bets/bet-12345678']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <DrawPage />
    </MemoryRouter>,
  );
}

describe('DrawPage', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('polls a committed pending draw and replaces it with the verified gift', async () => {
    vi.useFakeTimers();
    vi.mocked(api.getBet)
      .mockResolvedValueOnce(bet())
      .mockResolvedValueOnce(
        bet({
          state: 'COMPLETED',
          resolved_at: '2026-01-01T00:00:03',
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
          beacon: {
            network: 'quicknet',
            round: 12345,
            signature: 'ab'.repeat(48),
            randomness: 'cd'.repeat(32),
            verified_at: '2026-01-01T00:00:03',
          },
        }),
      );
    renderDraw();
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText('Committed to drand round 12345')).toBeVisible();
    expect(screen.getByText(/No outcome can be selected/)).toBeVisible();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(
      screen.getByRole('heading', { name: 'Gift revealed' }),
    ).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Plush Pepe' })).toBeVisible();
    expect(screen.getByText('Midnight')).toBeVisible();
    expect(screen.getByText('Star')).toBeVisible();
    expect(screen.getByText('Rare')).toBeVisible();
    expect(screen.getByText('34 ★ below the ticket')).toBeVisible();
    expect(screen.getByText(/randomness: cdcd/)).toBeVisible();
    expect(api.getBet).toHaveBeenCalledTimes(2);
  });

  it('marks deadline cancellation as Network failure and shows full restoration', async () => {
    vi.mocked(api.getBet).mockResolvedValue(
      bet({
        state: 'CANCELLED',
        resolved_at: '2026-01-01T00:01:03',
        cancellation_reason: 'verified_randomness_unavailable_by_deadline',
      }),
    );
    renderDraw();

    expect(await screen.findByText('Network failure')).toBeVisible();
    expect(screen.getByText(/No gift was awarded/)).toBeVisible();
    expect(screen.getByText(/144 ★ demo debit was restored/)).toBeVisible();
    expect(screen.queryByText('Gift revealed')).toBeNull();
  });

  it('shows above-ticket comparison without changing the outcome', async () => {
    const completed = bet({
      state: 'COMPLETED',
      gift: {
        id: 'gift-2',
        model: 'Plush Pepe',
        backdrop: 'Gold',
        symbol: 'Gem',
        rarity: 'Epic',
        number: 4,
        player_sale_estimate: 180,
        ticket_price: 144,
        value_minus_ticket: 36,
      },
    });
    vi.mocked(api.getBet).mockResolvedValue(completed);
    renderDraw();

    expect(await screen.findByText('36 ★ above the ticket')).toBeVisible();
    expect(api.getBet).toHaveBeenCalledTimes(1);
  });
});
