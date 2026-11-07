import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { api } from './api/client';
import type { TelegramWebApp } from './telegram';

vi.mock('./api/client', () => ({
  api: {
    getAccount: vi.fn(),
    getCatalog: vi
      .fn()
      .mockResolvedValue({ collections: [], asset_mode: 'simulated' }),
    getInventory: vi
      .fn()
      .mockResolvedValue({ gifts: [], asset_mode: 'simulated' }),
    getAttempts: vi
      .fn()
      .mockResolvedValue({ attempts: [], asset_mode: 'simulated' }),
    resetAccount: vi.fn(),
  },
}));

const account = {
  telegram_user_id: 1001,
  username: 'player',
  demo_balance: 10000,
  active_epoch: 1,
  asset_mode: 'simulated',
} as const;

function telegramWebApp(colorScheme: 'light' | 'dark'): TelegramWebApp {
  return {
    initData: 'signed-test-data',
    colorScheme,
    themeParams: {},
    ready: vi.fn(),
    expand: vi.fn(),
    onEvent: vi.fn(),
    offEvent: vi.fn(),
  };
}

describe('App shell', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
    vi.mocked(api.getAccount).mockResolvedValue(account);
  });

  afterEach(() => {
    cleanup();
    delete window.Telegram;
    delete document.documentElement.dataset.theme;
  });

  it('loads a Telegram-associated demo account and keeps simulation labels visible', async () => {
    const webApp = telegramWebApp('light');
    window.Telegram = { WebApp: webApp };
    render(<App />);

    expect(await screen.findByText('10,000')).toBeInTheDocument();
    expect(screen.getAllByText('SIMULATION · DEMO ASSETS ONLY')).toHaveLength(
      1,
    );
    expect(
      screen.getByRole('navigation', { name: 'Primary navigation' }),
    ).toBeVisible();
    expect(webApp.ready).toHaveBeenCalled();
    expect(webApp.expand).toHaveBeenCalled();
    expect(
      screen.queryByRole('button', { name: /purchase|withdraw|wallet/i }),
    ).toBeNull();
    expect(
      screen.queryByRole('link', { name: /purchase|withdraw|wallet/i }),
    ).toBeNull();
  });

  it('adapts to Telegram dark mode and supports explicit theme switching', async () => {
    window.Telegram = { WebApp: telegramWebApp('dark') };
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText('10,000');
    expect(document.documentElement.dataset.theme).toBe('dark');
    await user.click(
      screen.getByRole('button', { name: 'Switch to light theme' }),
    );
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('provides mobile navigation to inventory and history', async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText('10,000');

    await user.click(screen.getByRole('link', { name: 'Inventory' }));
    expect(
      screen.getByRole('heading', { name: 'Virtual inventory' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'History' }));
    expect(
      screen.getByRole('heading', { name: 'Attempt history' }),
    ).toBeInTheDocument();
  });

  it('explains authenticated launch failures without exposing account actions', async () => {
    vi.mocked(api.getAccount).mockRejectedValue(
      new Error('Telegram launch data is required'),
    );
    render(<App />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Open this Mini App through Telegram');
    expect(alert).toHaveTextContent('Telegram launch data is required');
    await waitFor(() => expect(api.getAccount).toHaveBeenCalled());
  });
});
