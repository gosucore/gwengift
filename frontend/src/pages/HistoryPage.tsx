import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type AttemptHistory, type Bet } from '../api/client';
import { ResetDemoAccount } from '../components/ResetDemoAccount';
import { formatDate, formatStars } from '../format';

function attemptStatus(bet: Bet): string {
  if (bet.state === 'COMPLETED') return 'Completed';
  if (bet.state === 'CANCELLED') {
    return bet.cancellation_reason === 'demo_account_reset'
      ? 'Reset cancellation'
      : 'Network failure';
  }
  return 'Pending verified randomness';
}

export function HistoryPage() {
  const [history, setHistory] = useState<AttemptHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setHistory(await api.getAttempts());
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load attempt history',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="page">
      <p className="eyebrow">ACTIVE DEMO EPOCH</p>
      <h1>Attempt history</h1>
      {loading && (
        <p className="loading-panel" role="status">
          Loading attempts…
        </p>
      )}
      {error && (
        <div className="notice error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      )}
      {!loading && history?.attempts.length === 0 && (
        <section className="empty-state">
          <h2>No attempts in this demo epoch</h2>
          <p>Confirmed draws and cancellations will be listed here.</p>
        </section>
      )}
      <div className="history-list">
        {history?.attempts.map((bet) => (
          <article className="history-item" key={bet.id}>
            <div>
              <span className={`state-label ${bet.state.toLowerCase()}`}>
                {attemptStatus(bet)}
              </span>
              <h2>{bet.gift?.model ?? bet.collection_id}</h2>
              <p className="muted">
                {formatDate(bet.created_at)} UTC · {formatStars(bet.price)} demo
                ticket
              </p>
              {bet.gift && (
                <p>
                  Estimated {formatStars(bet.gift.player_sale_estimate)} ·{' '}
                  {bet.gift.value_minus_ticket >= 0 ? '+' : ''}
                  {formatStars(bet.gift.value_minus_ticket)} versus ticket
                </p>
              )}
              {bet.state === 'CANCELLED' && (
                <p>Full demo debit restored; no gift awarded.</p>
              )}
            </div>
            <Link className="text-link" to={`/bets/${bet.id}`}>
              Inspect attempt
            </Link>
          </article>
        ))}
      </div>
      <ResetDemoAccount onReset={load} />
    </main>
  );
}
