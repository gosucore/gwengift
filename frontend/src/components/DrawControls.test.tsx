import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  api,
  type Account,
  type Bet,
  type CollectionDetail,
} from '../api/client';
import { DrawControls } from './DrawControls';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return { ...actual, api: { createBet: vi.fn() } };
});

vi.mock('../appContext', () => ({
  useAppContext: () => context,
}));

let context: {
  account: Account;
  refreshAccount: ReturnType<typeof vi.fn>;
};

const account: Account = {
  telegram_user_id: 1001,
  username: 'player',
  demo_balance: 10000,
  active_epoch: 1,
  asset_mode: 'simulated',
};

const collection = {
  id: 'plush-pepe',
  available: true,
  pool: { id: 'pool-1', price: 144, remaining_count: 4 },
} as CollectionDetail;

function renderControls(onPoolChanged = vi.fn().mockResolvedValue(undefined)) {
  render(
    <MemoryRouter
      initialEntries={['/collections/plush-pepe']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/collections/:id"
          element={
            <DrawControls
              collection={collection}
              onPoolChanged={onPoolChanged}
            />
          }
        />
        <Route path="/bets/:id" element={<p>Committed draw route</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return onPoolChanged;
}

describe('DrawControls', () => {
  beforeEach(() => {
    context = { account, refreshAccount: vi.fn().mockResolvedValue(account) };
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('requires exact-price confirmation and prevents duplicate submissions', async () => {
    const user = userEvent.setup();
    let resolve: (bet: Bet) => void = () => undefined;
    vi.mocked(api.createBet).mockReturnValue(
      new Promise<Bet>((next) => {
        resolve = next;
      }),
    );
    renderControls();
    await user.click(
      screen.getByRole('button', { name: 'Review 144 ★ demo ticket' }),
    );
    expect(screen.getByRole('group')).toHaveTextContent(
      'Confirm this exact demo price',
    );
    const confirm = screen.getByRole('button', { name: 'Confirm 144 ★' });
    await user.click(confirm);
    await user.click(confirm);

    expect(api.createBet).toHaveBeenCalledTimes(1);
    expect(api.createBet).toHaveBeenCalledWith({
      collection_id: 'plush-pepe',
      pool_version_id: 'pool-1',
      idempotency_key: expect.any(String),
    });
    resolve({ id: 'bet-1' } as Bet);
    expect(await screen.findByText('Committed draw route')).toBeVisible();
    expect(context.refreshAccount).toHaveBeenCalledTimes(1);
  });

  it('disables submission when the demo balance is insufficient', async () => {
    context.account = { ...account, demo_balance: 50 };
    renderControls();

    const review = screen.getByRole('button', {
      name: 'Review 144 ★ demo ticket',
    });
    expect(review).toBeDisabled();
    expect(
      screen.getByText('Insufficient demo Stars for this ticket.'),
    ).toBeVisible();
    expect(api.createBet).not.toHaveBeenCalled();
  });

  it('retries a failed request with the same idempotency key', async () => {
    const user = userEvent.setup();
    vi.mocked(api.createBet)
      .mockRejectedValueOnce(
        new ApiError('Insufficient demo Stars balance', 400),
      )
      .mockResolvedValueOnce({ id: 'bet-retry' } as Bet);
    renderControls();
    await user.click(
      screen.getByRole('button', { name: 'Review 144 ★ demo ticket' }),
    );
    await user.click(screen.getByRole('button', { name: 'Confirm 144 ★' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Insufficient demo Stars balance',
    );

    await user.click(screen.getByRole('button', { name: 'Confirm 144 ★' }));
    expect(await screen.findByText('Committed draw route')).toBeVisible();
    const firstKey = vi.mocked(api.createBet).mock.calls[0][0].idempotency_key;
    const secondKey = vi.mocked(api.createBet).mock.calls[1][0].idempotency_key;
    expect(secondKey).toBe(firstKey);
  });

  it('reloads a stale pool quote instead of silently accepting it', async () => {
    const user = userEvent.setup();
    vi.mocked(api.createBet).mockRejectedValue(
      new ApiError('Pool quote changed', 409),
    );
    const onPoolChanged = renderControls();
    await user.click(
      screen.getByRole('button', { name: 'Review 144 ★ demo ticket' }),
    );
    await user.click(screen.getByRole('button', { name: 'Confirm 144 ★' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Pool quote changed',
    );
    expect(onPoolChanged).toHaveBeenCalledTimes(1);
  });
});
