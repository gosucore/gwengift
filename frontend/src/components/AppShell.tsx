import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { api, type Account } from '../api/client';
import type { AppContext } from '../appContext';
import { useTelegramTheme } from '../hooks/useTelegramTheme';

export function AppShell() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { theme, toggleTheme } = useTelegramTheme();

  const refreshAccount = useCallback(async () => {
    try {
      const next = await api.getAccount();
      setAccount(next);
      setError(null);
      return next;
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load the demo account',
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshAccount();
  }, [refreshAccount]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="demo-label">SIMULATION · DEMO ASSETS ONLY</p>
          <NavLink to="/" className="brand" aria-label="GwenGift catalog">
            GwenGift
          </NavLink>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </header>

      <section className="balance-bar" aria-label="Demo account balance">
        <span>Demo Stars</span>
        <strong>
          {loading
            ? '…'
            : account
              ? account.demo_balance.toLocaleString()
              : '—'}
        </strong>
      </section>

      {error && (
        <section className="notice error" role="alert">
          <strong>Open this Mini App through Telegram.</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void refreshAccount()}>
            Retry
          </button>
        </section>
      )}

      <Outlet context={{ account, refreshAccount } satisfies AppContext} />

      <nav className="bottom-nav" aria-label="Primary navigation">
        <NavLink to="/" end>
          <span className="nav-icon" aria-hidden="true">
            ▦
          </span>
          Collections
        </NavLink>
        <NavLink to="/inventory">
          <span className="nav-icon" aria-hidden="true">
            ◇
          </span>
          Inventory
        </NavLink>
        <NavLink to="/history">
          <span className="nav-icon" aria-hidden="true">
            ↻
          </span>
          History
        </NavLink>
      </nav>
    </div>
  );
}
